import json
import os
import logging

import boto3
import pymysql


# =========================================================
# LOGGING
# =========================================================

logger = logging.getLogger()
logger.setLevel(logging.INFO)


# =========================================================
# AWS CLIENT
# =========================================================

ssm = boto3.client("ssm")


# =========================================================
# ENVIRONMENT
# =========================================================

ENVIRONMENT = os.environ.get("ENVIRONMENT", "dev")

DB_HOST_PARAMETER = os.environ.get(
    "DB_HOST_PARAMETER",
    f"/cloudmart/{ENVIRONMENT}/db/host"
)

DB_PORT_PARAMETER = os.environ.get(
    "DB_PORT_PARAMETER",
    f"/cloudmart/{ENVIRONMENT}/db/port"
)

DB_NAME_PARAMETER = os.environ.get(
    "DB_NAME_PARAMETER",
    f"/cloudmart/{ENVIRONMENT}/db/name"
)

DB_USERNAME_PARAMETER = os.environ.get(
    "DB_USERNAME_PARAMETER",
    f"/cloudmart/{ENVIRONMENT}/db/username"
)

DB_PASSWORD_PARAMETER = os.environ.get(
    "DB_PASSWORD_PARAMETER",
    f"/cloudmart/{ENVIRONMENT}/db/password"
)


# =========================================================
# RESPONSE
# =========================================================

def response(status_code, body):

    return {
        "statusCode": status_code,
        "headers": {
            "Content-Type": "application/json"
        },
        "body": json.dumps(body, default=str)
    }


# =========================================================
# STRUCTURED LOGGING
# =========================================================

def log_event(level, action, **kwargs):

    log_data = {
        "level": level,
        "service": "cloudmart-product-service",
        "environment": ENVIRONMENT,
        "action": action
    }

    log_data.update(kwargs)

    logger.info(json.dumps(log_data))


# =========================================================
# GET DATABASE PARAMETERS FROM SSM
# =========================================================

def get_database_parameters():

    parameter_names = [
        DB_HOST_PARAMETER,
        DB_PORT_PARAMETER,
        DB_NAME_PARAMETER,
        DB_USERNAME_PARAMETER,
        DB_PASSWORD_PARAMETER
    ]

    result = ssm.get_parameters(
        Names=parameter_names,
        WithDecryption=True
    )

    parameters = {}

    for parameter in result["Parameters"]:
        parameters[parameter["Name"]] = parameter["Value"]

    missing = [
        name
        for name in parameter_names
        if name not in parameters
    ]

    if missing:
        raise Exception(
            f"Missing SSM parameters: {missing}"
        )

    return {
        "host": parameters[DB_HOST_PARAMETER],
        "port": int(parameters[DB_PORT_PARAMETER]),
        "database": parameters[DB_NAME_PARAMETER],
        "username": parameters[DB_USERNAME_PARAMETER],
        "password": parameters[DB_PASSWORD_PARAMETER]
    }


# =========================================================
# DATABASE CONNECTION
# =========================================================

def get_connection():

    db = get_database_parameters()

    return pymysql.connect(
        host=db["host"],
        port=db["port"],
        user=db["username"],
        password=db["password"],
        database=db["database"],
        cursorclass=pymysql.cursors.DictCursor,
        connect_timeout=10
    )


# =========================================================
# REQUEST BODY
# =========================================================

def get_request_body(event):

    body = event.get("body")

    if not body:
        return {}

    if isinstance(body, str):

        try:
            return json.loads(body)

        except json.JSONDecodeError:

            raise ValueError(
                "Request body must be valid JSON"
            )

    return body


# =========================================================
# CREATE PRODUCT
# POST /products
# =========================================================

def create_product(event):

    body = get_request_body(event)

    name = body.get("name")
    description = body.get("description")
    price = body.get("price")
    category = body.get("category")
    stock_count = body.get("stock_count")
    low_stock_threshold = body.get(
        "low_stock_threshold",
        10
    )

    if not name or price is None or stock_count is None:

        return response(
            400,
            {
                "message": (
                    "name, price and stock_count "
                    "are required"
                )
            }
        )

    try:

        price = float(price)
        stock_count = int(stock_count)
        low_stock_threshold = int(
            low_stock_threshold
        )

    except (ValueError, TypeError):

        return response(
            400,
            {
                "message": (
                    "price must be a number, "
                    "stock_count and low_stock_threshold "
                    "must be integers"
                )
            }
        )

    if price < 0:
        return response(
            400,
            {
                "message": "price cannot be negative"
            }
        )

    if stock_count < 0:
        return response(
            400,
            {
                "message": "stock_count cannot be negative"
            }
        )

    if low_stock_threshold < 0:
        return response(
            400,
            {
                "message": (
                    "low_stock_threshold "
                    "cannot be negative"
                )
            }
        )

    connection = None

    try:

        connection = get_connection()

        with connection.cursor() as cursor:

            # ---------------------------------------------
            # Insert product
            # ---------------------------------------------

            cursor.execute(
                """
                INSERT INTO products
                    (name, description, price, category)
                VALUES
                    (%s, %s, %s, %s)
                """,
                (
                    name,
                    description,
                    price,
                    category
                )
            )

            product_id = cursor.lastrowid

            # ---------------------------------------------
            # Insert inventory
            # ---------------------------------------------

            cursor.execute(
                """
                INSERT INTO inventory
                    (
                        product_id,
                        stock_count,
                        low_stock_threshold
                    )
                VALUES
                    (%s, %s, %s)
                """,
                (
                    product_id,
                    stock_count,
                    low_stock_threshold
                )
            )

        connection.commit()

        log_event(
            "INFO",
            "create_product",
            product_id=product_id
        )

        return response(
            201,
            {
                "message": "Product created successfully",
                "product_id": product_id
            }
        )

    except Exception as error:

        if connection:
            connection.rollback()

        log_event(
            "ERROR",
            "create_product_failed",
            error=str(error)
        )

        return response(
            500,
            {
                "message": "Failed to create product"
            }
        )

    finally:

        if connection:
            connection.close()


