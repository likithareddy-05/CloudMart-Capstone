CREATE DATABASE IF NOT EXISTS cloudmart;

USE cloudmart;

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
-- INDEXES
-- =====================================================

CREATE INDEX idx_products_category
    ON products(category);

CREATE INDEX idx_inventory_product
    ON inventory(product_id);


-- =====================================================
-- SAMPLE PRODUCTS
-- =====================================================

INSERT INTO products
    (name, description, price, category)
VALUES
    (
        'Laptop',
        '15 inch business laptop',
        65000.00,
        'Electronics'
    ),
    (
        'Wireless Mouse',
        'Wireless optical mouse',
        1200.00,
        'Accessories'
    ),
    (
        'Keyboard',
        'Mechanical keyboard',
        3500.00,
        'Accessories'
    );


-- =====================================================
-- SAMPLE INVENTORY
-- =====================================================

INSERT INTO inventory
    (product_id, stock_count, low_stock_threshold)
VALUES
    (1, 25, 5),
    (2, 50, 10),
    (3, 8, 10);