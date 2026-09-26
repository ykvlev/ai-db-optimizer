# AI Database Optimizer

Интеллектуальная система анализа и оптимизации SQL-запросов в реляционных БД с использованием методов ИИ.

Система не просто «переписывает SQL через нейросеть»: ИИ — один компонент конвейера
**SQL Parser → Schema → Execution Plan → Rule Engine → AI → Safety → Validation → Equivalence → Benchmark → Score → Dataset**.
Любое улучшение подтверждается измерениями на реальной БД; без подключения система не показывает ни времени, ни ускорения.

## Возможности (MVP 1 + MVP 2 + MVP 3)

| Модуль | Что делает | Файл |
|---|---|---|
| SQL Parser | AST (sqlglot): тип, таблицы, JOIN, WHERE, GROUP/ORDER BY, CTE, подзапросы (в т.ч. коррелированные), агрегаты, функции | `backend/app/services/sql_parser.py` |
| Schema Analyzer | схема из DDL (офлайн) или из живой БД: колонки, типы, индексы, PK/FK, число строк, размер | `schema_ddl.py`, `connectors.py` |
| Rule Engine | 16 детерминированных правил: функция над колонкой, LIKE '%…', OR по разным колонкам, NOT IN, коррелированные подзапросы, несовпадение типов, отсутствующий индекс, сортировка без индекса, большой OFFSET, декартово произведение, `= NULL`, ORDER BY RAND(), SELECT * … | `rules.py` |
| Rule-based rewriter | безопасные эквивалентные преобразования без ИИ (YEAR/DATE/EXTRACT → диапазон) — baseline для экспериментов | `rewriter.py` |
| Execution Plan Analyzer | MySQL `EXPLAIN FORMAT=JSON`, PostgreSQL `EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)` → единое дерево; full scan, filesort, temporary, nested loop, ошибка оценки строк | `explain.py` |
| AI-модуль | структурированный JSON-контекст, версионируемые промпты, строгий JSON-ответ, провайдеры GigaChat / YandexGPT / OpenAI-совместимые | `services/ai/` |
| Safety Engine | только один read-only SELECT; блокирует DML/DDL, `SELECT … INTO`, `FOR UPDATE`, опасные функции, executable-комментарии, модифицирующие CTE | `safety.py` |
| Валидация ответа ИИ | SYNTAX_ERROR, WRONG_TABLE, WRONG_COLUMN, INDEX_HALLUCINATION, SCHEMA_HALLUCINATION, DANGEROUS_QUERY, INVALID_RESPONSE — до выполнения | `ai/optimizer.py` |
| Equivalence | мультимножество строк (checksum), число колонок, порядок при ORDER BY; при расхождении — `REJECT` и примеры отличающихся строк | `benchmark.py` |
| Benchmark | прогрев + N прогонов, чередование исходного и нового запроса; медиана/среднее/min/max/σ, rows examined (MySQL Handler_read_*, PG из ANALYZE), буферы | `benchmark.py` |
| Score и Confidence | Optimization Score 0–100 (веса в `backend/config/scoring.json`), AI Confidence из измеренных факторов, а не из самооценки модели | `scoring.py` |
| Хранилище | запросы, версии, запуски, планы, бенчмарки, промпты и сырые ответы моделей, рекомендации индексов; экспорт CSV/XLSX/JSON | `db.py`, `main.py` |
| Research Mode | датасеты запросов, фоновые эксперименты «датасет × модели», сравнение моделей, базовая линия без ИИ, продолжение прерванных экспериментов | `backend/app/research/` |
| Научный отчёт | параметры воспроизводимости, сводная таблица моделей, bootstrap-ДИ медианы ускорения, разбивка по категориям, типы ошибок, методика; HTML (печать в PDF), Markdown, CSV/XLSX/JSON | `research/report.py` |
| Веб-интерфейс | Dashboard, SQL Analyzer (Monaco), сравнение ORIGINAL/OPTIMIZED, эксперименты, Database Explorer, история | `frontend/` |

Все запросы к анализируемой БД выполняются в `READ ONLY` транзакции с таймаутом. Рекомендуется пользователь только с правом SELECT: система проверяет права и предупреждает, если их больше. Индексы не создаются автоматически.

