"""Собственная БД проекта: хранение запросов, запусков анализа, планов, бенчмарков и ответов моделей.

По умолчанию SQLite (data/optimizer.db); для PostgreSQL задайте DATABASE_URL=postgresql+psycopg://...
"""

from __future__ import annotations

import datetime as dt
from typing import Any

from cryptography.fernet import Fernet
from sqlalchemy import (JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text, create_engine, event)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, sessionmaker

from app.config import DATA_DIR, get_settings


def utcnow() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)


class Base(DeclarativeBase):
    pass


class Project(Base):
    __tablename__ = "projects"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow)


class DatabaseConnection(Base):
    __tablename__ = "database_connections"
    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), default=1)
    name: Mapped[str] = mapped_column(String(200))
    dbms: Mapped[str] = mapped_column(String(32))
    host: Mapped[str] = mapped_column(String(255))
    port: Mapped[int] = mapped_column(Integer)
    database: Mapped[str] = mapped_column(String(255))
    username: Mapped[str] = mapped_column(String(255))
    password_enc: Mapped[str] = mapped_column(Text, default="")
    ssl: Mapped[bool] = mapped_column(Boolean, default=False)
    server_version: Mapped[str | None] = mapped_column(String(128))
    read_only_user: Mapped[bool | None] = mapped_column(Boolean)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow)


class Query(Base):
    __tablename__ = "queries"
    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), default=1)
    sql_text: Mapped[str] = mapped_column(Text)
    sql_hash: Mapped[str] = mapped_column(String(64), index=True)
    query_type: Mapped[str | None] = mapped_column(String(32))
    dbms: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow)


class AnalysisRun(Base):
    __tablename__ = "analysis_runs"
    id: Mapped[int] = mapped_column(primary_key=True)
    query_id: Mapped[int] = mapped_column(ForeignKey("queries.id"), index=True)
    kind: Mapped[str] = mapped_column(String(16))  # analyze / optimize / compare
    connection_id: Mapped[int | None] = mapped_column(ForeignKey("database_connections.id"))
    dbms_version: Mapped[str | None] = mapped_column(String(128))
    app_version: Mapped[str] = mapped_column(String(32))
    model_name: Mapped[str | None] = mapped_column(String(128))
    prompt_version: Mapped[str | None] = mapped_column(String(64))
    prompt_sha256: Mapped[str | None] = mapped_column(String(64))
    model_parameters: Mapped[dict | None] = mapped_column(JSON)
    started_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow)
    finished_at: Mapped[dt.datetime | None] = mapped_column(DateTime)
    verdict: Mapped[str | None] = mapped_column(String(16))
    verdict_reason: Mapped[str | None] = mapped_column(Text)
    optimization_score: Mapped[float | None] = mapped_column(Float)
    confidence: Mapped[float | None] = mapped_column(Float)
    original_time_ms: Mapped[float | None] = mapped_column(Float)
    optimized_time_ms: Mapped[float | None] = mapped_column(Float)
    speedup: Mapped[float | None] = mapped_column(Float)
    result_equivalent: Mapped[bool | None] = mapped_column(Boolean)
    error_types: Mapped[list | None] = mapped_column(JSON)
    issue_codes: Mapped[list | None] = mapped_column(JSON)
    result: Mapped[dict | None] = mapped_column(JSON)  # полный ответ API — для воспроизводимости

    query: Mapped[Query] = relationship()
    versions: Mapped[list["QueryVersion"]] = relationship(cascade="all, delete-orphan")
    plans: Mapped[list["ExecutionPlan"]] = relationship(cascade="all, delete-orphan")
    benchmarks: Mapped[list["Benchmark"]] = relationship(cascade="all, delete-orphan")
    ai_recommendations: Mapped[list["AIRecommendation"]] = relationship(cascade="all, delete-orphan")
    index_recommendations: Mapped[list["IndexRecommendation"]] = relationship(cascade="all, delete-orphan")


