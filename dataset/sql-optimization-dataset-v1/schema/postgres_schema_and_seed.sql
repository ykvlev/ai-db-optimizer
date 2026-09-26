-- Демонстрационная БД «shop» для PostgreSQL 16 — та же схема и те же данные (seed v1), что и для MySQL.

CREATE TABLE users (
  id          BIGINT       PRIMARY KEY,
  email       VARCHAR(255) NOT NULL UNIQUE,
  phone       VARCHAR(32),
  name        VARCHAR(100) NOT NULL,
  city        VARCHAR(64)  NOT NULL,
  created_at  TIMESTAMP    NOT NULL
);

CREATE TABLE products (
  id          INT           PRIMARY KEY,
  name        VARCHAR(200)  NOT NULL,
  category    VARCHAR(64)   NOT NULL,
  price       NUMERIC(10,2) NOT NULL,
  created_at  TIMESTAMP     NOT NULL
);

CREATE TABLE orders (
  id          BIGINT        PRIMARY KEY,
  user_id     BIGINT        NOT NULL REFERENCES users (id),
  status      VARCHAR(16)   NOT NULL,
  total       NUMERIC(12,2) NOT NULL,
  created_at  TIMESTAMP     NOT NULL
);
CREATE INDEX idx_orders_user_id ON orders (user_id);
CREATE INDEX idx_orders_created_at ON orders (created_at);

CREATE TABLE order_items (
  id          BIGINT        PRIMARY KEY,
  order_id    BIGINT        NOT NULL REFERENCES orders (id),
  product_id  INT           NOT NULL REFERENCES products (id),
  quantity    INT           NOT NULL,
  price       NUMERIC(10,2) NOT NULL
);
CREATE INDEX idx_order_items_order_id ON order_items (order_id);
CREATE INDEX idx_order_items_product_id ON order_items (product_id);

INSERT INTO users (id, email, phone, name, city, created_at)
SELECT n,
       'user' || n || '@' || (ARRAY['mail.ru', 'yandex.ru', 'gmail.com', 'example.org'])[1 + n % 4],
       CASE WHEN n % 10 = 0 THEN NULL ELSE '+7900' || LPAD(n::text, 7, '0') END,
       'Пользователь ' || n,
       (ARRAY['Москва', 'Москва', 'Санкт-Петербург', 'Казань', 'Новосибирск', 'Екатеринбург', 'Нижний Новгород',
              'Самара', 'Томск', 'Иркутск'])[1 + (n * 7) % 10],
       TIMESTAMP '2020-01-01' + ((n::bigint * 1987) % 199584000) * INTERVAL '1 second'
FROM generate_series(1, 100000) AS n;

INSERT INTO products (id, name, category, price, created_at)
SELECT n, 'Товар ' || n,
       (ARRAY['Электроника', 'Книги', 'Одежда', 'Дом', 'Спорт', 'Игрушки', 'Продукты', 'Красота'])[1 + n % 8],
       ROUND(100 + ((n::bigint * 7919) % 50000) / 3.0, 2),
       TIMESTAMP '2019-06-01' + ((n::bigint * 86413) % 180000000) * INTERVAL '1 second'
FROM generate_series(1, 2000) AS n;

INSERT INTO orders (id, user_id, status, total, created_at)
SELECT n,
       1 + (n::bigint * 7919) % 100000,
       (ARRAY['paid', 'paid', 'paid', 'paid', 'paid', 'paid', 'delivered', 'delivered', 'delivered', 'delivered',
              'delivered', 'delivered', 'new', 'new', 'shipped', 'shipped', 'cancelled', 'cancelled', 'refunded',
              'paid'])[1 + (n * 31) % 20],
       ROUND(150 + ((n::bigint * 104729) % 1500000) / 100.0, 2),
       TIMESTAMP '2020-01-01' + ((n::bigint * 37813) % 212284800) * INTERVAL '1 second'
FROM generate_series(1, 500000) AS n;

INSERT INTO order_items (id, order_id, product_id, quantity, price)
SELECT (o - 1) * 3 + k + 1,
       o,
       1 + (o::bigint * 13 + k * 577) % 2000,
       1 + (o + k) % 4,
       ROUND(100 + ((((o::bigint * 13 + k * 577) % 2000) * 7919) % 50000) / 3.0, 2)
FROM generate_series(1, 500000) AS o CROSS JOIN generate_series(0, 2) AS k;

ANALYZE;

CREATE ROLE optimizer_ro LOGIN PASSWORD 'optimizer_ro';
GRANT CONNECT ON DATABASE shop TO optimizer_ro;
GRANT USAGE ON SCHEMA public TO optimizer_ro;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO optimizer_ro;
