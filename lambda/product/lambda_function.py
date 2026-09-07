import json
import os

import boto3
import pymysql


# =========================================================
# AWS CLIENTS
# =========================================================

ssm = boto3.client("ssm")
events = boto3.client("events")


# =========================================================
# STRUCTURED LOGGING
# =========================================================

def log_event(event_name, **kwargs):

    log_data = {
        "event": event_name,
        **kwargs
    }

    print(
        json.dumps(
            log_data,
            default=str
        )
    )


# =========================================================
# GET PARAMETER FROM SSM
# =========================================================

def get_parameter(name):

    response = ssm.get_parameter(
        Name=name,
        WithDecryption=True
    )

    return response["Parameter"]["Value"]


# =========================================================
# GET DATABASE CREDENTIALS
# =========================================================

def get_database_credentials():

    environment = os.environ.get(
        "ENVIRONMENT",
        "dev"
    )

    prefix = f"/cloudmart/{environment}/db"

    return {

        "host": get_parameter(
            f"{prefix}/host"
        ),

        "port": int(
            get_parameter(
                f"{prefix}/port"
            )
        ),

        "database": get_parameter(
            f"{prefix}/name"
        ),

        "username": get_parameter(
            f"{prefix}/username"
        ),

        "password": get_parameter(
            f"{prefix}/password"
        )
    }


# =========================================================
# CONNECT TO RDS
# =========================================================

def get_connection():

    db = get_database_credentials()

    return pymysql.connect(

        host=db["host"],

        port=db["port"],

        user=db["username"],

        password=db["password"],

        database=db["database"],

        cursorclass=pymysql.cursors.DictCursor,

        connect_timeout=10,

        read_timeout=30,

        write_timeout=30
    )


# =========================================================
# PUBLISH INVENTORY UPDATED EVENT
# =========================================================

def publish_inventory_event(
    product_id,
    product_name,
    stock_count,
    low_stock_threshold
):

    event_bus_name = os.environ[
        "EVENT_BUS_NAME"
    ]

    event_detail = {

        "product_id":
            product_id,

        "product_name":
            product_name,

        "stock_count":
            stock_count,

        "low_stock_threshold":
            low_stock_threshold
    }

    response = events.put_events(

        Entries=[

            {

                "EventBusName":
                    event_bus_name,

                "Source":
                    "cloudmart.product",

                "DetailType":
                    "InventoryUpdated",

                "Detail":
                    json.dumps(
                        event_detail,
                        default=str
                    )
            }
        ]
    )

    if response["FailedEntryCount"] > 0:

        log_event(

            "inventory_event_publish_failed",

            product_id=product_id,

            response=response,

            status="failed"
        )

        raise RuntimeError(
            "Failed to publish InventoryUpdated event"
        )

    log_event(

        "inventory_event_published",

        product_id=product_id,

        product_name=product_name,

        stock_count=stock_count,

        low_stock_threshold=
            low_stock_threshold,

        event_bus=event_bus_name,

        status="success"
    )


# =========================================================
# HTTP RESPONSE
# =========================================================

def create_response(
    status_code,
    body
):

    return {

        "statusCode":
            status_code,

        "headers": {

            "Content-Type":
                "application/json"
        },

        "body":
            json.dumps(
                body,
                default=str
            )
    }


# =========================================================
# GET HTTP METHOD
# =========================================================

def get_http_method(event):

    method = event.get(
        "httpMethod"
    )

    if method:
        return method.upper()

    method = (
        event.get(
            "requestContext",
            {}
        )
        .get(
            "http",
            {}
        )
        .get(
            "method"
        )
    )

    if method:
        return method.upper()

    return None


# =========================================================
# GET PRODUCT ID
# =========================================================

def get_product_id(event):

    path_parameters = (
        event.get(
            "pathParameters"
        )
        or {}
    )

    return path_parameters.get(
        "id"
    )


# =========================================================
# PARSE REQUEST BODY
# =========================================================

def get_request_body(event):

    body = event.get(
        "body"
    )

    if not body:

        raise ValueError(
            "Request body is required"
        )

    if isinstance(
        body,
        str
    ):

        body = json.loads(
            body
        )

    if not isinstance(
        body,
        dict
    ):

        raise ValueError(
            "Request body must be a JSON object"
        )

    return body


# =========================================================
# LAMBDA HANDLER
# =========================================================