class QueryVersion(Base):
    __tablename__ = "query_versions"
    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("analysis_runs.id"), index=True)
    source: Mapped[str] = mapped_column(String(16))  # original / ai / rule / manual
    sql_text: Mapped[str] = mapped_column(Text)


class ExecutionPlan(Base):
    __tablename__ = "execution_plans"
    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("analysis_runs.id"), index=True)
    label: Mapped[str] = mapped_column(String(16))  # original / optimized
    total_cost: Mapped[float | None] = mapped_column(Float)
    analyzed: Mapped[bool] = mapped_column(Boolean, default=False)
    raw: Mapped[Any] = mapped_column(JSON)


class Benchmark(Base):
    __tablename__ = "benchmarks"
    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("analysis_runs.id"), index=True)
    label: Mapped[str] = mapped_column(String(16))
    runs: Mapped[int] = mapped_column(Integer)
    warmup: Mapped[int] = mapped_column(Integer)
    mean_ms: Mapped[float] = mapped_column(Float)
    median_ms: Mapped[float] = mapped_column(Float)
    min_ms: Mapped[float] = mapped_column(Float)
    max_ms: Mapped[float] = mapped_column(Float)
    stdev_ms: Mapped[float] = mapped_column(Float)
    rows_returned: Mapped[int] = mapped_column(Integer)
    rows_examined: Mapped[float | None] = mapped_column(Float)
    times_ms: Mapped[list] = mapped_column(JSON)


class AIRecommendation(Base):
    __tablename__ = "ai_recommendations"
    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("analysis_runs.id"), index=True)
    provider: Mapped[str | None] = mapped_column(String(64))
    model: Mapped[str | None] = mapped_column(String(128))
    prompt_version: Mapped[str] = mapped_column(String(64))
    system_prompt: Mapped[str] = mapped_column(Text)
    user_prompt: Mapped[str] = mapped_column(Text)
    raw_response: Mapped[str | None] = mapped_column(Text)
    parsed: Mapped[dict | None] = mapped_column(JSON)
    error: Mapped[str | None] = mapped_column(Text)
    latency_ms: Mapped[float | None] = mapped_column(Float)
    prompt_tokens: Mapped[int | None] = mapped_column(Integer)
    completion_tokens: Mapped[int | None] = mapped_column(Integer)


class IndexRecommendation(Base):
    __tablename__ = "index_recommendations"
    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("analysis_runs.id"), index=True)
    source: Mapped[str] = mapped_column(String(16))  # ai / rule
    table_name: Mapped[str] = mapped_column(String(255))
    columns: Mapped[list] = mapped_column(JSON)
    sql: Mapped[str | None] = mapped_column(Text)
    reason: Mapped[str | None] = mapped_column(Text)


# ---------------------------------------------------------------- Research Mode
class Dataset(Base):
    __tablename__ = "datasets"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    version: Mapped[str] = mapped_column(String(64))
    dbms: Mapped[str] = mapped_column(String(32))
    description: Mapped[str | None] = mapped_column(Text)
    database_seed: Mapped[str | None] = mapped_column(String(64))  # на каких данных рассчитан датасет
    builtin: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow)
    queries: Mapped[list["DatasetQuery"]] = relationship(cascade="all, delete-orphan", order_by="DatasetQuery.position")


class DatasetQuery(Base):
    __tablename__ = "dataset_queries"
    id: Mapped[int] = mapped_column(primary_key=True)
    dataset_id: Mapped[int] = mapped_column(ForeignKey("datasets.id"), index=True)
    position: Mapped[int] = mapped_column(Integer)
    key: Mapped[str] = mapped_column(String(64))
    title: Mapped[str] = mapped_column(String(255))
    category: Mapped[str] = mapped_column(String(64))
    sql_text: Mapped[str] = mapped_column(Text)