## Быстрый старт

Нужны: Python 3.11+, Node.js 20+, Docker (для тестовых БД).

```bash
# 1. Тестовые БД (MySQL 8.4 :3307 и PostgreSQL 16 :5434, база shop, пользователь optimizer_ro/optimizer_ro)
docker compose -f docker/docker-compose.yml up -d

# 2. Backend
cd backend
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
copy .env.example .env        # и при желании указать ключи LLM
.venv\Scripts\python -m uvicorn app.main:app --port 8000

# 3. Frontend
cd frontend
npm install
npm run dev                   # http://localhost:5173
```

API-документация: http://localhost:8000/docs

В разделе «Базы данных» есть кнопки-пресеты для демо-MySQL и демо-PostgreSQL.

## LLM-провайдеры, работающие в России

| Провайдер | Настройка в `backend/.env` | id модели |
|---|---|---|
| GigaChat (Сбер) | `GIGACHAT_AUTH_KEY`, при ошибке SSL — `GIGACHAT_CA_BUNDLE` (сертификат НУЦ Минцифры) | `gigachat:GigaChat-2-Max` |
| YandexGPT | `YANDEX_API_KEY`, `YANDEX_FOLDER_ID` | `yandex:yandexgpt/latest` |
| DeepSeek / OpenRouter / Ollama / LM Studio | `OPENAI_BASE_URL`, `OPENAI_API_KEY`, `OPENAI_MODELS`, `OPENAI_PROVIDER_NAME` | `<provider>:<model>` |

Новый провайдер добавляется подклассом `LLMProvider` (`backend/app/services/ai/providers.py`).
Промпты хранятся как файлы `backend/app/services/ai/prompts/<id>.json`. Для каждого запуска в БД сохраняются id промпта, его SHA-256, полный текст промпта и сырой ответ модели.

## Research Mode

Раздел «Эксперименты» в интерфейсе или `POST /api/experiments`:

1. Выберите подключение, датасет и модели. Встроенные датасеты: `shop-bench-v1` (40 запросов: 15 категорий антипаттернов и контрольная группа уже оптимальных запросов) и `shop-bench-mini-v1` (по одному запросу на категорию). Свои датасеты импортируются списком SELECT-запросов.
2. Для каждой пары «запрос × модель» выполняется полный конвейер: анализ → кандидат → проверки → эквивалентность → бенчмарк. Модели идут во внутреннем цикле, поэтому кандидаты для одного запроса измеряются в близкое время.
3. `baseline:rule-based` — детерминированная базовая линия без ИИ, проходит те же проверки. С ней сравниваются LLM.
4. Исходы: **Улучшено** (результат совпал, ускорение ≥ 1,05x), **Без изменений**, **Ухудшено** (результат совпал, но медленнее более чем на 5%), **Некорректно** (синтаксис, схема, безопасность, изменение результата), **Сбой вызова** (инфраструктура LLM, не считается ошибкой модели).
5. Отчёт: `GET /api/experiments/{id}/report` (HTML, печать в PDF), `/report.md`, `/export?format=csv|xlsx|json`.

Для каждого эксперимента сохраняются: experiment_id, dataset_version, database_seed, application_version, модели и их параметры, prompt_version и SHA-256 промпта, версия СУБД, время начала и окончания.

Не запускайте два эксперимента одновременно и не нагружайте машину во время прогона: бенчмарк измеряет реальное время.

## Тесты

```bash
cd backend
.venv\Scripts\python -m pytest -q                 # unit + интеграционные (интеграционные пропускаются без docker)
.venv\Scripts\python scripts\smoke_test.py        # прогон демо-запросов через запущенный API
```

Интеграционные тесты проверяют полный AI-цикл на обеих СУБД с подставной моделью:
корректная оптимизация принимается, изменение результата отклоняется (`RESULT_CHANGED`),
выдуманная колонка отклоняется до выполнения (`WRONG_COLUMN`).

## Первые измерения (демо-БД, rule-based rewriter, без ИИ)