# =========================================================
# GET ALL PRODUCTS
# GET /products
# =========================================================

def get_products():

    connection = None

    try:

        connection = get_connection()

        with connection.cursor() as cursor:

            cursor.execute(
                """
                SELECT
                    p.product_id,
                    p.name,
                    p.description,
                    p.price,
                    p.category,
                    p.created_at,
                    p.updated_at,
                    i.inventory_id,
                    i.stock_count,
                    i.low_stock_threshold,
                    i.updated_at AS inventory_updated_at
                FROM products p
                LEFT JOIN inventory i
                    ON p.product_id = i.product_id
                ORDER BY p.product_id
                """
            )

            products = cursor.fetchall()

        log_event(
            "INFO",
            "get_products",
            count=len(products)
        )

        return response(
            200,
            products
        )

    except Exception as error:

        log_event(
            "ERROR",
            "get_products_failed",
            error=str(error)
        )

        return response(
            500,
            {
                "message": "Failed to retrieve products"
            }
        )

    finally:

        if connection:
            connection.close()


# =========================================================
# GET PRODUCT BY ID
# GET /products/{id}
# =========================================================

def get_product(product_id):

    try:

        product_id = int(product_id)

    except (ValueError, TypeError):

        return response(
            400,
            {
                "message": "Invalid product ID"
            }
        )

    connection = None

    try:

        connection = get_connection()

        with connection.cursor() as cursor:

            cursor.execute(
                """
                SELECT
                    p.product_id,
                    p.name,
                    p.description,
                    p.price,
                    p.category,
                    p.created_at,
                    p.updated_at,
                    i.inventory_id,
                    i.stock_count,
                    i.low_stock_threshold,
                    i.updated_at AS inventory_updated_at
                FROM products p
                LEFT JOIN inventory i
                    ON p.product_id = i.product_id
                WHERE p.product_id = %s
                """,
                (product_id,)
            )

            product = cursor.fetchone()

        if not product:

            return response(
                404,
                {
                    "message": "Product not found"
                }
            )

        log_event(
            "INFO",
            "get_product",
            product_id=product_id
        )

        return response(
            200,
            product
        )

    except Exception as error:

        log_event(
            "ERROR",
            "get_product_failed",
            product_id=product_id,
            error=str(error)
        )

        return response(
            500,
            {
                "message": "Failed to retrieve product"
            }
        )

    finally:

        if connection:
            connection.close()


# =========================================================
# UPDATE PRODUCT
# PUT /products/{id}
# =========================================================

