CREATE DATABASE IF NOT EXISTS cloudmart;

USE cloudmart;


-- =====================================================
-- USERS TABLE
-- =====================================================

CREATE TABLE IF NOT EXISTS users (
    user_id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(150) NOT NULL,
    email VARCHAR(255) NOT NULL UNIQUE,
    role VARCHAR(20) NOT NULL DEFAULT 'USER',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        ON UPDATE CURRENT_TIMESTAMP
);


-- =====================================================
-- PRODUCTS TABLE
-- =====================================================

CREATE TABLE IF NOT EXISTS products (
    product_id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(150) NOT NULL,
    description VARCHAR(500),
    price DECIMAL(10,2) NOT NULL,
    category VARCHAR(100),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        ON UPDATE CURRENT_TIMESTAMP
);


-- =====================================================
-- INVENTORY TABLE
-- =====================================================

CREATE TABLE IF NOT EXISTS inventory (
    inventory_id INT AUTO_INCREMENT PRIMARY KEY,
    product_id INT NOT NULL,
    stock_count INT NOT NULL DEFAULT 0,
    low_stock_threshold INT NOT NULL DEFAULT 10,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        ON UPDATE CURRENT_TIMESTAMP,

    CONSTRAINT fk_inventory_product
        FOREIGN KEY (product_id)
        REFERENCES products(product_id)
        ON DELETE CASCADE
        ON UPDATE CASCADE
);


-- =====================================================
-- ORDERS TABLE
-- =====================================================

CREATE TABLE IF NOT EXISTS orders (
    order_id INT AUTO_INCREMENT PRIMARY KEY,

    customer_id INT NOT NULL,

    product_id INT NOT NULL,

    quantity INT NOT NULL,

    total_amount DECIMAL(10,2) NOT NULL,

    status VARCHAR(30) NOT NULL DEFAULT 'PENDING',

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        ON UPDATE CURRENT_TIMESTAMP,

    CONSTRAINT fk_orders_customer
        FOREIGN KEY (customer_id)
        REFERENCES users(user_id)
        ON DELETE RESTRICT
        ON UPDATE CASCADE,

    CONSTRAINT fk_orders_product
        FOREIGN KEY (product_id)
        REFERENCES products(product_id)
        ON DELETE RESTRICT
        ON UPDATE CASCADE
);


-- =====================================================
-- PRODUCTS CATEGORY INDEX
-- =====================================================

SET @index_exists = (
    SELECT COUNT(*)
    FROM information_schema.statistics
    WHERE table_schema = DATABASE()
      AND table_name = 'products'
      AND index_name = 'idx_products_category'
);

SET @sql = IF(
    @index_exists = 0,
    'CREATE INDEX idx_products_category ON products(category)',
    'SELECT 1'
);

PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;


-- =====================================================
-- INVENTORY PRODUCT INDEX
-- =====================================================

SET @index_exists = (
    SELECT COUNT(*)
    FROM information_schema.statistics
    WHERE table_schema = DATABASE()
      AND table_name = 'inventory'
      AND index_name = 'idx_inventory_product'
);

SET @sql = IF(
    @index_exists = 0,
    'CREATE INDEX idx_inventory_product ON inventory(product_id)',
    'SELECT 1'
);

PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;


-- =====================================================
-- ORDERS CUSTOMER INDEX
-- =====================================================

SET @index_exists = (
    SELECT COUNT(*)
    FROM information_schema.statistics
    WHERE table_schema = DATABASE()
      AND table_name = 'orders'
      AND index_name = 'idx_orders_customer'
);

SET @sql = IF(
    @index_exists = 0,
    'CREATE INDEX idx_orders_customer ON orders(customer_id)',
    'SELECT 1'
);

PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;


-- =====================================================
-- ORDERS PRODUCT INDEX
-- =====================================================

SET @index_exists = (
    SELECT COUNT(*)
    FROM information_schema.statistics
    WHERE table_schema = DATABASE()
      AND table_name = 'orders'
      AND index_name = 'idx_orders_product'
);

SET @sql = IF(
    @index_exists = 0,
    'CREATE INDEX idx_orders_product ON orders(product_id)',
    'SELECT 1'
);

PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;


-- =====================================================
-- SAMPLE USERS
-- =====================================================

INSERT INTO users
    (name, email, role)
SELECT
    'CloudMart User',
    'user@cloudmart.com',
    'USER'
WHERE NOT EXISTS (
    SELECT 1
    FROM users
    WHERE email = 'user@cloudmart.com'
);


INSERT INTO users
    (name, email, role)
SELECT
    'CloudMart Admin',
    'admin@cloudmart.com',
    'ADMIN'
WHERE NOT EXISTS (
    SELECT 1
    FROM users
    WHERE email = 'admin@cloudmart.com'
);


-- =====================================================
-- SAMPLE PRODUCTS
-- =====================================================

INSERT INTO products
    (name, description, price, category)
SELECT
    'Laptop',
    '15 inch business laptop',
    65000.00,
    'Electronics'
WHERE NOT EXISTS (
    SELECT 1
    FROM products
    WHERE name = 'Laptop'
);


INSERT INTO products
    (name, description, price, category)
SELECT
    'Wireless Mouse',
    'Wireless optical mouse',
    1200.00,
    'Accessories'
WHERE NOT EXISTS (
    SELECT 1
    FROM products
    WHERE name = 'Wireless Mouse'
);


INSERT INTO products
    (name, description, price, category)
SELECT
    'Keyboard',
    'Mechanical keyboard',
    3500.00,
    'Accessories'
WHERE NOT EXISTS (
    SELECT 1
    FROM products
    WHERE name = 'Keyboard'
);


-- =====================================================
-- SAMPLE INVENTORY
-- =====================================================

INSERT INTO inventory
    (product_id, stock_count, low_stock_threshold)
SELECT
    product_id,
    25,
    5
FROM products
WHERE name = 'Laptop'
  AND NOT EXISTS (
      SELECT 1
      FROM inventory i
      WHERE i.product_id = products.product_id
  );


INSERT INTO inventory
    (product_id, stock_count, low_stock_threshold)
SELECT
    product_id,
    50,
    10
FROM products
WHERE name = 'Wireless Mouse'
  AND NOT EXISTS (
      SELECT 1
      FROM inventory i
      WHERE i.product_id = products.product_id
  );


INSERT INTO inventory
    (product_id, stock_count, low_stock_threshold)
SELECT
    product_id,
    8,
    10
FROM products
WHERE name = 'Keyboard'
  AND NOT EXISTS (
      SELECT 1
      FROM inventory i
      WHERE i.product_id = products.product_id
  );