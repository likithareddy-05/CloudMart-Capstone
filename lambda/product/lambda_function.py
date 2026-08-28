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

    print(json.dumps(log_data, default=str))


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
# PUBLISH INVENTORY EVENT
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

        "product_id": product_id,

        "product_name": product_name,

        "stock_count": stock_count,

        "low_stock_threshold": low_stock_threshold
    }

    response = events.put_events(

        Entries=[

            {
                "EventBusName": event_bus_name,

                "Source": "cloudmart.product",

                "DetailType": "InventoryUpdated",

                "Detail": json.dumps(
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

        low_stock_threshold=low_stock_threshold,

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

        "statusCode": status_code,

        "headers": {

            "Content-Type": "application/json"
        },

        "body": json.dumps(
            body,
            default=str
        )
    }


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

        http_method = event.get(
            "httpMethod"
        )

        if not http_method:

            http_method = (
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


        if not http_method:

            return create_response(
                400,
                {
                    "message": "HTTP method is missing"
                }
            )


        http_method = http_method.upper()


        log_event(
            "http_method",
            method=http_method
        )


        # =================================================
        # GET PATH PARAMETERS
        # =================================================

        path_parameters = (
            event.get(
                "pathParameters"
            )
            or {}
        )

        product_id = path_parameters.get(
            "id"
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
                        product_id,
                        name,
                        description,
                        price,
                        category,
                        created_at,
                        updated_at
                    FROM products
                    ORDER BY product_id
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
                        product_id,
                        name,
                        description,
                        price,
                        category,
                        created_at,
                        updated_at
                    FROM products
                    WHERE product_id = %s
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
                            "message": "Product not found"
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

                body = event.get(
                    "body"
                )

                if not body:

                    return create_response(
                        400,
                        {
                            "message":
                                "Request body is required"
                        }
                    )


                if isinstance(
                    body,
                    str
                ):

                    body = json.loads(
                        body
                    )


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


                if not name:

                    return create_response(
                        400,
                        {
                            "message":
                                "name is required"
                        }
                    )


                if price is None:

                    return create_response(
                        400,
                        {
                            "message":
                                "price is required"
                        }
                    )


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
                        price,
                        category
                    )
                )


                connection.commit()

                new_product_id = cursor.lastrowid


                log_event(
                    "product_created",

                    product_id=new_product_id,

                    status="success"
                )


                return create_response(
                    201,
                    {
                        "message":
                            "Product created successfully",

                        "product_id":
                            new_product_id
                    }
                )


            # =================================================
            # UPDATE PRODUCT + INVENTORY
            # =================================================

            if (
                http_method == "PUT"
                and product_id
            ):

                body = event.get(
                    "body"
                )

                if not body:

                    return create_response(
                        400,
                        {
                            "message":
                                "Request body is required"
                        }
                    )


                if isinstance(
                    body,
                    str
                ):

                    body = json.loads(
                        body
                    )


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
                # INVENTORY FIELD
                #
                # Correct database column:
                # stock_count
                #
                # quantity is also accepted as a backwards-
                # compatible API field.
                # =================================================

                stock_count = body.get(
                    "stock_count"
                )

                if stock_count is None:

                    stock_count = body.get(
                        "quantity"
                    )


                # =================================================
                # UPDATE PRODUCT
                # =================================================

                cursor.execute(
                    """
                    UPDATE products
                    SET
                        name = %s,
                        description = %s,
                        price = %s,
                        category = %s
                    WHERE product_id = %s
                    """,
                    (
                        name,
                        description,
                        price,
                        category,
                        product_id
                    )
                )


                if cursor.rowcount == 0:

                    connection.rollback()

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


                inventory_event = None


                # =================================================
                # UPDATE INVENTORY
                # =================================================

                if stock_count is not None:

                    cursor.execute(
                        """
                        UPDATE inventory
                        SET
                            stock_count = %s,
                            updated_at =
                                CURRENT_TIMESTAMP
                        WHERE product_id = %s
                        """,
                        (
                            stock_count,
                            product_id
                        )
                    )


                    if cursor.rowcount == 0:

                        connection.rollback()

                        log_event(
                            "inventory_not_found",

                            product_id=product_id
                        )

                        return create_response(
                            404,
                            {
                                "message":
                                    "Inventory record not found"
                            }
                        )


                    # =================================================
                    # GET INVENTORY DETAILS
                    #
                    # Correct database columns:
                    #
                    # stock_count
                    # low_stock_threshold
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
                        """,
                        (product_id,)
                    )


                    inventory = cursor.fetchone()


                    if not inventory:

                        connection.rollback()

                        log_event(
                            "inventory_information_not_found",

                            product_id=product_id
                        )

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
                            inventory["name"],

                        "stock_count":
                            inventory["stock_count"],

                        "low_stock_threshold":
                            inventory[
                                "low_stock_threshold"
                            ]
                    }


                    log_event(
                        "inventory_updated",

                        product_id=product_id,

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
                # COMMIT DATABASE CHANGES
                # =================================================

                connection.commit()


                # =================================================
                # PUBLISH EVENT
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
                # PRODUCT UPDATE LOG
                # =================================================

                log_event(
                    "product_updated",

                    product_id=product_id,

                    inventory_updated=
                        stock_count is not None,

                    status="success"
                )


                return create_response(
                    200,
                    {
                        "message":
                            "Product updated successfully",

                        "product_id":
                            product_id,

                        "inventory_updated":
                            stock_count is not None
                    }
                )


            # =================================================
            # DELETE PRODUCT
            # =================================================

            if (
                http_method == "DELETE"
                and product_id
            ):

                cursor.execute(
                    """
                    DELETE FROM products
                    WHERE product_id = %s
                    """,
                    (product_id,)
                )


                if cursor.rowcount == 0:

                    connection.rollback()

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


                connection.commit()


                log_event(
                    "product_deleted",

                    product_id=product_id,

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
    # INVALID JSON
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