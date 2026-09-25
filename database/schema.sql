-- =====================================================
-- CLOUDMART DATABASE SCHEMA
-- =====================================================

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

    token_hash VARCHAR(64) UNIQUE,

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

    is_deleted BOOLEAN NOT NULL DEFAULT FALSE,

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
        ON UPDATE CASCADE,

    CONSTRAINT uq_inventory_product
        UNIQUE (product_id)
);

-- =====================================================
-- ORDERS TABLE
--
-- One order can contain multiple products.
-- Product-specific information is stored in order_items.
-- =====================================================

CREATE TABLE IF NOT EXISTS orders (
    order_id INT AUTO_INCREMENT PRIMARY KEY,

    customer_id INT NOT NULL,

    total_amount DECIMAL(10,2) NOT NULL DEFAULT 0.00,

    status VARCHAR(30) NOT NULL DEFAULT 'PENDING',

    failure_reason VARCHAR(500) NULL,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        ON UPDATE CURRENT_TIMESTAMP,

    CONSTRAINT fk_orders_customer
        FOREIGN KEY (customer_id)
        REFERENCES users(user_id)
        ON DELETE RESTRICT
        ON UPDATE CASCADE
);


-- =====================================================
-- ORDER ITEMS TABLE
--
-- Stores individual products belonging to an order.
--
-- Example:
--
-- Order 1001:
--     Product 17 -> quantity 2
--     Product 5  -> quantity 1
--     Product 12 -> quantity 3
--
-- This creates ONE order row and THREE order_items rows.
-- =====================================================