Медиана прогонов, время на клиенте. Данные детерминированы (seed v1): 100 тыс. пользователей, 500 тыс. заказов, 1,5 млн позиций.

| Запрос | СУБД | До | После | Ускорение | Просмотрено строк | Результат |
|---|---|---|---|---|---|---|
| `DATE(created_at) = '2025-03-15'` | MySQL 8.4 | 89 мс | 2,7 мс | 33x | 500 002 → 204 | совпал |
| `YEAR(created_at) = 2024 … LIMIT 50` | MySQL 8.4 | 197 мс | 3,5 мс | 56x | 128 261 → 142 | совпал |
| `DATE(created_at) = …` | PostgreSQL 16 | 58 мс | 4,8 мс | 12x | 500 001 → 203 | совпал |
| `EXTRACT(YEAR …) = 2024 … LIMIT 50` | PostgreSQL 16 | 39 мс | 4,5 мс | 8,8x | 128 260 → 142 | совпал |
| отчёт по категориям, `YEAR(o.created_at) = 2025` | MySQL 8.4 | 140 мс | 185 мс | **0,76x** | 525 980 → 100 204 | совпал |
| то же | PostgreSQL 16 | 83 мс | 169 мс | **0,49x** | 522 267 → 91 359 | совпал |

Последние две строки показывают, зачем нужна проверка измерением. Переписывание стало «sargable», и строк просматривается в 5 раз меньше, но оптимизатор выбрал худший план соединения, и запрос замедлился. Система фиксирует это как регресс и не засчитывает как улучшение.

## Эксперименты 1–2: базовая линия на shop-bench-v1

40 запросов, прогрев 2, прогонов 5. Отчёты: `/api/experiments/1/report` (MySQL), `/api/experiments/2/report` (PostgreSQL).

| | MySQL 8.4 | PostgreSQL 16 |
|---|---|---|
| Улучшено / без изменений / ухудшено / некорректно | 7 / 29 / 4 / 0 | 9 / 29 / 2 / 0 |
| Предложено изменений | 11 из 40 | 11 из 40 |
| Медиана ускорения (95% bootstrap-ДИ) | 33,6x (0,93–37,2x) | 11,5x (4,2–16,1x) |
| Геометрическое среднее ускорения | 10,3x | 6,3x |
| Максимальное ускорение | 106x | 24,9x |
| Контрольная группа (оптимальные запросы) | не затронута | не затронута |

Одно и то же эквивалентное преобразование `YEAR(created_at) = N` → диапазон дат в агрегирующем запросе ускоряет PostgreSQL в 4,2–4,6 раза, а MySQL замедляет (0,85–0,95x). Для отчёта с JOIN замедление на обеих СУБД (0,5–0,9x). Правило, «правильное» по учебнику, не универсально: без измерения на конкретной СУБД его применять нельзя.

## Структура

```
backend/
  app/
    main.py              HTTP API (FastAPI)
    models.py            доменные модели (Pydantic)
    db.py                хранилище результатов (SQLAlchemy)
    services/
      sql_parser.py  rules.py  rewriter.py  safety.py  schema_ddl.py
      connectors.py  explain.py  benchmark.py  scoring.py  pipeline.py
      ai/  providers.py  optimizer.py  prompts/optimizer-v1.json
  config/scoring.json    веса Optimization Score и AI Confidence
  tests/                 unit и интеграционные тесты
  scripts/smoke_test.py
frontend/                React + TypeScript + Vite + Tailwind + Monaco
docker/                  MySQL 8.4 и PostgreSQL 16 с демо-БД shop
```

## Ограничения текущей версии

- Эквивалентность проверяется эмпирически, на текущих данных, а не формально. Если ключ ORDER BY не уникален, различие в порядке строк выдаётся как предупреждение.
- Время измеряется на клиенте и включает передачу результата по сети.
- Рекомендованные индексы не применяются: бенчмарк отражает текущую схему. Проверку через гипотетические индексы (HypoPG) можно добавить позже.
- Research Mode (массовые эксперименты, сравнение моделей, автоотчёты) — это MVP 3. Данные для него уже сохраняются и выгружаются.

## Лицензия

MIT — см. [LICENSE](LICENSE).