def update_product(product_id, event):

    try:

        product_id = int(product_id)

    except (ValueError, TypeError):

        return response(
            400,
            {
                "message": "Invalid product ID"
            }
        )

    body = get_request_body(event)

    name = body.get("name")
    description = body.get("description")
    price = body.get("price")
    category = body.get("category")
    stock_count = body.get("stock_count")
    low_stock_threshold = body.get(
        "low_stock_threshold"
    )

    if all(
        value is None
        for value in [
            name,
            description,
            price,
            category,
            stock_count,
            low_stock_threshold
        ]
    ):

        return response(
            400,
            {
                "message": (
                    "At least one field is "
                    "required for update"
                )
            }
        )

    connection = None

    try:

        connection = get_connection()

        with connection.cursor() as cursor:

            # ---------------------------------------------
            # Check product
            # ---------------------------------------------

            cursor.execute(
                """
                SELECT product_id
                FROM products
                WHERE product_id = %s
                """,
                (product_id,)
            )

            product = cursor.fetchone()

            if not product:

                return response(
                    404,
                    {
                        "message": "Product not found"
                    }
                )

            # ---------------------------------------------
            # Product updates
            # ---------------------------------------------

            updates = []
            values = []

            if name is not None:

                updates.append("name = %s")
                values.append(name)

            if description is not None:

                updates.append("description = %s")
                values.append(description)

            if price is not None:

                price = float(price)

                if price < 0:

                    return response(
                        400,
                        {
                            "message": (
                                "price cannot be negative"
                            )
                        }
                    )

                updates.append("price = %s")
                values.append(price)

            if category is not None:

                updates.append("category = %s")
                values.append(category)

            if updates:

                values.append(product_id)

                sql = f"""
                    UPDATE products
                    SET {", ".join(updates)}
                    WHERE product_id = %s
                """

                cursor.execute(
                    sql,
                    values
                )

            # ---------------------------------------------
            # Inventory updates
            # ---------------------------------------------

            inventory_updates = []
            inventory_values = []

            if stock_count is not None:

                stock_count = int(stock_count)

                if stock_count < 0:

                    return response(
                        400,
                        {
                            "message": (
                                "stock_count "
                                "cannot be negative"
                            )
                        }
                    )

                inventory_updates.append(
                    "stock_count = %s"
                )

                inventory_values.append(
                    stock_count
                )

            if low_stock_threshold is not None:

                low_stock_threshold = int(
                    low_stock_threshold
                )

                if low_stock_threshold < 0:

                    return response(
                        400,
                        {
                            "message": (
                                "low_stock_threshold "
                                "cannot be negative"
                            )
                        }
                    )

                inventory_updates.append(
                    "low_stock_threshold = %s"
                )

                inventory_values.append(
                    low_stock_threshold
                )

            if inventory_updates:

                inventory_values.append(
                    product_id
                )

                inventory_sql = f"""
                    UPDATE inventory
                    SET {", ".join(inventory_updates)}
                    WHERE product_id = %s
                """

                cursor.execute(
                    inventory_sql,
                    inventory_values
                )

        connection.commit()

        log_event(
            "INFO",
            "update_product",
            product_id=product_id,
            stock_changed=stock_count is not None
        )

        return response(
            200,
            {
                "message": "Product updated successfully",
                "product_id": product_id
            }
        )

    except Exception as error:

        if connection:
            connection.rollback()

        log_event(
            "ERROR",
            "update_product_failed",
            product_id=product_id,
            error=str(error)
        )

        return response(
            500,
            {
                "message": "Failed to update product"
            }
        )

    finally:

        if connection:
            connection.close()


# =========================================================
# DELETE PRODUCT
# DELETE /products/{id}
# =========================================================

def delete_product(product_id):

    try:

        product_id = int(product_id)

    except (ValueError, TypeError):

        return response(
            400,
            {
                "message": "Invalid product ID"
            }
        )

    connection = None

    try:

        connection = get_connection()

        with connection.cursor() as cursor:

            # Because your schema uses ON DELETE CASCADE,
            # deleting the product automatically deletes
            # its inventory record.

            cursor.execute(
                """
                DELETE FROM products
                WHERE product_id = %s
                """,
                (product_id,)
            )

            if cursor.rowcount == 0:

                connection.rollback()

                return response(
                    404,
                    {
                        "message": "Product not found"
                    }
                )

        connection.commit()

        log_event(
            "INFO",
            "delete_product",
            product_id=product_id
        )

        return response(
            200,
            {
                "message": "Product deleted successfully",
                "product_id": product_id
            }
        )

    except Exception as error:

        if connection:
            connection.rollback()

        log_event(
            "ERROR",
            "delete_product_failed",
            product_id=product_id,
            error=str(error)
        )

        return response(
            500,
            {
                "message": "Failed to delete product"
            }
        )

    finally:

        if connection:
            connection.close()


# =========================================================
# MAIN HANDLER
# =========================================================

def lambda_handler(event, context):

    log_event(
        "INFO",
        "request_received",
        request_id=context.aws_request_id
    )

    try:

        # -------------------------------------------------
        # HTTP METHOD
        # -------------------------------------------------

        http_method = (
            event.get("httpMethod")
            or event.get("requestContext", {})
            .get("http", {})
            .get("method")
        )

        http_method = (
            http_method.upper()
            if http_method
            else ""
        )

        # -------------------------------------------------
        # PATH PARAMETERS
        # -------------------------------------------------

        path_parameters = (
            event.get("pathParameters") or {}
        )

        product_id = path_parameters.get("id")

        # -------------------------------------------------
        # ROUTING
        # -------------------------------------------------

        if http_method == "POST":

            return create_product(event)

        elif http_method == "GET":

            if product_id:

                return get_product(product_id)

            return get_products()

        elif http_method == "PUT":

            if not product_id:

                return response(
                    400,
                    {
                        "message": (
                            "Product ID is required"
                        )
                    }
                )

            return update_product(
                product_id,
                event
            )

        elif http_method == "DELETE":

            if not product_id:

                return response(
                    400,
                    {
                        "message": (
                            "Product ID is required"
                        )
                    }
                )

            return delete_product(product_id)

        else:

            return response(
                405,
                {
                    "message": "Method not allowed"
                }
            )

    except ValueError as error:

        log_event(
            "ERROR",
            "invalid_request",
            error=str(error)
        )

        return response(
            400,
            {
                "message": str(error)
            }
        )

    except Exception as error:

        log_event(
            "ERROR",
            "unhandled_error",
            error=str(error)
        )

        return response(
            500,
            {
                "message": "Internal server error"
            }
        )