CREATE TABLE IF NOT EXISTS order_items (
    order_item_id INT AUTO_INCREMENT PRIMARY KEY,

    order_id INT NOT NULL,

    product_id INT NOT NULL,

    quantity INT NOT NULL,

    unit_price DECIMAL(10,2) NOT NULL,

    subtotal DECIMAL(10,2) NOT NULL,

    CONSTRAINT fk_order_items_order
        FOREIGN KEY (order_id)
        REFERENCES orders(order_id)
        ON DELETE CASCADE
        ON UPDATE CASCADE,

    CONSTRAINT fk_order_items_product
        FOREIGN KEY (product_id)
        REFERENCES products(product_id)
        ON DELETE RESTRICT
        ON UPDATE CASCADE,

    CONSTRAINT uq_order_product
        UNIQUE (order_id, product_id)
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
-- REMOVE DUPLICATE INVENTORY ROWS
-- =====================================================

DELETE i1
FROM inventory i1
JOIN inventory i2
    ON i1.product_id = i2.product_id
   AND i1.inventory_id > i2.inventory_id;


-- =====================================================
-- INVENTORY PRODUCT UNIQUE CONSTRAINT
-- =====================================================

SET @constraint_exists = (
    SELECT COUNT(*)
    FROM information_schema.table_constraints
    WHERE constraint_schema = DATABASE()
      AND table_name = 'inventory'
      AND constraint_name = 'uq_inventory_product'
);

SET @sql = IF(
    @constraint_exists = 0,
    'ALTER TABLE inventory
     ADD CONSTRAINT uq_inventory_product UNIQUE (product_id)',
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
-- ORDER ITEMS ORDER INDEX
-- =====================================================

SET @index_exists = (
    SELECT COUNT(*)
    FROM information_schema.statistics
    WHERE table_schema = DATABASE()
      AND table_name = 'order_items'
      AND index_name = 'idx_order_items_order'
);

SET @sql = IF(
    @index_exists = 0,
    'CREATE INDEX idx_order_items_order ON order_items(order_id)',
    'SELECT 1'
);

PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;


-- =====================================================
-- ORDER ITEMS PRODUCT INDEX
-- =====================================================

SET @index_exists = (
    SELECT COUNT(*)
    FROM information_schema.statistics
    WHERE table_schema = DATABASE()
      AND table_name = 'order_items'
      AND index_name = 'idx_order_items_product'
);

SET @sql = IF(
    @index_exists = 0,
    'CREATE INDEX idx_order_items_product ON order_items(product_id)',
    'SELECT 1'
);

PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;


-- =====================================================
-- ADD FAILURE_REASON TO EXISTING ORDERS
-- =====================================================

SET @column_exists = (
    SELECT COUNT(*)
    FROM information_schema.columns
    WHERE table_schema = DATABASE()
      AND table_name = 'orders'
      AND column_name = 'failure_reason'
);

SET @sql = IF(
    @column_exists = 0,
    'ALTER TABLE orders
     ADD COLUMN failure_reason VARCHAR(500) NULL',
    'SELECT 1'
);

PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;


-- =====================================================
-- ADD IS_DELETED TO EXISTING PRODUCTS
-- =====================================================

SET @column_exists = (
    SELECT COUNT(*)
    FROM information_schema.columns
    WHERE table_schema = DATABASE()
      AND table_name = 'products'
      AND column_name = 'is_deleted'
);

SET @sql = IF(
    @column_exists = 0,
    'ALTER TABLE products
     ADD COLUMN is_deleted BOOLEAN NOT NULL DEFAULT FALSE',
    'SELECT 1'
);

PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;


-- =====================================================
-- ADD TOKEN_HASH TO EXISTING USERS
-- =====================================================

SET @column_exists = (
    SELECT COUNT(*)
    FROM information_schema.columns
    WHERE table_schema = DATABASE()
      AND table_name = 'users'
      AND column_name = 'token_hash'
);

SET @sql = IF(
    @column_exists = 0,
    'ALTER TABLE users
     ADD COLUMN token_hash VARCHAR(64) NULL UNIQUE',
    'SELECT 1'
);

PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;


-- =====================================================
-- MIGRATE EXISTING ORDERS
--
-- Old orders table had:
--     product_id
--     quantity
--
-- These values are moved into order_items.
-- =====================================================

SET @column_exists = (
    SELECT COUNT(*)
    FROM information_schema.columns
    WHERE table_schema = DATABASE()
      AND table_name = 'orders'
      AND column_name = 'product_id'
);

SET @sql = IF(
    @column_exists = 1,
    '
    INSERT INTO order_items
        (
            order_id,
            product_id,
            quantity,
            unit_price,
            subtotal
        )
    SELECT
        o.order_id,
        o.product_id,
        o.quantity,

        CASE
            WHEN o.quantity > 0
                THEN o.total_amount / o.quantity
            ELSE 0
        END,

        o.total_amount

    FROM orders o

    WHERE NOT EXISTS (
        SELECT 1
        FROM order_items oi
        WHERE oi.order_id = o.order_id
    )
    ',
    'SELECT 1'
);

PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;


-- =====================================================
-- DROP OLD ORDERS PRODUCT FOREIGN KEY
-- =====================================================

SET @constraint_exists = (
    SELECT COUNT(*)
    FROM information_schema.table_constraints
    WHERE constraint_schema = DATABASE()
      AND table_name = 'orders'
      AND constraint_name = 'fk_orders_product'
);

SET @sql = IF(
    @constraint_exists = 1,
    'ALTER TABLE orders
     DROP FOREIGN KEY fk_orders_product',
    'SELECT 1'
);

PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;


-- =====================================================
-- DROP OLD ORDERS PRODUCT INDEX
-- =====================================================

SET @index_exists = (
    SELECT COUNT(*)
    FROM information_schema.statistics
    WHERE table_schema = DATABASE()
      AND table_name = 'orders'
      AND index_name = 'idx_orders_product'
);

SET @sql = IF(
    @index_exists = 1,
    'ALTER TABLE orders
     DROP INDEX idx_orders_product',
    'SELECT 1'
);

PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;


-- =====================================================
-- DROP OLD ORDERS PRODUCT_ID COLUMN
-- =====================================================

SET @column_exists = (
    SELECT COUNT(*)
    FROM information_schema.columns
    WHERE table_schema = DATABASE()
      AND table_name = 'orders'
      AND column_name = 'product_id'
);

SET @sql = IF(
    @column_exists = 1,
    'ALTER TABLE orders
     DROP COLUMN product_id',
    'SELECT 1'
);

PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;


-- =====================================================
-- DROP OLD ORDERS QUANTITY COLUMN
-- =====================================================

SET @column_exists = (
    SELECT COUNT(*)
    FROM information_schema.columns
    WHERE table_schema = DATABASE()
      AND table_name = 'orders'
      AND column_name = 'quantity'
);

SET @sql = IF(
    @column_exists = 1,
    'ALTER TABLE orders
     DROP COLUMN quantity',
    'SELECT 1'
);

PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;


-- =====================================================
-- SAMPLE USERS
-- =====================================================

-- =====================================================
-- SAMPLE CUSTOMERS AND ADMIN
-- =====================================================

INSERT IGNORE INTO users
(
    user_id,
    name,
    email,
    role,
    token_hash
)
VALUES
(
    1,
    'User 1',
    'user1@cloudmart.com',
    'USER',
    SHA2('CMUserToken001', 256)
),
(
    2,
    'User 2',
    'user2@cloudmart.com',
    'USER',
    SHA2('CMUserToken002', 256)
),
(
    3,
    'User 3',
    'user3@cloudmart.com',
    'USER',
    SHA2('CMUserToken003', 256)
),
(
    4,
    'User 4',
    'user4@cloudmart.com',
    'USER',
    SHA2('CMUserToken004', 256)
),
(
    5,
    'Admin',
    'admin@cloudmart.com',
    'ADMIN',
    SHA2('CMAdminToken001', 256)
);

-- =====================================================
-- SAMPLE PRODUCTS
-- =====================================================

INSERT INTO products
    (
        product_id,
        name,
        description,
        price,
        category
    )
VALUES
    (
        1,
        'Laptop',
        'Business laptop',
        75000.00,
        'Electronics'
    ),
    (
        2,
        'Wireless Mouse',
        'Wireless optical mouse',
        1200.00,
        'Accessories'
    ),
    (
        3,
        'Keyboard',
        'Mechanical keyboard',
        3500.00,
        'Accessories'
    )
ON DUPLICATE KEY UPDATE
    name = VALUES(name),
    description = VALUES(description),
    price = VALUES(price),
    category = VALUES(category);


-- =====================================================
-- SAMPLE INVENTORY
-- =====================================================

INSERT INTO inventory
    (
        product_id,
        stock_count,
        low_stock_threshold
    )
VALUES
    (
        1,
        50,
        10
    ),
    (
        2,
        100,
        20
    ),
    (
        3,
        75,
        15
    )
ON DUPLICATE KEY UPDATE
    stock_count = VALUES(stock_count),
    low_stock_threshold = VALUES(low_stock_threshold);




-- =====================================================
-- RESET AUTO_INCREMENT VALUES
-- Continue IDs from the CURRENT data
-- =====================================================

-- USERS
SET @next_user_id = (
    SELECT COALESCE(MAX(user_id), 0) + 1
    FROM users
);

SET @sql = CONCAT(
    'ALTER TABLE users AUTO_INCREMENT = ',
    @next_user_id
);

PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;


-- PRODUCTS
SET @next_product_id = (
    SELECT COALESCE(MAX(product_id), 0) + 1
    FROM products
);

SET @sql = CONCAT(
    'ALTER TABLE products AUTO_INCREMENT = ',
    @next_product_id
);

PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;


-- INVENTORY
SET @next_inventory_id = (
    SELECT COALESCE(MAX(inventory_id), 0) + 1
    FROM inventory
);

SET @sql = CONCAT(
    'ALTER TABLE inventory AUTO_INCREMENT = ',
    @next_inventory_id
);

PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;


-- ORDERS
SET @next_order_id = (
    SELECT COALESCE(MAX(order_id), 0) + 1
    FROM orders
);

SET @sql = CONCAT(
    'ALTER TABLE orders AUTO_INCREMENT = ',
    @next_order_id
);

PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;


-- ORDER ITEMS
SET @next_order_item_id = (
    SELECT COALESCE(MAX(order_item_id), 0) + 1
    FROM order_items
);

SET @sql = CONCAT(
    'ALTER TABLE order_items AUTO_INCREMENT = ',
    @next_order_item_id
);

PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;


-- =====================================================
-- END OF SCHEMA
-- =====================================================