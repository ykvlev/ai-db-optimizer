"""Провайдер-независимый слой LLM.

Поддерживаются (доступны в РФ):
  * GigaChat (Сбер)            — gigachat:<model>
  * YandexGPT (Yandex Cloud)   — yandex:<model>
  * любой OpenAI-совместимый API (DeepSeek, OpenRouter, Ollama, LM Studio, vLLM, …) — <provider_name>:<model>
"""

from __future__ import annotations

import threading
import time
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass

import httpx

from app.config import Settings, get_settings


class LLMError(Exception):
    pass


@dataclass
class LLMResult:
    text: str
    provider: str
    model: str
    latency_ms: float
    prompt_tokens: int | None = None
    completion_tokens: int | None = None


class LLMProvider(ABC):
    name: str
    models: list[str]

    @abstractmethod
    def complete(self, model: str, system: str, user: str, temperature: float) -> LLMResult: ...


def _int(v) -> int | None:
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def _raise_for(resp: httpx.Response, who: str):
    if resp.status_code >= 400:
        raise LLMError(f"{who}: HTTP {resp.status_code}: {resp.text[:500]}")


class OpenAICompatibleProvider(LLMProvider):
    def __init__(self, name: str, base_url: str, api_key: str | None, models: list[str], timeout: float):
        self.name, self.base_url, self.api_key, self.models, self.timeout = name, base_url.rstrip("/"), api_key, models, timeout

    def complete(self, model: str, system: str, user: str, temperature: float) -> LLMResult:
        headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
        body = {"model": model, "temperature": temperature,
                "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}
        t0 = time.perf_counter()
        try:
            r = httpx.post(f"{self.base_url}/chat/completions", json=body, headers=headers, timeout=self.timeout)
        except httpx.HTTPError as e:
            raise LLMError(f"{self.name}: {e}") from e
        _raise_for(r, self.name)
        data = r.json()
        usage = data.get("usage") or {}
        return LLMResult(text=data["choices"][0]["message"]["content"] or "", provider=self.name, model=model,
                         latency_ms=(time.perf_counter() - t0) * 1000,
                         prompt_tokens=_int(usage.get("prompt_tokens")), completion_tokens=_int(usage.get("completion_tokens")))


class GigaChatProvider(LLMProvider):
    OAUTH_URL = "https://ngw.devices.sberbank.ru:9443/api/v2/oauth"
    API_URL = "https://gigachat.devices.sberbank.ru/api/v1/chat/completions"

    def __init__(self, auth_key: str, scope: str, models: list[str], verify: bool | str, timeout: float):
        self.name, self.auth_key, self.scope, self.models, self.verify, self.timeout = \
            "gigachat", auth_key, scope, models, verify, timeout
        self._token: str | None = None
        self._expires_at = 0.0
        self._lock = threading.Lock()

    def _access_token(self) -> str:
        with self._lock:
            if self._token and time.time() < self._expires_at - 60:
                return self._token
            try:
                r = httpx.post(self.OAUTH_URL, data={"scope": self.scope}, verify=self.verify, timeout=30,
                               headers={"Authorization": f"Basic {self.auth_key}", "RqUID": str(uuid.uuid4()),
                                        "Accept": "application/json"})
            except httpx.HTTPError as e:
                raise LLMError(f"GigaChat OAuth: {e}. Если ошибка SSL — укажите GIGACHAT_CA_BUNDLE "
                               "(сертификат НУЦ Минцифры) или GIGACHAT_VERIFY_SSL=false") from e
            _raise_for(r, "GigaChat OAuth")
            data = r.json()
            self._token = data["access_token"]
            self._expires_at = data.get("expires_at", 0) / 1000 or time.time() + 1500
            return self._token

    def complete(self, model: str, system: str, user: str, temperature: float) -> LLMResult:
        body = {"model": model, "temperature": max(temperature, 0.01),
                "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}
        t0 = time.perf_counter()
        try:
            r = httpx.post(self.API_URL, json=body, verify=self.verify, timeout=self.timeout,
                           headers={"Authorization": f"Bearer {self._access_token()}"})
        except httpx.HTTPError as e:
            raise LLMError(f"GigaChat: {e}") from e
        _raise_for(r, "GigaChat")
        data = r.json()
        usage = data.get("usage") or {}
        return LLMResult(text=data["choices"][0]["message"]["content"] or "", provider=self.name, model=model,
                         latency_ms=(time.perf_counter() - t0) * 1000,
                         prompt_tokens=_int(usage.get("prompt_tokens")), completion_tokens=_int(usage.get("completion_tokens")))


class YandexGPTProvider(LLMProvider):
    API_URL = "https://llm.api.cloud.yandex.net/foundationModels/v1/completion"

    def __init__(self, api_key: str, folder_id: str, models: list[str], timeout: float):
        self.name, self.api_key, self.folder_id, self.models, self.timeout = "yandex", api_key, folder_id, models, timeout

    def complete(self, model: str, system: str, user: str, temperature: float) -> LLMResult:
        body = {"modelUri": f"gpt://{self.folder_id}/{model}",
                "completionOptions": {"stream": False, "temperature": temperature, "maxTokens": "8000"},
                "messages": [{"role": "system", "text": system}, {"role": "user", "text": user}]}
        t0 = time.perf_counter()
        try:
            r = httpx.post(self.API_URL, json=body, timeout=self.timeout,
                           headers={"Authorization": f"Api-Key {self.api_key}", "x-folder-id": self.folder_id})
        except httpx.HTTPError as e:
            raise LLMError(f"YandexGPT: {e}") from e
        _raise_for(r, "YandexGPT")
        res = r.json()["result"]
        usage = res.get("usage") or {}
        return LLMResult(text=res["alternatives"][0]["message"]["text"], provider=self.name, model=model,
                         latency_ms=(time.perf_counter() - t0) * 1000,
                         prompt_tokens=_int(usage.get("inputTextTokens")), completion_tokens=_int(usage.get("completionTokens")))


class OllamaProvider(LLMProvider):
    """Нативный API Ollama: явный num_ctx (иначе длинный промпт молча обрезается) и format=json."""

    def __init__(self, base_url: str, models: list[str], num_ctx: int, num_predict: int, timeout: float):
        self.name, self.base_url, self.models, self.timeout = "ollama", base_url.rstrip("/"), models, timeout
        self.num_ctx, self.num_predict = num_ctx, num_predict

    def complete(self, model: str, system: str, user: str, temperature: float) -> LLMResult:
        body = {"model": model, "stream": False, "format": "json",
                "options": {"temperature": temperature, "num_ctx": self.num_ctx, "num_predict": self.num_predict, "seed": 42},
                "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}
        t0 = time.perf_counter()
        try:
            r = httpx.post(f"{self.base_url}/api/chat", json=body, timeout=self.timeout)
        except httpx.HTTPError as e:
            raise LLMError(f"Ollama: {e!r}") from e
        _raise_for(r, "Ollama")
        data = r.json()
        return LLMResult(text=data["message"]["content"], provider=self.name, model=model,
                         latency_ms=(time.perf_counter() - t0) * 1000,
                         prompt_tokens=_int(data.get("prompt_eval_count")), completion_tokens=_int(data.get("eval_count")))


def _split(s: str) -> list[str]:
    return [x.strip() for x in s.split(",") if x.strip()]


class ProviderRegistry:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.providers: dict[str, LLMProvider] = {}
        t = settings.llm_timeout_s
        if settings.gigachat_auth_key:
            verify: bool | str = settings.gigachat_ca_bundle or settings.gigachat_verify_ssl
            self.providers["gigachat"] = GigaChatProvider(settings.gigachat_auth_key, settings.gigachat_scope,
                                                          _split(settings.gigachat_models), verify, t)
        if settings.yandex_api_key and settings.yandex_folder_id:
            self.providers["yandex"] = YandexGPTProvider(settings.yandex_api_key, settings.yandex_folder_id,
                                                         _split(settings.yandex_models), t)
        if settings.ollama_base_url and _split(settings.ollama_models):
            self.providers["ollama"] = OllamaProvider(settings.ollama_base_url, _split(settings.ollama_models),
                                                      settings.ollama_num_ctx, settings.ollama_num_predict, t)
        if settings.openai_base_url and _split(settings.openai_models):
            name = settings.openai_provider_name
            self.providers[name] = OpenAICompatibleProvider(name, settings.openai_base_url, settings.openai_api_key,
                                                            _split(settings.openai_models), t)

    def register(self, provider: LLMProvider):
        self.providers[provider.name] = provider

    def model_ids(self) -> list[str]:
        return [f"{p.name}:{m}" for p in self.providers.values() for m in p.models]

    def default_model(self) -> str | None:
        ids = self.model_ids()
        if self.settings.default_model in ids:
            return self.settings.default_model
        return ids[0] if ids else None

    def resolve(self, model_id: str | None) -> tuple[LLMProvider, str]:
        model_id = model_id if model_id and model_id != "default" else self.default_model()
        if not model_id:
            raise LLMError("Не настроен ни один LLM-провайдер. Укажите ключи GigaChat, YandexGPT или "
                           "OpenAI-совместимого API в backend/.env")
        name, _, model = model_id.partition(":")
        if name not in self.providers:
            raise LLMError(f"Провайдер «{name}» не настроен")
        return self.providers[name], model


_registry: ProviderRegistry | None = None


def get_registry() -> ProviderRegistry:
    global _registry
    if _registry is None:
        _registry = ProviderRegistry(get_settings())
    return _registry
