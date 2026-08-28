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

        "host":
            get_parameter(
                f"{prefix}/host"
            ),

        "port":
            int(
                get_parameter(
                    f"{prefix}/port"
                )
            ),

        "database":
            get_parameter(
                f"{prefix}/name"
            ),

        "username":
            get_parameter(
                f"{prefix}/username"
            ),

        "password":
            get_parameter(
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
    quantity,
    reorder_level
):

    event_bus_name = os.environ[
        "EVENT_BUS_NAME"
    ]

    event_detail = {

        "product_id":
            product_id,

        "product_name":
            product_name,

        "quantity":
            quantity,

        "reorder_level":
            reorder_level
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
                        event_detail
                    )
            }
        ]
    )

    if response["FailedEntryCount"] > 0:

        print(
            json.dumps({

                "event":
                    "inventory_event_publish_failed",

                "product_id":
                    product_id,

                "response":
                    response
            })
        )

        raise RuntimeError(
            "Failed to publish InventoryUpdated event"
        )


    print(
        json.dumps({

            "event":
                "inventory_event_published",

            "product_id":
                product_id,

            "quantity":
                quantity,

            "reorder_level":
                reorder_level,

            "status":
                "success"
        })
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
# LAMBDA HANDLER
# =========================================================

def lambda_handler(
    event,
    context
):

    connection = None

    try:

        print(
            json.dumps({

                "event":
                    "product_request_started"
            })
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


        print(
            json.dumps({

                "event":
                    "http_method",

                "method":
                    http_method
            })
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

        print(
            json.dumps({

                "event":
                    "rds_connection",

                "status":
                    "success"
            })
        )


        # =================================================
        # DATABASE OPERATIONS
        # =================================================

        with connection.cursor() as cursor:


            # =============================================
            # GET ALL PRODUCTS
            # =============================================

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

                return create_response(
                    200,
                    products
                )


            # =============================================
            # GET PRODUCT BY ID
            # =============================================

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

                    return create_response(

                        404,

                        {
                            "message":
                                "Product not found"
                        }
                    )

                return create_response(
                    200,
                    product
                )


            # =============================================
            # CREATE PRODUCT
            # =============================================

            if http_method == "POST":

                body = event.get("body")

                if not body:

                    return create_response(

                        400,

                        {
                            "message":
                                "Request body is required"
                        }
                    )


                if isinstance(body, str):

                    body = json.loads(body)


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


                print(
                    json.dumps({

                        "event":
                            "product_created",

                        "product_id":
                            new_product_id,

                        "status":
                            "success"
                    })
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


            # =============================================
            # UPDATE PRODUCT + INVENTORY
            # =============================================

            if (
                http_method == "PUT"
                and product_id
            ):

                body = event.get("body")

                if not body:

                    return create_response(

                        400,

                        {
                            "message":
                                "Request body is required"
                        }
                    )


                if isinstance(body, str):

                    body = json.loads(body)


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

                quantity = body.get(
                    "quantity"
                )


                # -----------------------------------------
                # UPDATE PRODUCT
                # -----------------------------------------

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

                    return create_response(

                        404,

                        {
                            "message":
                                "Product not found"
                        }
                    )


                inventory_event = None


                # -----------------------------------------
                # UPDATE INVENTORY
                # -----------------------------------------

                if quantity is not None:

                    cursor.execute(

                        """
                        UPDATE inventory
                        SET
                            quantity = %s,
                            updated_at =
                                CURRENT_TIMESTAMP
                        WHERE product_id = %s
                        """,

                        (
                            quantity,
                            product_id
                        )
                    )


                    if cursor.rowcount == 0:

                        connection.rollback()

                        return create_response(

                            404,

                            {
                                "message":
                                    "Inventory record not found"
                            }
                        )


                    # -------------------------------------
                    # GET INVENTORY DETAILS
                    # -------------------------------------

                    cursor.execute(

                        """
                        SELECT
                            p.name,
                            i.quantity,
                            i.reorder_level
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

                        "quantity":
                            inventory["quantity"],

                        "reorder_level":
                            inventory["reorder_level"]
                    }


                # -----------------------------------------
                # COMMIT
                # -----------------------------------------

                connection.commit()


                # -----------------------------------------
                # PUBLISH EVENT
                # -----------------------------------------

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

                        quantity=
                            inventory_event[
                                "quantity"
                            ],

                        reorder_level=
                            inventory_event[
                                "reorder_level"
                            ]
                    )


                print(
                    json.dumps({

                        "event":
                            "product_updated",

                        "product_id":
                            product_id,

                        "inventory_updated":
                            quantity is not None,

                        "status":
                            "success"
                    })
                )


                return create_response(

                    200,

                    {

                        "message":
                            "Product updated successfully",

                        "inventory_updated":
                            quantity is not None
                    }
                )


            # =============================================
            # DELETE PRODUCT
            # =============================================

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

                    return create_response(

                        404,

                        {
                            "message":
                                "Product not found"
                        }
                    )


                connection.commit()


                print(
                    json.dumps({

                        "event":
                            "product_deleted",

                        "product_id":
                            product_id,

                        "status":
                            "success"
                    })
                )


                return create_response(

                    200,

                    {

                        "message":
                            "Product deleted successfully"
                    }
                )


            # =============================================
            # UNSUPPORTED METHOD
            # =============================================

            return create_response(

                405,

                {
                    "message":
                        "Method not allowed"
                }
            )


    # =====================================================
    # INVALID JSON
    # =====================================================

    except json.JSONDecodeError:

        print(
            json.dumps({

                "event":
                    "invalid_json",

                "status":
                    "failed"
            })
        )

        return create_response(

            400,

            {
                "message":
                    "Invalid JSON body"
            }
        )


    # =====================================================
    # GENERAL ERROR
    # =====================================================

    except Exception as error:

        print(
            json.dumps({

                "event":
                    "product_request_failed",

                "error":
                    str(error),

                "status":
                    "failed"
            })
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


    # =====================================================
    # CLOSE CONNECTION
    # =====================================================

    finally:

        if connection:

            connection.close()