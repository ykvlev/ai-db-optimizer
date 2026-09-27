"""Аудит структуры базы: целостность, индексы, типы данных, статистика планировщика.

Каждое замечание объясняет, почему это плохо и что изменится после исправления. Исправление предлагается
только проверенное на данных (например, первичный ключ — если значения действительно уникальны). Оценка
считается по направлениям как доля таблиц без проблем, поэтому не зависит от размера базы.

Применение исправлений — отдельное действие: пользователь вводит учётные данные с правом на изменение
(они не сохраняются), сервер заново проводит аудит и выполняет только собственные исправления по их
идентификаторам — произвольный SQL через этот путь выполнить нельзя.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import asdict, dataclass, replace

from app.config import get_settings
from app.models import Dialect, SchemaInfo, TableInfo
from app.services.connectors import ConnectionConfig, Connector, DBError

CATEGORIES = {
    "integrity": ("Целостность данных", 0.35,
                  "Первичные и внешние ключи не дают появиться дублям и ссылкам на несуществующие записи."),
    "indexes": ("Индексы", 0.30,
                "Нужные индексы ускоряют поиск и соединения таблиц, лишние — замедляют запись и занимают место."),
    "types": ("Типы данных", 0.20,
              "Правильный тип — это верные сравнения и сортировка, проверка значений и меньше места на диске."),
    "stats": ("Статистика планировщика", 0.15,
              "По статистике СУБД оценивает число строк и выбирает план запроса."),
}
WEIGHT = {"high": 1.0, "medium": 0.5, "low": 0.15}
DATA_CHECK_MAX_ROWS = 2_000_000  # проверки на данных — только для таблиц разумного размера

_DATE_NAME = re.compile(r"(^|_)(date|dt|data|time|created|updated|deleted|birth|дата)(_|$)|_(at|on)$|^data_", re.I)
_MONEY_NAME = re.compile(r"(price|amount|cost|sum|total|salary|balance|fee|oklad|summa|stoimost|tsena|стоимость|цена|сумма)", re.I)
_TEXT_TYPE = re.compile(r"^(VARCHAR|CHARACTER VARYING|CHAR|CHARACTER|TEXT|TINYTEXT|MEDIUMTEXT|NVARCHAR)", re.I)
_FLOAT_TYPE = re.compile(r"^(FLOAT|DOUBLE|REAL)", re.I)
_INT_TYPE = re.compile(r"^(INT|INTEGER|BIGINT|SMALLINT|MEDIUMINT|TINYINT|SERIAL|BIGSERIAL|NUMERIC\(\d+,\s*0\)|DECIMAL\(\d+,\s*0\))", re.I)


@dataclass
class Finding:
    id: str
    code: str
    category: str
    severity: str  # high | medium | low
    table: str
    title: str
    why: str       # почему это плохо
    effect: str    # что изменится после исправления
    fix_sql: str | None = None
    fix_kind: str = "manual"  # safe — проверено на данных; check — стоит проверить; manual — только рекомендация
    note: str | None = None


def _q(name: str, dialect: Dialect) -> str:
    q = "`" if dialect == "mysql" else '"'
    return ".".join(q + p.replace(q, q * 2) + q for p in name.split("."))


def _short(name: str) -> str:
    return name.split(".")[-1]


def _mk(code, category, severity, table, title, why, effect, fix=None, kind="manual", note=None, key="") -> Finding:
    fid = hashlib.sha1(f"{code}|{table}|{key}".encode()).hexdigest()[:12]
    return Finding(fid, code, category, severity, table, title, why, effect, fix, kind if fix else "manual", note)


def _scalar_row(conn: Connector, sql: str) -> tuple | None:
    try:
        rows = conn._query(sql)  # noqa: SLF001 — внутренний read-only запрос коннектора
        return rows[0] if rows else None
    except DBError:
        return None


def _checkable(t: TableInfo) -> bool:
    return (t.row_count or 0) <= DATA_CHECK_MAX_ROWS


# ---------------------------------------------------------------- проверки
def _primary_key(conn, dialect, t: TableInfo) -> Finding | None:
    if any(i.primary for i in t.indexes):
        return None
    tn, short = _q(t.name, dialect), _short(t.name).lower()
    names = [c.name for c in t.columns]
    candidates = [c for c in names if c.lower() in ("id", f"{short}_id", f"id_{short}", "kod", "code", "nomer")]
    candidates += [c for c in names if c not in candidates and re.match(r"^(id|kod|code)(_|$)", c, re.I)]
    why = ("Без первичного ключа в таблице могут появиться полностью одинаковые строки, их нельзя однозначно изменить "
           "или удалить, на таблицу нельзя сослаться внешним ключом.")
    for col in candidates[:3]:
        if not _checkable(t):
            break
        r = _scalar_row(conn, f"SELECT count(*), count(DISTINCT {_q(col, dialect)}), count({_q(col, dialect)}) FROM {tn}")
        if r and r[0] == r[1] == r[2]:
            return _mk("NO_PRIMARY_KEY", "integrity", "high", t.name, "Нет первичного ключа", why,
                       f"Столбец {col} станет первичным ключом: СУБД будет следить за уникальностью, появится индекс "
                       "для быстрого поиска по нему.",
                       f"ALTER TABLE {tn} ADD PRIMARY KEY ({_q(col, dialect)});", "safe",
                       f"Проверено: все {r[0]} значений {col} уникальны и заполнены.", key=col)
    return _mk("NO_PRIMARY_KEY", "integrity", "high", t.name, "Нет первичного ключа", why,
               "Добавьте столбец-идентификатор (например, id с автоувеличением) и объявите его первичным ключом.",
               note="Подходящего столбца с уникальными значениями не найдено — нужно решение разработчика.")


def _ref_candidates(col: str) -> list[str]:
    c = col.lower()
    out = []
    for pat in (r"^(.+)_id$", r"^id_(.+)$", r"^kod_(.+)$", r"^(.+)_kod$", r"^(.+)_code$", r"^code_(.+)$", r"^(.+)id$"):
        m = re.match(pat, c)
        if m and m.group(1) not in ("", "_"):
            out.append(m.group(1).strip("_"))
    return out


def _missing_fks(conn, dialect, t: TableInfo, schema: SchemaInfo) -> list[Finding]:
    """Столбцы вида user_id / kod_user без внешнего ключа, хотя есть таблица, на которую они явно ссылаются."""
    out = []
    prefix = t.name.rsplit(".", 1)[0] + "." if "." in t.name else ""
    fk_cols = {c for f in t.foreign_keys for c in f.columns}
    pk_cols = {c for i in t.indexes if i.primary for c in i.columns}
    for col in t.columns:
        if col.name in fk_cols or col.name in pk_cols or not _INT_TYPE.match(col.type):
            continue
        for ref in _ref_candidates(col.name):
            target = next((r for r in schema.tables if r is not t and r.name.lower() in
                           {f"{prefix}{ref}", f"{prefix}{ref}s", f"{prefix}{ref}es"}), None)
            if not target:
                continue
            pk = next((i for i in target.indexes if i.primary and len(i.columns) == 1), None)
            if not pk:
                continue
            tn, rn, c, p = _q(t.name, dialect), _q(target.name, dialect), _q(col.name, dialect), _q(pk.columns[0], dialect)
            why = (f"Столбец {col.name} по смыслу ссылается на {_short(target.name)}, но связь не объявлена: СУБД позволит "
                   f"записать номер несуществующей записи или удалить запись из {_short(target.name)}, оставив «висячие» ссылки.")
            effect = f"СУБД будет проверять, что каждое значение {col.name} есть в {_short(target.name)}.{pk.columns[0]}."
            fix = f"ALTER TABLE {tn} ADD CONSTRAINT {_q('fk_' + _short(t.name) + '_' + col.name, dialect)} FOREIGN KEY ({c}) REFERENCES {rn} ({p});"
            orphans = _scalar_row(conn, f"SELECT count(*) FROM {tn} x WHERE x.{c} IS NOT NULL AND NOT EXISTS "
                                        f"(SELECT 1 FROM {rn} y WHERE y.{p} = x.{c})") if _checkable(t) else None
            if orphans and orphans[0] == 0:
                out.append(_mk("MISSING_FOREIGN_KEY", "integrity", "medium", t.name,
                               f"Связь {col.name} → {_short(target.name)} не объявлена", why, effect, fix, "safe",
                               "Проверено: все значения ссылаются на существующие записи.", key=col.name))
            else:
                n = orphans[0] if orphans else None
                out.append(_mk("MISSING_FOREIGN_KEY", "integrity", "medium", t.name,
                               f"Связь {col.name} → {_short(target.name)} не объявлена", why, effect,
                               note=(f"{n} строк ссылаются на несуществующие записи — сначала исправьте данные."
                                     if n else "Проверить данные не удалось."), key=col.name))
            break
    return out


def _fk_indexes(dialect, t: TableInfo) -> list[Finding]:
    out = []
    rows = t.row_count or 0
    for fk in t.foreign_keys:
        n = len(fk.columns)
        if any([c.lower() for c in i.columns[:n]] == [c.lower() for c in fk.columns] for i in t.indexes):
            continue
        sev = "high" if rows >= 10_000 else "medium" if rows >= 1_000 else "low"
        cols = ", ".join(_q(c, dialect) for c in fk.columns)
        out.append(_mk(
            "FK_WITHOUT_INDEX", "indexes", sev, t.name, f"Внешний ключ ({', '.join(fk.columns)}) без индекса",
            f"Соединение {_short(t.name)} с {_short(fk.ref_table)} и удаление записей из {_short(fk.ref_table)} заставляют "
            f"СУБД читать {_short(t.name)} целиком" + (" — пока таблица маленькая, это незаметно." if sev == "low" else "."),
            "Поиск строк по этому столбцу пойдёт через индекс, соединения и проверки ключа ускорятся.",
            f"CREATE INDEX {_q('idx_' + _short(t.name) + '_' + '_'.join(fk.columns), dialect)} ON {_q(t.name, dialect)} ({cols});",
            "safe", key=",".join(fk.columns)))
    return out


def _redundant_indexes(dialect, t: TableInfo) -> list[Finding]:
    out = []
    for a in t.indexes:
        if a.primary or a.unique:
            continue
        for b in t.indexes:
            ca, cb = [c.lower() for c in a.columns], [c.lower() for c in b.columns]
            if a is b or ca != cb[:len(ca)] or not (len(ca) < len(cb) or b.primary or b.unique or b.name < a.name):
                continue
            drop = (f"DROP INDEX {_q(a.name, dialect)} ON {_q(t.name, dialect)};" if dialect == "mysql"
                    else f"DROP INDEX {_q('.'.join(t.name.split('.')[:-1] + [a.name]), dialect)};")
            out.append(_mk("REDUNDANT_INDEX", "indexes", "medium", t.name, f"Лишний индекс {a.name}",
                           f"Индекс {a.name} ({', '.join(a.columns)}) полностью повторяет начало индекса {b.name} "
                           f"({', '.join(b.columns)}): любой поиск, который он ускоряет, ускорит и {b.name}.",
                           "Вставка и изменение строк станут чуть быстрее, освободится место. Поиск не замедлится.",
                           drop, "safe", key=a.name))
            break
    return out


def _date_as_text(conn, dialect, t: TableInfo) -> list[Finding]:
    out = []
    for c in t.columns:
        if not (_DATE_NAME.search(c.name) and _TEXT_TYPE.match(c.type)):
            continue
        tn, cn = _q(t.name, dialect), _q(c.name, dialect)
        why = ("Дата хранится строкой: сравнение и сортировка идут по буквам ('10.01.2024' < '9.01.2024'), можно записать "
               "'31.02.2024' или 'вчера', функции дат требуют преобразования, индекс по диапазону дат не работает.")
        effect = "Столбец станет датой: СУБД будет проверять значения, сортировка и отбор по периоду заработают правильно."
        fix, kind, note = None, "manual", None
        if _checkable(t):
            rx = "~" if dialect == "postgres" else "REGEXP"
            r = _scalar_row(conn, (
                f"SELECT count({cn}), "
                f"sum(CASE WHEN {cn} {rx} '^[0-9]{{4}}-[0-9]{{2}}-[0-9]{{2}}$' THEN 1 ELSE 0 END), "
                f"sum(CASE WHEN {cn} {rx} '^[0-9]{{4}}-[0-9]{{2}}-[0-9]{{2}}[ T][0-9]{{2}}:[0-9]{{2}}(:[0-9]{{2}}([.][0-9]+)?)?"
                f"(Z|[+-][0-9]{{2}}(:?[0-9]{{2}})?)?$' THEN 1 ELSE 0 END), "
                f"sum(CASE WHEN {cn} {rx} '^[0-9]{{2}}\\.[0-9]{{2}}\\.[0-9]{{4}}$' THEN 1 ELSE 0 END) FROM {tn}"))
            if r:
                total, iso_d, iso_dt, ru = (int(x or 0) for x in r)
                if total == 0 or iso_d == total:
                    kind = "safe"
                    note = ("Столбец пока пуст — тип можно сменить без риска." if total == 0
                            else f"Проверено: все {total} значений в формате ГГГГ-ММ-ДД.")
                    fix = (f"ALTER TABLE {tn} ALTER COLUMN {cn} TYPE date USING {cn}::date;" if dialect == "postgres"
                           else f"ALTER TABLE {tn} MODIFY {cn} DATE;")
                elif iso_d + iso_dt == total:
                    kind, note = "safe", f"Проверено: все {total} значений — дата и время в формате ГГГГ-ММ-ДД ЧЧ:ММ."
                    fix = (f"ALTER TABLE {tn} ALTER COLUMN {cn} TYPE timestamptz USING {cn}::timestamptz;" if dialect == "postgres"
                           else f"ALTER TABLE {tn} MODIFY {cn} DATETIME;")
                elif ru == total and dialect == "postgres":
                    kind, note = "safe", f"Проверено: все {total} значений в формате ДД.ММ.ГГГГ."
                    fix = f"ALTER TABLE {tn} ALTER COLUMN {cn} TYPE date USING to_date({cn}, 'DD.MM.YYYY');"
                else:
                    bad = total - max(iso_d + iso_dt, ru)
                    note = f"{bad} из {total} значений не похожи на дату одного формата — сначала приведите данные к одному виду."
        out.append(_mk("DATE_AS_TEXT", "types", "medium", t.name, f"Дата в текстовом столбце {c.name}", why, effect,
                       fix, kind, note, key=c.name))
    return out


def _money_as_float(conn, dialect, t: TableInfo) -> list[Finding]:
    out = []
    for c in t.columns:
        if not (_MONEY_NAME.search(c.name) and _FLOAT_TYPE.match(c.type)):
            continue
        tn, cn = _q(t.name, dialect), _q(c.name, dialect)
        fix = (f"ALTER TABLE {tn} ALTER COLUMN {cn} TYPE numeric(14,2);" if dialect == "postgres"
               else f"ALTER TABLE {tn} MODIFY {cn} DECIMAL(14,2);")
        r = _scalar_row(conn, f"SELECT max(abs({cn})) FROM {tn}") if _checkable(t) else None
        ok = r is not None and (r[0] is None or float(r[0]) < 1e12)
        out.append(_mk("MONEY_AS_FLOAT", "types", "medium", t.name, f"Денежная сумма {c.name} в типе {c.type.lower()}",
                       "Числа с плавающей точкой хранят суммы приближённо: 0,1 + 0,2 даёт 0,30000000000000004, "
                       "итоги по копейкам расходятся.",
                       "Суммы будут храниться точно, до копейки.", fix if ok else None, "check",
                       "Значения округлятся до двух знаков после запятой." if ok else "Проверить диапазон значений не удалось.",
                       key=c.name))
    return out


# ---------------------------------------------------------------- аудит и оценка
def run(conn: Connector, dialect: Dialect, schema: SchemaInfo) -> dict:
    findings: list[Finding] = []
    for t in schema.tables:
        pk = _primary_key(conn, dialect, t)
        if pk:
            findings.append(pk)
        findings += _missing_fks(conn, dialect, t, schema)
        findings += _fk_indexes(dialect, t)
        findings += _redundant_indexes(dialect, t)
        findings += _date_as_text(conn, dialect, t)
        findings += _money_as_float(conn, dialect, t)
        if len(t.indexes) > 8:
            findings.append(_mk("TOO_MANY_INDEXES", "indexes", "low", t.name, f"{len(t.indexes)} индексов на одной таблице",
                                "Каждый индекс обновляется при каждой вставке и изменении строки.",
                                "Проверьте, все ли индексы используются (раздел «Медленные запросы» и статистика)."))
    names = {t.name for t in schema.tables}
    rows = {t.name: t.row_count or 0 for t in schema.tables}
    usage = conn.index_usage()
    for table, index in usage or []:
        if table in names and rows[table] >= 10_000:
            drop = (f"DROP INDEX {_q(index, dialect)} ON {_q(table, dialect)};" if dialect == "mysql"
                    else f"DROP INDEX {_q('.'.join(table.split('.')[:-1] + [index]), dialect)};")
            findings.append(_mk("UNUSED_INDEX", "indexes", "low", table, f"Индекс {index} ни разу не использовался",
                                "С момента запуска сервера или сброса статистики к индексу не было ни одного обращения, "
                                "а обновляется он при каждой записи.",
                                "Запись станет быстрее. Удаляйте, только если статистика собрана за обычный период работы.",
                                drop, "check", key=index))
    for table in conn.never_analyzed():
        if table in names and rows[table] >= 1_000:  # маленькие таблицы PostgreSQL сам не анализирует — это нормально
            findings.append(_mk("NO_STATISTICS", "stats", "medium", table, "У планировщика нет статистики",
                                f"В таблице ~{rows[table]} строк, но ANALYZE по ней не выполнялся: СУБД не знает, сколько "
                                "строк вернёт условие, и может выбрать медленный план.",
                                "Оценки числа строк станут точными, планы запросов — лучше.",
                                f"ANALYZE {_q(table, dialect)};", "safe"))

    n = max(len(schema.tables), 1)
    cats = {}
    for key, (title, weight, about) in CATEGORIES.items():
        per_table: dict[str, float] = {}
        for f in findings:
            if f.category == key:
                per_table[f.table] = min(1.0, per_table.get(f.table, 0) + WEIGHT[f.severity])
        score = round(100 * (1 - sum(per_table.values()) / n))
        cats[key] = {"title": title, "weight": weight, "about": about, "score": score,
                     "issues": sum(1 for f in findings if f.category == key), "tables_affected": len(per_table)}
    total = round(sum(c["score"] * c["weight"] for c in cats.values()))
    verdict = ("отлично" if total >= 85 else "хорошо" if total >= 70 else "есть что улучшить" if total >= 50
               else "требует внимания")
    order = {"high": 0, "medium": 1, "low": 2}
    findings.sort(key=lambda f: (list(CATEGORIES).index(f.category), order[f.severity], f.table))
    return {
        "score": total, "verdict": verdict, "tables": len(schema.tables), "categories": cats,
        "findings": [asdict(f) for f in findings],
        "counts": {s: sum(1 for f in findings if f.severity == s) for s in ("high", "medium", "low")},
        "fixable": sum(1 for f in findings if f.fix_sql),
        "usage_stats": usage is not None,
        "how": ("Оценка — взвешенное среднее четырёх направлений: целостность 35 %, индексы 30 %, типы данных 20 %, "
                "статистика 15 %. В каждом направлении считается, какая доля таблиц обходится без проблем: серьёзная "
                "проблема «съедает» таблицу целиком, средняя — наполовину, мелкая — на 15 %."),
    }


# ---------------------------------------------------------------- применение исправлений
_ERROR_HINTS = (("must be owner", "нужен владелец таблицы — войдите под пользователем, который её создал"),
                ("permission denied", "у пользователя нет прав на изменение структуры"),
                ("command denied", "у пользователя нет прав на изменение структуры"),
                ("could not create unique index", "значения повторяются — данные изменились после аудита"),
                ("violates foreign key", "появились ссылки на несуществующие записи — данные изменились после аудита"))


def _explain_error(msg: str) -> str:
    first = msg.strip().split("\n")[0]
    hint = next((h for k, h in _ERROR_HINTS if k in first.lower()), None)
    return f"{first} ({hint})" if hint else first
def apply(cfg: ConnectionConfig, dialect: Dialect, fixes: list[dict], username: str, password: str) -> dict:
    """Выполняет исправления от имени пользователя с правами на изменение. PostgreSQL — одной транзакцией
    (ошибка → откат всего), MySQL — по одному (DDL в MySQL фиксируется сразу), до первой ошибки."""
    alias = get_settings().localhost_alias
    host = alias if alias and cfg.host in ("localhost", "127.0.0.1", "::1") else cfg.host
    cfg = replace(cfg, host=host, username=username, password=password)
    results = []
    if dialect == "postgres":
        import psycopg
        try:
            conn = psycopg.connect(host=cfg.host, port=cfg.port, dbname=cfg.database, user=cfg.username,
                                   password=cfg.password, connect_timeout=10, sslmode="require" if cfg.ssl else "prefer")
        except Exception as e:  # noqa: BLE001
            raise DBError(f"Не удалось подключиться: {e}") from e
        with conn:
            cur = conn.cursor()
            cur.execute("SET statement_timeout = '300s'")
            try:
                for f in fixes:
                    cur.execute(f["fix_sql"])
                    results.append({"id": f["id"], "ok": True, "error": None})
                conn.commit()
            except Exception as e:  # noqa: BLE001
                conn.rollback()
                failed = fixes[len(results)]
                results = [{"id": r["id"], "ok": False, "error": "отменено — транзакция откатана"} for r in results]
                results.append({"id": failed["id"], "ok": False, "error": _explain_error(str(e))})
                return {"applied": 0, "failed": 1, "rolled_back": True, "results": results}
        return {"applied": len(results), "failed": 0, "rolled_back": False, "results": results}

    import pymysql
    try:
        conn = pymysql.connect(host=cfg.host, port=cfg.port, user=cfg.username, password=cfg.password,
                               database=cfg.database, connect_timeout=10, autocommit=True)
    except Exception as e:  # noqa: BLE001
        raise DBError(f"Не удалось подключиться: {e}") from e
    applied = 0
    try:
        with conn.cursor() as cur:
            for f in fixes:
                try:
                    cur.execute(f["fix_sql"])
                    applied += 1
                    results.append({"id": f["id"], "ok": True, "error": None})
                except Exception as e:  # noqa: BLE001
                    results.append({"id": f["id"], "ok": False, "error": _explain_error(str(e))})
                    break
    finally:
        conn.close()
    return {"applied": applied, "failed": len(fixes) - applied, "rolled_back": False, "results": results}


EXPLAIN_SYSTEM = """Ты — опытный администратор баз данных и наставник. Тебе даны результаты аудита структуры базы
(оценки по направлениям и замечания). Объясни их человеку простым русским языком, без канцелярита.

Ответь строго JSON:
{"summary": "3–4 предложения: общее состояние базы и главное, что стоит сделать",
 "good": ["что в базе сделано хорошо (1–3 пункта, если есть)"],
 "priorities": [{"title": "что сделать", "why": "почему это важно именно для этой базы", "tables": ["таблицы"]}]}
priorities — не больше 5, в порядке важности. Не придумывай проблем, которых нет в замечаниях."""
