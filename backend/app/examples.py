"""Демонстрационные запросы к тестовой БД «shop» (docker/)."""

DEMO_DDL_MYSQL = """CREATE TABLE users (
  id BIGINT NOT NULL PRIMARY KEY,
  email VARCHAR(255) NOT NULL,
  phone VARCHAR(32),
  name VARCHAR(100) NOT NULL,
  city VARCHAR(64) NOT NULL,
  created_at DATETIME NOT NULL,
  UNIQUE KEY uq_users_email (email)
);
CREATE TABLE products (
  id INT NOT NULL PRIMARY KEY,
  name VARCHAR(200) NOT NULL,
  category VARCHAR(64) NOT NULL,
  price DECIMAL(10,2) NOT NULL,
  created_at DATETIME NOT NULL
);
CREATE TABLE orders (
  id BIGINT NOT NULL PRIMARY KEY,
  user_id BIGINT NOT NULL,
  status VARCHAR(16) NOT NULL,
  total DECIMAL(12,2) NOT NULL,
  created_at DATETIME NOT NULL,
  KEY idx_orders_user_id (user_id),
  KEY idx_orders_created_at (created_at),
  CONSTRAINT fk_orders_user FOREIGN KEY (user_id) REFERENCES users (id)
);
CREATE TABLE order_items (
  id BIGINT NOT NULL PRIMARY KEY,
  order_id BIGINT NOT NULL,
  product_id INT NOT NULL,
  quantity INT NOT NULL,
  price DECIMAL(10,2) NOT NULL,
  KEY idx_order_items_order_id (order_id),
  KEY idx_order_items_product_id (product_id)
);"""

DEMO_DDL_POSTGRES = """CREATE TABLE users (
  id BIGINT PRIMARY KEY,
  email VARCHAR(255) NOT NULL UNIQUE,
  phone VARCHAR(32),
  name VARCHAR(100) NOT NULL,
  city VARCHAR(64) NOT NULL,
  created_at TIMESTAMP NOT NULL
);
CREATE TABLE products (
  id INT PRIMARY KEY,
  name VARCHAR(200) NOT NULL,
  category VARCHAR(64) NOT NULL,
  price NUMERIC(10,2) NOT NULL,
  created_at TIMESTAMP NOT NULL
);
CREATE TABLE orders (
  id BIGINT PRIMARY KEY,
  user_id BIGINT NOT NULL REFERENCES users (id),
  status VARCHAR(16) NOT NULL,
  total NUMERIC(12,2) NOT NULL,
  created_at TIMESTAMP NOT NULL
);
CREATE INDEX idx_orders_user_id ON orders (user_id);
CREATE INDEX idx_orders_created_at ON orders (created_at);
CREATE TABLE order_items (
  id BIGINT PRIMARY KEY,
  order_id BIGINT NOT NULL REFERENCES orders (id),
  product_id INT NOT NULL REFERENCES products (id),
  quantity INT NOT NULL,
  price NUMERIC(10,2) NOT NULL
);
CREATE INDEX idx_order_items_order_id ON order_items (order_id);
CREATE INDEX idx_order_items_product_id ON order_items (product_id);"""

