"""Конфигурация приложения. Все значения читаются из переменных окружения / файла .env."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BACKEND_DIR / "data"
PROMPTS_DIR = Path(__file__).resolve().parent / "services" / "ai" / "prompts"
SCORING_CONFIG = BACKEND_DIR / "config" / "scoring.json"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=BACKEND_DIR / ".env", env_file_encoding="utf-8", extra="ignore")

    # Хранилище результатов (собственная БД проекта). По умолчанию SQLite, для продакшена — PostgreSQL.
    database_url: str = f"sqlite:///{(DATA_DIR / 'optimizer.db').as_posix()}"
    # Ключ шифрования паролей подключений (Fernet). Если не задан — создаётся в data/secret.key.
    secret_key: str | None = None

    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    # Запуск в Docker: собранный интерфейс (frontend/dist), который сервер раздаёт сам, и адрес компьютера
    # пользователя, на который перенаправляются подключения к localhost
    frontend_dir: str | None = None
    localhost_alias: str | None = None

    # --- LLM-провайдеры (все необязательные; доступны те, что настроены) ---
    default_model: str | None = None  # id модели из /api/models, напр. "gigachat:GigaChat-2-Max"

    gigachat_auth_key: str | None = None  # «Authorization key» из личного кабинета Sber Developers
    gigachat_scope: str = "GIGACHAT_API_PERS"
    gigachat_models: str = "GigaChat-2,GigaChat-2-Pro,GigaChat-2-Max"
    gigachat_ca_bundle: str | None = None  # путь к russian_trusted_root_ca.cer
    gigachat_verify_ssl: bool = True

    yandex_api_key: str | None = None
    yandex_folder_id: str | None = None
    yandex_models: str = "yandexgpt/latest,yandexgpt-lite/latest"

    openai_base_url: str | None = None  # DeepSeek, OpenRouter, Ollama, LM Studio, vLLM и т.д.
    openai_api_key: str | None = None
    openai_models: str = ""
    openai_provider_name: str = "openai-compatible"

    # Ollama (локальные модели) через нативный API: позволяет задать размер контекста и JSON-режим
    ollama_base_url: str | None = None  # напр. http://127.0.0.1:11434
    ollama_models: str = ""
    ollama_num_ctx: int = 8192
    ollama_num_predict: int = 1500  # предел длины ответа: защита от зацикливания генерации

    llm_temperature: float = 0.1
    llm_timeout_s: float = 120.0

    # --- Выполнение запросов ---
    query_timeout_ms: int = 30000
    benchmark_warmup: int = 2
    benchmark_runs: int = 5


@lru_cache
def get_settings() -> Settings:
    return Settings()


def load_scoring_config() -> dict[str, dict[str, float]]:
    with open(SCORING_CONFIG, encoding="utf-8") as f:
        cfg = json.load(f)
    return {"weights": cfg["weights"], "confidence_weights": cfg["confidence_weights"]}
