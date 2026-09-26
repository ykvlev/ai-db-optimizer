"""Встроенный исследовательский датасет shop-bench-v1 для демо-БД «shop» (docker/, seed shop-seed-v1).

Запросы сгруппированы по категориям антипаттернов. Категория «control» — уже оптимальные запросы:
по ним измеряется, как часто система/модель «ломает» или замедляет запрос, которому оптимизация не нужна.
"""

from __future__ import annotations

from app.models import Dialect

DATASET_NAME = "shop-bench"
DATASET_VERSION = "shop-bench-v1"
DATABASE_SEED = "shop-seed-v1"

CATEGORIES = {
    "date_function": "Функция DATE() над индексированной колонкой",
    "year_function": "YEAR()/EXTRACT над колонкой + сортировка с LIMIT",
    "year_aggregate": "YEAR()/EXTRACT в агрегирующем запросе",
    "correlated_select": "Коррелированные подзапросы в списке SELECT",
    "correlated_exists": "Коррелированный EXISTS",
    "not_in": "NOT IN с подзапросом",
    "distinct_join": "DISTINCT + JOIN вместо полусоединения",
    "or_columns": "OR по разным колонкам",
    "type_mismatch": "Несовпадение типов в сравнении",
    "big_offset": "Глубокая пагинация OFFSET",
    "leading_like": "LIKE с ведущим %",
    "in_subquery_agg": "IN с агрегирующим подзапросом",
    "report": "Аналитический отчёт с JOIN и функцией над датой",
    "count_distinct_subquery": "COUNT по производной таблице с DISTINCT",
    "max_per_group": "Максимум в группе через коррелированный подзапрос",
    "control": "Контроль: уже оптимальные запросы",
}


def _year(col: str, dbms: Dialect) -> str:
    return f"YEAR({col})" if dbms == "mysql" else f"EXTRACT(YEAR FROM {col})"