def lambda_handler(
    event,
    context
):

    connection = None

    try:

        # =================================================
        # REQUEST START
        # =================================================

        log_event(
            "product_request_started"
        )


        # =================================================
        # GET HTTP METHOD
        # =================================================

        http_method = get_http_method(
            event
        )

        if not http_method:

            return create_response(

                400,

                {
                    "message":
                        "HTTP method is missing"
                }
            )


        log_event(

            "http_method",

            method=http_method
        )


        # =================================================
        # GET PRODUCT ID
        # =================================================

        product_id = get_product_id(
            event
        )


        # =================================================
        # CONNECT TO RDS
        # =================================================

        connection = get_connection()

        log_event(

            "rds_connection",

            status="success"
        )


        # =================================================
        # DATABASE OPERATIONS
        # =================================================

        with connection.cursor() as cursor:


            # =================================================
            # GET ALL PRODUCTS
            # =================================================

            if (
                http_method == "GET"
                and not product_id
            ):

                cursor.execute(

                    """
                    SELECT
                        p.product_id,
                        p.name,
                        p.description,
                        p.price,
                        p.category,
                        i.stock_count,
                        i.low_stock_threshold,
                        p.created_at,
                        p.updated_at
                    FROM products p
                    LEFT JOIN inventory i
                        ON p.product_id =
                           i.product_id
                    WHERE p.is_deleted = FALSE
                    ORDER BY p.product_id
                    """
                )

                products = cursor.fetchall()

                log_event(

                    "products_retrieved",

                    count=len(products),

                    status="success"
                )

                return create_response(

                    200,

                    products
                )


            # =================================================
            # GET PRODUCT BY ID
            # =================================================

            if (
                http_method == "GET"
                and product_id
            ):

                cursor.execute(

                    """
                    SELECT
                        p.product_id,
                        p.name,
                        p.description,
                        p.price,
                        p.category,
                        i.stock_count,
                        i.low_stock_threshold,
                        p.created_at,
                        p.updated_at
                    FROM products p
                    LEFT JOIN inventory i
                        ON p.product_id =
                           i.product_id
                    WHERE p.product_id = %s
                      AND p.is_deleted = FALSE
                    """,

                    (product_id,)
                )

                product = cursor.fetchone()

                if not product:

                    log_event(

                        "product_not_found",

                        product_id=product_id
                    )

                    return create_response(

                        404,

                        {
                            "message":
                                "Product not found"
                        }
                    )

                log_event(

                    "product_retrieved",

                    product_id=product_id,

                    status="success"
                )

                return create_response(

                    200,

                    product
                )


            # =================================================
            # CREATE PRODUCT
            # =================================================

            if http_method == "POST":

                body = get_request_body(
                    event
                )


                # =================================================
                # PRODUCT FIELDS
                # =================================================

                name = body.get(
                    "name"
                )

                description = body.get(
                    "description"
                )

                price = body.get(
                    "price"
                )

                category = body.get(
                    "category"
                )


                # =================================================
                # INVENTORY FIELDS
                # =================================================

                stock_count = body.get(
                    "stock_count",
                    0
                )

                low_stock_threshold = body.get(
                    "low_stock_threshold",
                    10
                )


                # =================================================
                # VALIDATE NAME
                # =================================================

                if (
                    name is None
                    or not isinstance(
                        name,
                        str
                    )
                    or not name.strip()
                ):

                    return create_response(

                        400,

                        {
                            "message":
                                "name is required"
                        }
                    )

                name = name.strip()


                # =================================================
                # VALIDATE PRICE
                # =================================================

                if price is None:

                    return create_response(

                        400,

                        {
                            "message":
                                "price is required"
                        }
                    )


                if isinstance(
                    price,
                    bool
                ):

                    return create_response(

                        400,

                        {
                            "message":
                                "price must be a number"
                        }
                    )


                try:

                    price_value = float(
                        price
                    )

                except (
                    TypeError,
                    ValueError
                ):

                    return create_response(

                        400,

                        {
                            "message":
                                "price must be a number"
                        }
                    )


                if price_value <= 0:

                    return create_response(

                        400,

                        {
                            "message":
                                "price must be greater than 0"
                        }
                    )


                # =================================================
                # VALIDATE STOCK COUNT
                # =================================================

                if (
                    not isinstance(
                        stock_count,
                        int
                    )
                    or isinstance(
                        stock_count,
                        bool
                    )
                ):

                    return create_response(

                        400,

                        {
                            "message":
                                "stock_count must be an integer"
                        }
                    )


                if stock_count < 0:

                    return create_response(

                        400,

                        {
                            "message":
                                "stock_count cannot be negative"
                        }
                    )


                # =================================================
                # VALIDATE LOW STOCK THRESHOLD
                # =================================================

                if (
                    not isinstance(
                        low_stock_threshold,
                        int
                    )
                    or isinstance(
                        low_stock_threshold,
                        bool
                    )
                ):

                    return create_response(

                        400,

                        {
                            "message":
                                "low_stock_threshold "
                                "must be an integer"
                        }
                    )


                if low_stock_threshold < 0:

                    return create_response(

                        400,

                        {
                            "message":
                                "low_stock_threshold "
                                "cannot be negative"
                        }
                    )


                # =================================================
                # INSERT PRODUCT
                # =================================================

                cursor.execute(

                    """
                    INSERT INTO products
                    (
                        name,
                        description,
                        price,
                        category
                    )
                    VALUES
                    (
                        %s,
                        %s,
                        %s,
                        %s
                    )
                    """,

                    (
                        name,
                        description,
                        price_value,
                        category
                    )
                )


                new_product_id = (
                    cursor.lastrowid
                )


                # =================================================
                # INSERT INVENTORY
                # =================================================

                cursor.execute(

                    """
                    INSERT INTO inventory
                    (
                        product_id,
                        stock_count,
                        low_stock_threshold
                    )
                    VALUES
                    (
                        %s,
                        %s,
                        %s
                    )
                    """,

                    (
                        new_product_id,
                        stock_count,
                        low_stock_threshold
                    )
                )


                # =================================================
                # COMMIT
                # =================================================

                connection.commit()


                # =================================================
                # PUBLISH EVENT
                # =================================================

                publish_inventory_event(

                    product_id=
                        new_product_id,

                    product_name=
                        name,

                    stock_count=
                        stock_count,

                    low_stock_threshold=
                        low_stock_threshold
                )


                # =================================================
                # LOG
                # =================================================

                log_event(

                    "product_created",

                    product_id=
                        new_product_id,

                    stock_count=
                        stock_count,

                    low_stock_threshold=
                        low_stock_threshold,

                    status="success"
                )


                # =================================================
                # RESPONSE
                # =================================================

                return create_response(

                    201,

                    {

                        "message":
                            "Product created successfully",

                        "product_id":
                            new_product_id,

                        "stock_count":
                            stock_count,

                        "low_stock_threshold":
                            low_stock_threshold
                    }
                )


            # =================================================
            # UPDATE PRODUCT + INVENTORY
            # =================================================

            if (
                http_method == "PUT"
                and product_id
            ):

                body = get_request_body(
                    event
                )


                # =================================================
                # PRODUCT FIELDS
                # =================================================

                name = body.get(
                    "name"
                )

                description = body.get(
                    "description"
                )

                price = body.get(
                    "price"
                )

                category = body.get(
                    "category"
                )


                # =================================================
                # INVENTORY FIELDS
                # =================================================

                stock_count = body.get(
                    "stock_count"
                )

                low_stock_threshold = body.get(
                    "low_stock_threshold"
                )


                # =================================================
                # VALIDATE NAME
                # =================================================

                if (
                    name is None
                    or not isinstance(
                        name,
                        str
                    )
                    or not name.strip()
                ):

                    return create_response(

                        400,

                        {
                            "message":
                                "name is required"
                        }
                    )

                name = name.strip()


                # =================================================
                # VALIDATE PRICE
                # =================================================

                if price is not None:

                    if isinstance(
                        price,
                        bool
                    ):

                        return create_response(

                            400,

                            {
                                "message":
                                    "price must be a number"
                            }
                        )


                    try:

                        price_value = float(
                            price
                        )

                    except (
                        TypeError,
                        ValueError
                    ):

                        return create_response(

                            400,

                            {
                                "message":
                                    "price must be a number"
                            }
                        )


                    if price_value <= 0:

                        return create_response(

                            400,

                            {
                                "message":
                                    "price must be greater than 0"
                            }
                        )

                else:

                    price_value = None


                # =================================================
                # VALIDATE STOCK COUNT
                # =================================================

                if stock_count is not None:

                    if (
                        not isinstance(
                            stock_count,
                            int
                        )
                        or isinstance(
                            stock_count,
                            bool
                        )
                    ):

                        return create_response(

                            400,

                            {
                                "message":
                                    "stock_count "
                                    "must be an integer"
                            }
                        )


                    if stock_count < 0:

                        return create_response(

                            400,

                            {
                                "message":
                                    "stock_count "
                                    "cannot be negative"
                            }
                        )


                # =================================================
                # VALIDATE LOW STOCK THRESHOLD
                # =================================================

                if low_stock_threshold is not None:

                    if (
                        not isinstance(
                            low_stock_threshold,
                            int
                        )
                        or isinstance(
                            low_stock_threshold,
                            bool
                        )
                    ):

                        return create_response(

                            400,

                            {
                                "message":
                                    "low_stock_threshold "
                                    "must be an integer"
                            }
                        )


                    if low_stock_threshold < 0:

                        return create_response(

                            400,

                            {
                                "message":
                                    "low_stock_threshold "
                                    "cannot be negative"
                            }
                        )


                # =================================================
                # CHECK PRODUCT EXISTS
                # =================================================

                # IMPORTANT:
                #
                # Do NOT use cursor.rowcount from the UPDATE
                # to determine whether the product exists.
                #
                # MySQL can return rowcount = 0 when the new
                # values are exactly the same as the old values.
                #
                # Therefore we check existence FIRST.

                cursor.execute(

                    """
                    SELECT
                        product_id
                    FROM products
                    WHERE product_id = %s
                      AND is_deleted = FALSE
                    """,

                    (product_id,)
                )


                existing_product = (
                    cursor.fetchone()
                )


                if not existing_product:

                    connection.rollback()

                    log_event(

                        "product_not_found",

                        product_id=
                            product_id
                    )

                    return create_response(

                        404,

                        {
                            "message":
                                "Product not found"
                        }
                    )


                # =================================================
                # UPDATE PRODUCT
                # =================================================

                # Build the update dynamically so that if price,
                # description or category are not supplied, their
                # existing values remain unchanged.

                update_fields = [
                    "name = %s"
                ]

                update_values = [
                    name
                ]


                if description is not None:

                    update_fields.append(
                        "description = %s"
                    )

                    update_values.append(
                        description
                    )


                if price_value is not None:

                    update_fields.append(
                        "price = %s"
                    )

                    update_values.append(
                        price_value
                    )


                if category is not None:

                    update_fields.append(
                        "category = %s"
                    )

                    update_values.append(
                        category
                    )


                update_values.append(
                    product_id
                )


                product_update_sql = f"""
                    UPDATE products
                    SET
                        {", ".join(update_fields)}
                    WHERE product_id = %s
                      AND is_deleted = FALSE
                """


                cursor.execute(

                    product_update_sql,

                    tuple(
                        update_values
                    )
                )


                # =================================================
                # UPDATE INVENTORY
                # =================================================

                inventory_event = None


                if (
                    stock_count is not None
                    or low_stock_threshold is not None
                ):


                    # =================================================
                    # CHECK INVENTORY EXISTS
                    # =================================================

                    cursor.execute(

                        """
                        SELECT
                            inventory_id,
                            stock_count,
                            low_stock_threshold
                        FROM inventory
                        WHERE product_id = %s
                        """,

                        (product_id,)
                    )


                    existing_inventory = (
                        cursor.fetchone()
                    )


                    if not existing_inventory:

                        connection.rollback()

                        log_event(

                            "inventory_not_found",

                            product_id=
                                product_id
                        )

                        return create_response(

                            404,

                            {
                                "message":
                                    "Inventory record not found"
                            }
                        )


                    # =================================================
                    # UPDATE INVENTORY
                    # =================================================

                    inventory_fields = []

                    inventory_values = []


                    if stock_count is not None:

                        inventory_fields.append(
                            "stock_count = %s"
                        )

                        inventory_values.append(
                            stock_count
                        )


                    if low_stock_threshold is not None:

                        inventory_fields.append(
                            "low_stock_threshold = %s"
                        )

                        inventory_values.append(
                            low_stock_threshold
                        )


                    inventory_fields.append(
                        "updated_at = CURRENT_TIMESTAMP"
                    )


                    inventory_values.append(
                        product_id
                    )


                    inventory_update_sql = f"""
                        UPDATE inventory
                        SET
                            {", ".join(inventory_fields)}
                        WHERE product_id = %s
                    """


                    cursor.execute(

                        inventory_update_sql,

                        tuple(
                            inventory_values
                        )
                    )


                    # =================================================
                    # GET UPDATED INVENTORY
                    # =================================================

                    cursor.execute(

                        """
                        SELECT
                            p.name,
                            i.stock_count,
                            i.low_stock_threshold
                        FROM products p
                        JOIN inventory i
                            ON p.product_id =
                               i.product_id
                        WHERE p.product_id = %s
                          AND p.is_deleted = FALSE
                        """,

                        (product_id,)
                    )


                    inventory = (
                        cursor.fetchone()
                    )


                    if not inventory:

                        connection.rollback()

                        return create_response(

                            404,

                            {
                                "message":
                                    "Inventory information not found"
                            }
                        )


                    inventory_event = {

                        "product_id":
                            product_id,

                        "product_name":
                            inventory[
                                "name"
                            ],

                        "stock_count":
                            inventory[
                                "stock_count"
                            ],

                        "low_stock_threshold":
                            inventory[
                                "low_stock_threshold"
                            ]
                    }


                    log_event(

                        "inventory_updated",

                        product_id=
                            product_id,

                        stock_count=
                            inventory[
                                "stock_count"
                            ],

                        low_stock_threshold=
                            inventory[
                                "low_stock_threshold"
                            ],

                        status="success"
                    )


                # =================================================
                # COMMIT
                # =================================================

                connection.commit()


                # =================================================
                # PUBLISH INVENTORY EVENT
                # =================================================

                if inventory_event:

                    publish_inventory_event(

                        product_id=
                            inventory_event[
                                "product_id"
                            ],

                        product_name=
                            inventory_event[
                                "product_name"
                            ],

                        stock_count=
                            inventory_event[
                                "stock_count"
                            ],

                        low_stock_threshold=
                            inventory_event[
                                "low_stock_threshold"
                            ]
                    )


                # =================================================
                # LOG PRODUCT UPDATE
                # =================================================

                log_event(

                    "product_updated",

                    product_id=
                        product_id,

                    inventory_updated=(
                        stock_count is not None
                        or
                        low_stock_threshold is not None
                    ),

                    status="success"
                )


                # =================================================
                # RESPONSE
                # =================================================

                return create_response(

                    200,

                    {

                        "message":
                            "Product updated successfully",

                        "product_id":
                            product_id,

                        "inventory_updated": (
                            stock_count is not None
                            or
                            low_stock_threshold is not None
                        )
                    }
                )


            # =================================================
            # DELETE PRODUCT - SOFT DELETE
            # =================================================

            if (
                http_method == "DELETE"
                and product_id
            ):

                # First check product exists
                cursor.execute(

                    """
                    SELECT
                        product_id
                    FROM products
                    WHERE product_id = %s
                      AND is_deleted = FALSE
                    """,

                    (product_id,)
                )


                existing_product = (
                    cursor.fetchone()
                )


                if not existing_product:

                    connection.rollback()

                    log_event(

                        "product_not_found",

                        product_id=
                            product_id
                    )

                    return create_response(

                        404,

                        {
                            "message":
                                "Product not found"
                        }
                    )


                # =================================================
                # SOFT DELETE
                # =================================================

                cursor.execute(

                    """
                    UPDATE products
                    SET
                        is_deleted = TRUE
                    WHERE product_id = %s
                      AND is_deleted = FALSE
                    """,

                    (product_id,)
                )


                connection.commit()


                log_event(

                    "product_deleted",

                    product_id=
                        product_id,

                    status="success"
                )


                return create_response(

                    200,

                    {

                        "message":
                            "Product deleted successfully",

                        "product_id":
                            product_id
                    }
                )


            # =================================================
            # UNSUPPORTED METHOD
            # =================================================

            log_event(

                "method_not_allowed",

                method=http_method,

                product_id=product_id
            )


            return create_response(

                405,

                {
                    "message":
                        "Method not allowed"
                }
            )


    # =========================================================
    # INVALID JSON / REQUEST BODY
    # =========================================================

    except json.JSONDecodeError:

        log_event(

            "invalid_json",

            status="failed"
        )

        if connection:

            connection.rollback()

        return create_response(

            400,

            {
                "message":
                    "Invalid JSON body"
            }
        )


    # =========================================================
    # VALIDATION ERROR
    # =========================================================

    except ValueError as error:

        log_event(

            "validation_error",

            error=str(error),

            status="failed"
        )

        if connection:

            connection.rollback()

        return create_response(

            400,

            {
                "message":
                    str(error)
            }
        )


    # =========================================================
    # GENERAL ERROR
    # =========================================================

    except Exception as error:

        log_event(

            "product_request_failed",

            error=str(error),

            status="failed"
        )

        if connection:

            connection.rollback()

        return create_response(

            500,

            {
                "message":
                    "Internal server error"
            }
        )


    # =========================================================
    # CLOSE DATABASE CONNECTION
    # =========================================================

    finally:

        if connection:

            connection.close()