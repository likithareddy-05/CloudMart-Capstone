Cloud Mart – Data Model Documentation
1. Introduction
The Cloud Mart application uses Amazon RDS for MySQL as its relational database.
The database is designed to store and manage:
•	User and authentication information 
•	Product catalog information 
•	Product inventory and stock levels 
•	Customer orders 
•	Individual products belonging to each order 
The data model uses primary keys, foreign keys, unique constraints, and referential integrity to maintain consistency between related entities.


2. Database Overview
Database: cloudmart
The database contains the following five main tables:
1.	USERS 
2.	PRODUCTS 
3.	INVENTORY 
4.	ORDERS 
5.	ORDER_ITEMS



High-level relationship
                    USERS
                      │
                      │ 1
                      │
                      │ Many
                      ▼
                    ORDERS
                      │
                      │ 1
                      │
                      │ Many
                      ▼
                 ORDER_ITEMS  
                      │
                      │ Many-to-One
                      ▼
                   PRODUCTS
                      │
                      │ One-to-One
                      ▼
                   INVENTORY
                    
                

3. USERS Table
The USERS table stores customer and administrator information used for authentication and authorization.

Structure
Column	Data Type	Constraint	Description
user_id	INT	Primary Key, Auto Increment	Unique identifier for each user
name	VARCHAR(150)	NOT NULL	User's name
email	VARCHAR(255)	NOT NULL, UNIQUE	User's email address
role	VARCHAR(20)	NOT NULL, Default USER	User role such as USER or ADMIN
token_hash	VARCHAR(64)	UNIQUE	Hash of the authentication token
created_at	TIMESTAMP	Default current timestamp	User creation time
updated_at	TIMESTAMP	Automatically updated	Last modification time

The current schema defines user_id as the primary key and email as unique. The authentication token is represented by token_hash, rather than storing the token itself in the table. 
Purpose
The table is used for:
•	Identifying users 
•	Storing user roles 
•	Authentication 
•	Associating users with their orders






4. PRODUCTS Table
The PRODUCTS table stores the product catalog.
Structure
Column	Data Type	Constraint	Description
product_id	INT	Primary Key, Auto Increment	Unique product identifier
name	VARCHAR(150)	NOT NULL	Product name
description	VARCHAR(500)	Nullable	Product description
price	DECIMAL(10,2)	NOT NULL	Product price
category	VARCHAR(100)	Nullable	Product category
is_deleted	BOOLEAN	NOT NULL, Default FALSE	Indicates whether product is soft-deleted
created_at	TIMESTAMP	Default current timestamp	Product creation time
updated_at	TIMESTAMP	Automatically updated	Last modification time

The product table uses product_id as its primary key and includes an is_deleted field to support soft deletion. 
Purpose
The table is used for:
•	Product creation 
•	Product retrieval 
•	Product updates 
•	Product deletion through soft delete 
•	Product information used during order processing 





5. INVENTORY Table
The INVENTORY table maintains stock information for products.
Structure
Column	Data Type	Constraint	Description
inventory_id	INT	Primary Key, Auto Increment	Unique inventory record ID
product_id	INT	NOT NULL, Foreign Key, UNIQUE	Product associated with the inventory record
stock_count	INT	NOT NULL, Default 0	Current available stock
low_stock_threshold	INT	NOT NULL, Default 10	Threshold used to identify low stock
updated_at	TIMESTAMP	Automatically updated	Last inventory modification time

The current schema enforces a foreign key from inventory.product_id to products.product_id and also makes product_id unique, ensuring one inventory record per product. 
Relationship
PRODUCTS
   │
   │ 1
   │
   │ 1
   ▼
INVENTORY
Purpose
The table is used for:
•	Tracking stock 
•	Updating stock when orders are placed 
•	Restoring stock when orders are cancelled 
•	Detecting low-stock conditions

6. ORDERS Table
The ORDERS table stores information about customer orders.
Structure
Column	Data Type	Constraint	Description
order_id	INT	Primary Key, Auto Increment	Unique order identifier
customer_id	INT	NOT NULL, Foreign Key	User who created the order
total_amount	DECIMAL(10,2)	NOT NULL, Default 0.00	Total order amount
status	VARCHAR(30)	NOT NULL, Default PENDING	Current order status
failure_reason	VARCHAR(500)	Nullable	Reason when an order fails
created_at	TIMESTAMP	Default current timestamp	Order creation time
updated_at	TIMESTAMP	Automatically updated	Last order modification time

The customer_id column references users.user_id. The schema uses ON DELETE RESTRICT for this relationship, preventing a user from being deleted when related orders exist. 
Relationship
USERS
  │
  │ 1
  │
  │ Many
  ▼
ORDERS
One user can have multiple orders.





7. ORDER_ITEMS Table
The ORDER_ITEMS table stores the individual products included in an order.
This table is important because one order can contain multiple products.
Structure
Column	Data Type	Constraint	Description
order_item_id	INT	Primary Key, Auto Increment	Unique order-item identifier
order_id	INT	NOT NULL, Foreign Key	Associated order
product_id	INT	NOT NULL, Foreign Key	Product included in the order
quantity	INT	NOT NULL	Quantity ordered
unit_price	DECIMAL(10,2)	NOT NULL	Product price at order time
subtotal	DECIMAL(10,2)	NOT NULL	Quantity × unit price

The schema defines foreign keys from order_items.order_id to orders.order_id and from order_items.product_id to products.product_id. It also enforces UNIQUE(order_id, product_id).


8. Primary Keys
Primary keys uniquely identify each record.
Table	Primary Key
USERS	user_id
PRODUCTS	product_id
INVENTORY	inventory_id
ORDERS	order_id
ORDER_ITEMS	order_item_id


All primary-key IDs use AUTO_INCREMENT. 

9. Foreign Keys
The database uses foreign keys to maintain relationships and referential integrity.
Child Table	Column	Parent Table	Parent Column
INVENTORY	product_id	PRODUCTS	product_id
ORDERS	customer_id	USERS	user_id
ORDER_ITEMS	order_id	ORDERS	order_id
ORDER_ITEMS	product_id	PRODUCTS	product_id

These relationships ensure that referenced users, products and orders exist before related records are created

10. Why This Data Model Was Chosen
The database separates different types of information into dedicated tables rather than storing everything in one table.
This provides:
•	Data organization — each table has a clear responsibility. 
•	Reduced duplication — product and user information does not need to be repeated in every order. 
•	Referential integrity — foreign keys maintain valid relationships. 
•	Scalability — multiple users, products and orders can be stored. 
•	Order flexibility — one order can contain multiple products through ORDER_ITEMS. 
•	Inventory tracking — inventory is maintained separately from product information. 
•	Authentication support — user roles and token hashes are stored in the USERS table. 
•	Historical pricing — ORDER_ITEMS.unit_price and subtotal preserve the pricing information associated with the order item.