def build_shop_bench(dbms: Dialect) -> list[dict]:
    q: list[dict] = []

    def add(category: str, title: str, sql: str):
        n = sum(1 for x in q if x["category"] == category) + 1
        q.append({"key": f"{category}-{n}", "category": category, "title": title, "sql": sql.strip()})

    for d in ("2025-03-15", "2023-11-02", "2021-07-19", "2026-01-05"):
        add("date_function", f"Заказы за {d}",
            f"SELECT id, user_id, total\nFROM orders\nWHERE DATE(created_at) = '{d}'\nORDER BY id")
    for y, s in ((2024, "paid"), (2022, "delivered"), (2025, "cancelled")):
        add("year_function", f"Последние заказы «{s}» за {y}",
            f"SELECT id, user_id, total, created_at\nFROM orders\nWHERE {_year('created_at', dbms)} = {y} AND status = '{s}'\n"
            f"ORDER BY created_at DESC\nLIMIT 50")
    for y in (2021, 2025):
        add("year_aggregate", f"Выручка по статусам за {y}",
            f"SELECT status, COUNT(*) AS cnt, SUM(total) AS revenue\nFROM orders\nWHERE {_year('created_at', dbms)} = {y}\n"
            f"GROUP BY status\nORDER BY status")
    for city in ("Томск", "Иркутск", "Самара"):
        add("correlated_select", f"Статистика клиентов, {city}",
            f"SELECT u.id, u.name,\n  (SELECT COUNT(*) FROM orders o WHERE o.user_id = u.id) AS orders_count,\n"
            f"  (SELECT SUM(o.total) FROM orders o WHERE o.user_id = u.id) AS orders_sum\nFROM users u\n"
            f"WHERE u.city = '{city}'\nORDER BY u.id")
    for city, amount in (("Казань", 14000), ("Новосибирск", 14500)):
        add("correlated_exists", f"Клиенты с крупными заказами, {city}",
            f"SELECT u.id, u.email\nFROM users u\nWHERE u.city = '{city}'\n"
            f"  AND EXISTS (SELECT 1 FROM orders o WHERE o.user_id = u.id AND o.total > {amount})\nORDER BY u.id")
    for s in ("cancelled", "refunded", "new"):
        add("not_in", f"Клиенты без заказов «{s}»",
            f"SELECT id, email\nFROM users\nWHERE id NOT IN (SELECT user_id FROM orders WHERE status = '{s}')\n"
            f"ORDER BY id\nLIMIT 100")
    for city, since in (("Казань", "2026-01-01"), ("Томск", "2025-06-01"), ("Самара", "2025-12-01")):
        add("distinct_join", f"Активные клиенты с {since}, {city}",
            f"SELECT DISTINCT u.id, u.email\nFROM users u\nJOIN orders o ON o.user_id = u.id\n"
            f"WHERE o.created_at >= '{since}' AND u.city = '{city}'\nORDER BY u.id")
    for n in (500, 77777):
        add("or_columns", f"Поиск клиента по email или телефону ({n})",
            f"SELECT id, name, email, phone\nFROM users\nWHERE email = 'user{n}@{('mail.ru', 'yandex.ru', 'gmail.com', 'example.org')[n % 4]}'"
            f" OR phone = '+7900{n + 1:07d}'")
    add("type_mismatch", "Поиск заказа по id-строке",
        "SELECT id, user_id, status, total\nFROM orders\nWHERE id = '123457'")
    if dbms == "mysql":
        add("type_mismatch", "Поиск по телефону числом",
            "SELECT id, name, phone\nFROM users\nWHERE phone = 79000012345")
    else:
        add("type_mismatch", "Поиск по телефону с приведением",
            "SELECT id, name, phone\nFROM users\nWHERE CAST(phone AS TEXT) = '+79000012345'")
    for off in (100000, 250000, 450000):
        add("big_offset", f"Страница заказов, OFFSET {off}",
            f"SELECT id, user_id, total\nFROM orders\nORDER BY id\nLIMIT 20 OFFSET {off}")
    for pat in ("%123@example.org", "%496@mail.ru"):
        add("leading_like", f"Поиск по окончанию email «{pat}»",
            f"SELECT id, email\nFROM users\nWHERE email LIKE '{pat}'\nORDER BY id")
    for qty in (1900, 1950):
        add("in_subquery_agg", f"Товары с продажами > {qty} шт.",
            f"SELECT id, name, category, price\nFROM products\nWHERE id IN (\n  SELECT product_id FROM order_items\n"
            f"  GROUP BY product_id HAVING SUM(quantity) > {qty}\n)\nORDER BY id")
    for y, s in ((2025, "refunded"), (2023, "cancelled")):
        add("report", f"Отчёт по категориям, {s} {y}",
            f"SELECT p.category, SUM(oi.quantity * oi.price) AS revenue, COUNT(DISTINCT o.id) AS orders\n"
            f"FROM order_items oi\nJOIN products p ON p.id = oi.product_id\nJOIN orders o ON o.id = oi.order_id\n"
            f"WHERE o.status = '{s}' AND {_year('o.created_at', dbms)} = {y}\nGROUP BY p.category\nORDER BY revenue DESC")
    add("count_distinct_subquery", "Число клиентов с оплаченными заказами",
        "SELECT COUNT(*) AS customers\nFROM (SELECT DISTINCT user_id FROM orders WHERE status = 'paid') t")
    for lo, hi in ((1, 1500), (50001, 51500)):
        add("max_per_group", f"Крупнейший заказ клиентов {lo}–{hi}",
            f"SELECT o.user_id, o.id, o.total\nFROM orders o\nWHERE o.user_id BETWEEN {lo} AND {hi}\n"
            f"  AND o.total = (SELECT MAX(o2.total) FROM orders o2 WHERE o2.user_id = o.user_id)\nORDER BY o.user_id, o.id")
    add("control", "Заказ по первичному ключу", "SELECT id, user_id, status, total\nFROM orders\nWHERE id = 424242")
    add("control", "Заказы клиента", "SELECT id, status, total, created_at\nFROM orders\nWHERE user_id = 31337\nORDER BY created_at")
    add("control", "Диапазон дат с LIMIT",
        "SELECT id, user_id, total\nFROM orders\nWHERE created_at >= '2025-05-01' AND created_at < '2025-05-02'\nORDER BY created_at\nLIMIT 100")
    add("control", "Позиции заказа с товарами",
        "SELECT oi.id, p.name, oi.quantity, oi.price\nFROM order_items oi\nJOIN products p ON p.id = oi.product_id\n"
        "WHERE oi.order_id = 250000\nORDER BY oi.id")
    return q


def build_shop_bench_mini(dbms: Dialect) -> list[dict]:
    """По одному запросу из каждой категории — для быстрых прогонов (например, локальных LLM на CPU)."""
    seen: set[str] = set()
    out = []
    for item in build_shop_bench(dbms):
        if item["category"] not in seen:
            seen.add(item["category"])
            out.append(item)
    return out


BUILTIN = [
    ("shop-bench", DATASET_VERSION, build_shop_bench,
     "40 запросов к демо-БД shop: 15 категорий антипаттернов + контрольная группа оптимальных запросов"),
    ("shop-bench-mini", "shop-bench-mini-v1", build_shop_bench_mini,
     "По одному запросу из каждой категории shop-bench-v1 (16 запросов) — для быстрых прогонов"),
]