class Experiment(Base):
    __tablename__ = "experiments"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    dataset_id: Mapped[int] = mapped_column(ForeignKey("datasets.id"))
    connection_id: Mapped[int | None] = mapped_column(ForeignKey("database_connections.id"))
    models: Mapped[list] = mapped_column(JSON)
    prompt_version: Mapped[str] = mapped_column(String(64))
    prompt_sha256: Mapped[str | None] = mapped_column(String(64))
    runs: Mapped[int] = mapped_column(Integer)
    warmup: Mapped[int] = mapped_column(Integer)
    model_parameters: Mapped[dict | None] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(16), default="pending")  # pending/running/done/cancelled/failed/interrupted
    progress_done: Mapped[int] = mapped_column(Integer, default=0)
    progress_total: Mapped[int] = mapped_column(Integer, default=0)
    current_item: Mapped[str | None] = mapped_column(String(255))
    app_version: Mapped[str] = mapped_column(String(32))
    dbms: Mapped[str | None] = mapped_column(String(32))
    dbms_version: Mapped[str | None] = mapped_column(String(128))
    dataset_version: Mapped[str | None] = mapped_column(String(64))
    database_seed: Mapped[str | None] = mapped_column(String(64))
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow)
    started_at: Mapped[dt.datetime | None] = mapped_column(DateTime)
    finished_at: Mapped[dt.datetime | None] = mapped_column(DateTime)
    dataset: Mapped[Dataset] = relationship()


class ExperimentResult(Base):
    __tablename__ = "experiment_results"
    id: Mapped[int] = mapped_column(primary_key=True)
    experiment_id: Mapped[int] = mapped_column(ForeignKey("experiments.id"), index=True)
    dataset_query_id: Mapped[int] = mapped_column(ForeignKey("dataset_queries.id"))
    model: Mapped[str] = mapped_column(String(128))
    run_id: Mapped[int | None] = mapped_column(ForeignKey("analysis_runs.id"))
    outcome: Mapped[str] = mapped_column(String(16))  # improved/unchanged/worse/invalid/error
    verdict: Mapped[str | None] = mapped_column(String(16))
    proposed: Mapped[bool] = mapped_column(Boolean, default=False)  # модель предложила отличающийся запрос
    executed: Mapped[bool] = mapped_column(Boolean, default=False)  # кандидат выполнился без ошибок
    equivalent: Mapped[bool | None] = mapped_column(Boolean)
    speedup: Mapped[float | None] = mapped_column(Float)
    time_before_ms: Mapped[float | None] = mapped_column(Float)
    time_after_ms: Mapped[float | None] = mapped_column(Float)
    optimization_score: Mapped[float | None] = mapped_column(Float)
    confidence: Mapped[float | None] = mapped_column(Float)
    error_types: Mapped[list | None] = mapped_column(JSON)
    latency_ms: Mapped[float | None] = mapped_column(Float)
    prompt_tokens: Mapped[int | None] = mapped_column(Integer)
    completion_tokens: Mapped[int | None] = mapped_column(Integer)
    message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow)
    query: Mapped[DatasetQuery] = relationship()


# ---------------------------------------------------------------- engine / session
_settings = get_settings()
if _settings.database_url.startswith("sqlite"):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
engine = create_engine(_settings.database_url, future=True)
if engine.dialect.name == "sqlite":
    @event.listens_for(engine, "connect")
    def _fk_on(dbapi_conn, _):
        dbapi_conn.execute("PRAGMA foreign_keys=ON")

SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


def init_db() -> None:
    Base.metadata.create_all(engine)
    with SessionLocal() as s:
        if s.get(Project, 1) is None:
            s.add(Project(id=1, name="Default"))
            s.commit()


# ---------------------------------------------------------------- шифрование паролей
def _fernet() -> Fernet:
    key = _settings.secret_key
    if not key:
        path = DATA_DIR / "secret.key"
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            path.write_bytes(Fernet.generate_key())
        key = path.read_text().strip()
    return Fernet(key.encode() if isinstance(key, str) else key)


def encrypt(value: str) -> str:
    return _fernet().encrypt(value.encode()).decode() if value else ""


def decrypt(value: str) -> str:
    return _fernet().decrypt(value.encode()).decode() if value else ""
