import json
import os

import boto3
import pymysql


# =========================================================
# AWS SSM CLIENT
# =========================================================

ssm = boto3.client("ssm")


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
# HTTP RESPONSE
# =========================================================

def create_response(status_code, body):

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

def lambda_handler(event, context):

    connection = None

    try:

        print(
            json.dumps({
                "event": "product_request_started"
            })
        )

        # =================================================
        # GET HTTP METHOD
        # =================================================

        http_method = event.get("httpMethod")

        # Support HTTP API payload format
        if not http_method:

            http_method = (
                event.get("requestContext", {})
                .get("http", {})
                .get("method")
            )

        print(
            json.dumps({
                "event": "http_method",
                "method": http_method
            })
        )


        # =================================================
        # GET PATH PARAMETERS
        # =================================================

        path_parameters = (
            event.get("pathParameters")
            or {}
        )

        product_id = path_parameters.get("id")


        # =================================================
        # CONNECT TO RDS
        # =================================================

        connection = get_connection()

        print(
            json.dumps({
                "event": "rds_connection",
                "status": "success"
            })
        )


        # =================================================
        # DATABASE OPERATIONS
        # =================================================

        with connection.cursor() as cursor:


            # =============================================
            # GET ALL PRODUCTS
            # GET /products
            # =============================================

            if http_method == "GET" and not product_id:

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
            # GET /products/{id}
            # =============================================

            if http_method == "GET" and product_id:

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
            # POST /products
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


                name = body.get("name")

                description = body.get(
                    "description"
                )

                price = body.get("price")

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
            # UPDATE PRODUCT
            # PUT /products/{id}
            # =============================================

            if http_method == "PUT" and product_id:

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


                name = body.get("name")

                description = body.get(
                    "description"
                )

                price = body.get("price")

                category = body.get(
                    "category"
                )


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


                connection.commit()


                if cursor.rowcount == 0:

                    return create_response(
                        404,
                        {
                            "message":
                                "Product not found"
                        }
                    )


                return create_response(
                    200,
                    {
                        "message":
                            "Product updated successfully"
                    }
                )


            # =============================================
            # DELETE PRODUCT
            # DELETE /products/{id}
            # =============================================

            if http_method == "DELETE" and product_id:

                cursor.execute(
                    """
                    DELETE FROM products
                    WHERE product_id = %s
                    """,
                    (product_id,)
                )


                connection.commit()


                if cursor.rowcount == 0:

                    return create_response(
                        404,
                        {
                            "message":
                                "Product not found"
                        }
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
                    str(error)
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