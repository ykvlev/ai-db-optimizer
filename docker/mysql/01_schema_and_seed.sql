SET NAMES utf8mb4;
-- Демонстрационная БД «shop» для MySQL 8. Данные детерминированы (seed v1): повторный запуск даёт ту же БД.
-- Намеренно НЕТ индексов по orders.status, users.phone, users.city, products.category —
-- чтобы на них были видны проблемы производительности.

CREATE TABLE users (
  id          BIGINT       NOT NULL,
  email       VARCHAR(255) NOT NULL,
  phone       VARCHAR(32),
  name        VARCHAR(100) NOT NULL,
  city        VARCHAR(64)  NOT NULL,
  created_at  DATETIME     NOT NULL,
  PRIMARY KEY (id),
  UNIQUE KEY uq_users_email (email)
) ENGINE=InnoDB;

CREATE TABLE products (
  id          INT           NOT NULL,
  name        VARCHAR(200)  NOT NULL,
  category    VARCHAR(64)   NOT NULL,
  price       DECIMAL(10,2) NOT NULL,
  created_at  DATETIME      NOT NULL,
  PRIMARY KEY (id)
) ENGINE=InnoDB;

CREATE TABLE orders (
  id          BIGINT        NOT NULL,
  user_id     BIGINT        NOT NULL,
  status      VARCHAR(16)   NOT NULL,
  total       DECIMAL(12,2) NOT NULL,
  created_at  DATETIME      NOT NULL,
  PRIMARY KEY (id),
  KEY idx_orders_user_id (user_id),
  KEY idx_orders_created_at (created_at),
  CONSTRAINT fk_orders_user FOREIGN KEY (user_id) REFERENCES users (id)
) ENGINE=InnoDB;

CREATE TABLE order_items (
  id          BIGINT        NOT NULL,
  order_id    BIGINT        NOT NULL,
  product_id  INT           NOT NULL,
  quantity    INT           NOT NULL,
  price       DECIMAL(10,2) NOT NULL,
  PRIMARY KEY (id),
  KEY idx_order_items_order_id (order_id),
  KEY idx_order_items_product_id (product_id),
  CONSTRAINT fk_items_order FOREIGN KEY (order_id) REFERENCES orders (id),
  CONSTRAINT fk_items_product FOREIGN KEY (product_id) REFERENCES products (id)
) ENGINE=InnoDB;

-- генератор чисел 1..1 000 000
CREATE TABLE _digits (d INT PRIMARY KEY);
INSERT INTO _digits VALUES (0),(1),(2),(3),(4),(5),(6),(7),(8),(9);
CREATE TABLE _seq (n INT PRIMARY KEY);
INSERT INTO _seq (n)
SELECT 1 + a.d + 10*b.d + 100*c.d + 1000*d.d + 10000*e.d + 100000*f.d
FROM _digits a, _digits b, _digits c, _digits d, _digits e, _digits f;

INSERT INTO users (id, email, phone, name, city, created_at)
SELECT n,
       CONCAT('user', n, '@', ELT(1 + n % 4, 'mail.ru', 'yandex.ru', 'gmail.com', 'example.org')),
       IF(n % 10 = 0, NULL, CONCAT('+7900', LPAD(n, 7, '0'))),
       CONCAT('Пользователь ', n),
       ELT(1 + (n * 7) % 10, 'Москва', 'Москва', 'Санкт-Петербург', 'Казань', 'Новосибирск', 'Екатеринбург',
           'Нижний Новгород', 'Самара', 'Томск', 'Иркутск'),
       TIMESTAMP('2020-01-01') + INTERVAL ((n * 1987) % 199584000) SECOND
FROM _seq WHERE n <= 100000;

INSERT INTO products (id, name, category, price, created_at)
SELECT n, CONCAT('Товар ', n),
       ELT(1 + n % 8, 'Электроника', 'Книги', 'Одежда', 'Дом', 'Спорт', 'Игрушки', 'Продукты', 'Красота'),
       ROUND(100 + (n * 7919) % 50000 / 3, 2),
       TIMESTAMP('2019-06-01') + INTERVAL ((n * 86413) % 180000000) SECOND
FROM _seq WHERE n <= 2000;

INSERT INTO orders (id, user_id, status, total, created_at)
SELECT n,
       1 + (n * 7919) % 100000,
       ELT(1 + (n * 31) % 20, 'paid', 'paid', 'paid', 'paid', 'paid', 'paid', 'delivered', 'delivered', 'delivered',
           'delivered', 'delivered', 'delivered', 'new', 'new', 'shipped', 'shipped', 'cancelled', 'cancelled',
           'refunded', 'paid'),
       ROUND(150 + (n * 104729) % 1500000 / 100, 2),
       TIMESTAMP('2020-01-01') + INTERVAL ((n * 37813) % 212284800) SECOND
FROM _seq WHERE n <= 500000;

INSERT INTO order_items (id, order_id, product_id, quantity, price)
SELECT (o.n - 1) * 3 + k.d + 1,
       o.n,
       1 + (o.n * 13 + k.d * 577) % 2000,
       1 + (o.n + k.d) % 4,
       ROUND(100 + ((o.n * 13 + k.d * 577) % 2000 * 7919) % 50000 / 3, 2)
FROM _seq o JOIN _digits k ON k.d < 3
WHERE o.n <= 500000;

DROP TABLE _seq;
DROP TABLE _digits;

ANALYZE TABLE users, products, orders, order_items;

-- Пользователь только для чтения: именно под ним AI Database Optimizer подключается к БД
CREATE USER 'optimizer_ro'@'%' IDENTIFIED BY 'optimizer_ro';
GRANT SELECT, SHOW VIEW ON shop.* TO 'optimizer_ro'@'%';
FLUSH PRIVILEGES;