EXAMPLES = {
    "ddl": {"mysql": DEMO_DDL_MYSQL, "postgres": DEMO_DDL_POSTGRES},
    "queries": [
        {"id": "date-function", "title": "Функция над индексированной датой",
         "mysql": "SELECT id, user_id, total\nFROM orders\nWHERE DATE(created_at) = '2025-03-15'\nORDER BY id",
         "postgres": "SELECT id, user_id, total\nFROM orders\nWHERE DATE(created_at) = '2025-03-15'\nORDER BY id"},
        {"id": "year-function", "title": "YEAR() и сортировка с LIMIT",
         "mysql": "SELECT id, user_id, total, created_at\nFROM orders\nWHERE YEAR(created_at) = 2024 AND status = 'paid'\n"
                  "ORDER BY created_at DESC\nLIMIT 50",
         "postgres": "SELECT id, user_id, total, created_at\nFROM orders\nWHERE EXTRACT(YEAR FROM created_at) = 2024 "
                     "AND status = 'paid'\nORDER BY created_at DESC\nLIMIT 50"},
        {"id": "correlated", "title": "Коррелированные подзапросы в SELECT",
         "mysql": "SELECT u.id, u.name,\n  (SELECT COUNT(*) FROM orders o WHERE o.user_id = u.id) AS orders_count,\n"
                  "  (SELECT SUM(o.total) FROM orders o WHERE o.user_id = u.id) AS orders_sum\nFROM users u\n"
                  "WHERE u.city = 'Томск'\nORDER BY u.id",
         "postgres": "SELECT u.id, u.name,\n  (SELECT COUNT(*) FROM orders o WHERE o.user_id = u.id) AS orders_count,\n"
                     "  (SELECT SUM(o.total) FROM orders o WHERE o.user_id = u.id) AS orders_sum\nFROM users u\n"
                     "WHERE u.city = 'Томск'\nORDER BY u.id"},
        {"id": "or-columns", "title": "OR по разным колонкам",
         "mysql": "SELECT *\nFROM users\nWHERE email = 'user500@yandex.ru' OR phone = '+79000000777'",
         "postgres": "SELECT *\nFROM users\nWHERE email = 'user500@yandex.ru' OR phone = '+79000000777'"},
        {"id": "type-mismatch", "title": "Сравнение строки с числом",
         "mysql": "SELECT id, name, email\nFROM users\nWHERE email = 'user42@gmail.com' OR id IN (SELECT user_id FROM orders WHERE id = '777')",
         "postgres": "SELECT id, name, email\nFROM users\nWHERE email = 'user42@gmail.com' OR id IN (SELECT user_id FROM orders WHERE id = '777')"},
        {"id": "not-in", "title": "NOT IN с подзапросом",
         "mysql": "SELECT id, email\nFROM users\nWHERE id NOT IN (SELECT user_id FROM orders WHERE status = 'cancelled')\nORDER BY id\nLIMIT 100",
         "postgres": "SELECT id, email\nFROM users\nWHERE id NOT IN (SELECT user_id FROM orders WHERE status = 'cancelled')\nORDER BY id\nLIMIT 100"},
        {"id": "distinct-join", "title": "DISTINCT вместо EXISTS",
         "mysql": "SELECT DISTINCT u.id, u.email\nFROM users u\nJOIN orders o ON o.user_id = u.id\n"
                  "WHERE o.created_at >= '2026-01-01' AND u.city = 'Казань'",
         "postgres": "SELECT DISTINCT u.id, u.email\nFROM users u\nJOIN orders o ON o.user_id = u.id\n"
                     "WHERE o.created_at >= '2026-01-01' AND u.city = 'Казань'"},
        {"id": "big-offset", "title": "Глубокая пагинация OFFSET",
         "mysql": "SELECT id, user_id, total\nFROM orders\nORDER BY id\nLIMIT 20 OFFSET 400000",
         "postgres": "SELECT id, user_id, total\nFROM orders\nORDER BY id\nLIMIT 20 OFFSET 400000"},
        {"id": "report", "title": "Отчёт по категориям",
         "mysql": "SELECT p.category, SUM(oi.quantity * oi.price) AS revenue, COUNT(DISTINCT o.id) AS orders\n"
                  "FROM order_items oi\nJOIN products p ON p.id = oi.product_id\nJOIN orders o ON o.id = oi.order_id\n"
                  "WHERE o.status = 'refunded' AND YEAR(o.created_at) = 2025\nGROUP BY p.category\nORDER BY revenue DESC",
         "postgres": "SELECT p.category, SUM(oi.quantity * oi.price) AS revenue, COUNT(DISTINCT o.id) AS orders\n"
                     "FROM order_items oi\nJOIN products p ON p.id = oi.product_id\nJOIN orders o ON o.id = oi.order_id\n"
                     "WHERE o.status = 'refunded' AND EXTRACT(YEAR FROM o.created_at) = 2025\nGROUP BY p.category\n"
                     "ORDER BY revenue DESC"},
        {"id": "like", "title": "LIKE с ведущим %",
         "mysql": "SELECT id, email\nFROM users\nWHERE email LIKE '%123@example.org'",
         "postgres": "SELECT id, email\nFROM users\nWHERE email LIKE '%123@example.org'"},
    ],
}
