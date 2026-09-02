import json
import os

import boto3
import pymysql


# =========================================================
# AWS CLIENT
# =========================================================

ssm = boto3.client("ssm")
events_client = boto3.client("events")


# =========================================================
# ENVIRONMENT VARIABLES
# =========================================================

ENVIRONMENT = os.environ.get(
    "ENVIRONMENT",
    "dev"
)

EVENT_BUS_NAME = os.environ.get(
    "EVENT_BUS_NAME"
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

    prefix = f"/cloudmart/{ENVIRONMENT}/db"

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
# DATABASE CONNECTION
# =========================================================

def get_connection():

    db = get_database_credentials()

    return pymysql.connect(
        host=db["host"],
        port=db["port"],
        user=db["username"],
        password=db["password"],
        database=db["database"],
        connect_timeout=10,
        read_timeout=30,
        write_timeout=30,
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=False
    )


# =========================================================
# RESPONSE HELPER
# =========================================================

def response(status_code, body):

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
# GET AUTHENTICATED USER
# =========================================================

def get_authorizer_context(event):

    request_context = event.get(
        "requestContext",
        {}
    )

    authorizer = request_context.get(
        "authorizer",
        {}
    )

    role = authorizer.get(
        "role"
    )

    user_id = authorizer.get(
        "user_id"
    )

    if not role or not user_id:

        raise Exception(
            "Authenticated user information is missing"
        )

    return {
        "role": str(role).upper(),
        "user_id": int(user_id)
    }


# =========================================================
# PUBLISH EVENT TO EVENTBRIDGE
# =========================================================

def publish_event(
    detail_type,
    detail
):

    if not EVENT_BUS_NAME:

        print(json.dumps({
            "event": "eventbridge_skipped",
            "reason": "EVENT_BUS_NAME_not_configured",
            "detail_type": detail_type
        }))

        return

    event_entry = {

        "Source": "cloudmart.order",

        "DetailType": detail_type,

        "Detail": json.dumps(detail),

        "EventBusName": EVENT_BUS_NAME
    }

    result = events_client.put_events(
        Entries=[event_entry]
    )

    print(json.dumps({
        "event": "eventbridge_event_published",
        "detail_type": detail_type,
        "failed_entry_count": result.get(
            "FailedEntryCount",
            0
        )
    }))

    if result.get(
        "FailedEntryCount",
        0
    ) > 0:

        raise Exception(
            f"EventBridge failed to publish {detail_type}"
        )


# =========================================================
# VALIDATE CUSTOMER
# =========================================================

def validate_customer(
    cursor,
    customer_id
):

    cursor.execute(
        """
        SELECT
            user_id,
            name,
            email,
            role
        FROM users
        WHERE user_id = %s
        """,
        (customer_id,)
    )

    customer = cursor.fetchone()

    if not customer:

        raise ValueError(
            "Customer not found"
        )

    return customer


# =========================================================
# CREATE ORDER
# =========================================================

def create_order(
    event,
    authenticated_user
):

    connection = None

    customer_id = authenticated_user["user_id"]

    product_id = None

    quantity = None

    order_id = None

    try:

        # =================================================
        # READ REQUEST BODY
        # =================================================

        body = event.get(
            "body"
        )

        if not body:

            return response(
                400,
                {
                    "message": "Request body is required"
                }
            )

        if isinstance(
            body,
            str
        ):

            body = json.loads(body)


        # =================================================
        # GET PRODUCT ID
        # =================================================

        product_id = body.get(
            "productId"
        )

        quantity = body.get(
            "quantity"
        )


        # =================================================
        # VALIDATE PRODUCT ID
        # =================================================

        if product_id is None:

            return response(
                400,
                {
                    "message": "productId is required"
                }
            )

        try:

            product_id = int(
                product_id
            )

        except (
            TypeError,
            ValueError
        ):

            return response(
                400,
                {
                    "message": "productId must be an integer"
                }
            )


        # =================================================
        # VALIDATE QUANTITY
        # =================================================

        try:

            quantity = int(
                quantity
            )

        except (
            TypeError,
            ValueError
        ):

            return response(
                400,
                {
                    "message": "quantity must be an integer"
                }
            )

        if quantity <= 0:

            return response(
                400,
                {
                    "message": "quantity must be greater than 0"
                }
            )


        # =================================================
        # CONNECT TO RDS
        # =================================================

        connection = get_connection()

        print(json.dumps({
            "event": "rds_connection",
            "status": "success"
        }))


        # =================================================
        # START TRANSACTION
        # =================================================

        with connection.cursor() as cursor:

            # =============================================
            # VALIDATE CUSTOMER
            # =============================================

            customer = validate_customer(
                cursor,
                customer_id
            )


            # =============================================
            # GET PRODUCT
            # =============================================

            cursor.execute(
                """
                SELECT
                    product_id,
                    name,
                    price
                FROM products
                WHERE product_id = %s
                """,
                (product_id,)
            )

            product = cursor.fetchone()

            if not product:

                raise ValueError(
                    "Product not found"
                )


            # =============================================
            # GET INVENTORY
            #
            # FOR UPDATE locks the inventory row while
            # this transaction is running.
            # =============================================

            cursor.execute(
                """
                SELECT
                    inventory_id,
                    product_id,
                    stock_count,
                    low_stock_threshold
                FROM inventory
                WHERE product_id = %s
                FOR UPDATE
                """,
                (product_id,)
            )

            inventory = cursor.fetchone()

            if not inventory:

                raise ValueError(
                    "Inventory not found for product"
                )


            # =============================================
            # CHECK STOCK
            # =============================================

            if inventory["stock_count"] < quantity:

                raise ValueError(
                    f"Insufficient stock. "
                    f"Available: {inventory['stock_count']}, "
                    f"Requested: {quantity}"
                )


            # =============================================
            # CALCULATE TOTAL
            # =============================================

            total_amount = (
                product["price"]
                * quantity
            )


            # =============================================
            # INSERT PENDING ORDER
            # =============================================

            cursor.execute(
                """
                INSERT INTO orders
                    (
                        customer_id,
                        product_id,
                        quantity,
                        total_amount,
                        status
                    )
                VALUES
                    (
                        %s,
                        %s,
                        %s,
                        %s,
                        %s
                    )
                """,
                (
                    customer_id,
                    product_id,
                    quantity,
                    total_amount,
                    "PENDING"
                )
            )

            order_id = cursor.lastrowid


            # =============================================
            # ORDER PLACED EVENT
            # =============================================

            publish_event(
                "OrderPlaced",
                {
                    "order_id": order_id,
                    "customer_id": customer_id,
                    "product_id": product_id,
                    "quantity": quantity,
                    "total_amount": float(
                        total_amount
                    ),
                    "status": "PENDING"
                }
            )


            # =============================================
            # DEDUCT INVENTORY
            # =============================================

            new_stock = (
                inventory["stock_count"]
                - quantity
            )

            cursor.execute(
                """
                UPDATE inventory
                SET stock_count = %s
                WHERE product_id = %s
                """,
                (
                    new_stock,
                    product_id
                )
            )


            # =============================================
            # UPDATE ORDER TO CONFIRMED
            # =============================================

            cursor.execute(
                """
                UPDATE orders
                SET status = %s
                WHERE order_id = %s
                """,
                (
                    "CONFIRMED",
                    order_id
                )
            )


            # =============================================
            # COMMIT DATABASE TRANSACTION
            # =============================================

            connection.commit()


        # =================================================
        # ORDER CONFIRMED EVENT
        # =================================================

        publish_event(
            "OrderConfirmed",
            {
                "order_id": order_id,
                "customer_id": customer_id,
                "customer_email": customer["email"],
                "product_id": product_id,
                "product_name": product["name"],
                "quantity": quantity,
                "total_amount": float(
                    total_amount
                ),
                "stock_remaining": new_stock,
                "status": "CONFIRMED"
            }
        )


        # =================================================
        # LOW STOCK LOGGING
        # =================================================

        if (
            new_stock
            <= inventory["low_stock_threshold"]
        ):

            print(json.dumps({
                "event": "low_stock_after_order",
                "product_id": product_id,
                "product_name": product["name"],
                "stock_count": new_stock,
                "low_stock_threshold":
                    inventory[
                        "low_stock_threshold"
                    ]
            }))


        # =================================================
        # SUCCESS RESPONSE
        # =================================================

        print(json.dumps({
            "event": "order_created",
            "order_id": order_id,
            "customer_id": customer_id,
            "product_id": product_id,
            "quantity": quantity,
            "status": "CONFIRMED"
        }))

        return response(
            201,
            {
                "message": "Order placed successfully",

                "order": {
                    "order_id": order_id,
                    "customer_id": customer_id,
                    "product_id": product_id,
                    "product_name": product["name"],
                    "quantity": quantity,
                    "total_amount": float(
                        total_amount
                    ),
                    "status": "CONFIRMED",
                    "stock_remaining": new_stock
                }
            }
        )


    except json.JSONDecodeError:

        if connection:

            connection.rollback()

        return response(
            400,
            {
                "message": "Invalid JSON request body"
            }
        )


    except ValueError as error:

        if connection:

            connection.rollback()

        print(json.dumps({
            "event": "order_failed",
            "reason": str(error),
            "customer_id": customer_id,
            "product_id": product_id,
            "quantity": quantity
        }))

        # ===============================================
        # PUBLISH ORDER FAILED EVENT
        # ===============================================

        try:

            publish_event(
                "OrderFailed",
                {
                    "order_id": order_id,
                    "customer_id": customer_id,
                    "product_id": product_id,
                    "quantity": quantity,
                    "status": "FAILED",
                    "reason": str(error)
                }
            )

        except Exception as event_error:

            print(json.dumps({
                "event": "order_failed_event_error",
                "error": str(event_error)
            }))

        return response(
            400,
            {
                "message": "Order could not be processed",
                "reason": str(error)
            }
        )


    except Exception as error:

        if connection:

            connection.rollback()

        print(json.dumps({
            "event": "order_processing_failed",
            "customer_id": customer_id,
            "product_id": product_id,
            "quantity": quantity,
            "error": str(error)
        }))

        # ===============================================
        # PUBLISH ORDER FAILED EVENT
        # ===============================================

        try:

            publish_event(
                "OrderFailed",
                {
                    "order_id": order_id,
                    "customer_id": customer_id,
                    "product_id": product_id,
                    "quantity": quantity,
                    "status": "FAILED",
                    "reason": str(error)
                }
            )

        except Exception as event_error:

            print(json.dumps({
                "event": "order_failed_event_error",
                "error": str(event_error)
            }))

        return response(
            500,
            {
                "message": "Internal server error"
            }
        )


    finally:

        if connection:

            connection.close()


# =========================================================
# GET ORDER BY ID
# =========================================================

def get_order_by_id(
    event,
    authenticated_user
):

    connection = None

    try:

        path_parameters = event.get(
            "pathParameters"
        ) or {}

        order_id = path_parameters.get(
            "id"
        )

        if not order_id:

            return response(
                400,
                {
                    "message": "Order ID is required"
                }
            )

        try:

            order_id = int(
                order_id
            )

        except (
            TypeError,
            ValueError
        ):

            return response(
                400,
                {
                    "message": "Order ID must be an integer"
                }
            )


        connection = get_connection()

        with connection.cursor() as cursor:

            cursor.execute(
                """
                SELECT
                    o.order_id,
                    o.customer_id,
                    u.name AS customer_name,
                    u.email AS customer_email,
                    o.product_id,
                    p.name AS product_name,
                    p.price,
                    o.quantity,
                    o.total_amount,
                    o.status,
                    o.created_at,
                    o.updated_at
                FROM orders o

                INNER JOIN users u
                    ON o.customer_id = u.user_id

                INNER JOIN products p
                    ON o.product_id = p.product_id

                WHERE o.order_id = %s
                """,
                (order_id,)
            )

            order = cursor.fetchone()


        if not order:

            return response(
                404,
                {
                    "message": "Order not found"
                }
            )


        # =================================================
        # USER CAN ONLY VIEW OWN ORDER
        # =================================================

        if (
            authenticated_user["role"]
            != "ADMIN"
            and order["customer_id"]
            != authenticated_user["user_id"]
        ):

            return response(
                403,
                {
                    "message": "You are not allowed to view this order"
                }
            )


        # =================================================
        # CONVERT DATETIME
        # =================================================

        if order.get("created_at"):

            order["created_at"] = (
                order["created_at"]
                .isoformat()
            )

        if order.get("updated_at"):

            order["updated_at"] = (
                order["updated_at"]
                .isoformat()
            )


        return response(
            200,
            {
                "order": order
            }
        )


    except Exception as error:

        print(json.dumps({
            "event": "get_order_failed",
            "error": str(error)
        }))

        return response(
            500,
            {
                "message": "Internal server error"
            }
        )


    finally:

        if connection:

            connection.close()


# =========================================================
# GET ORDERS
# =========================================================

def get_orders(
    event,
    authenticated_user
):

    connection = None

    try:

        query_parameters = event.get(
            "queryStringParameters"
        ) or {}

        requested_customer_id = (
            query_parameters.get(
                "customerId"
            )
        )


        # =================================================
        # DETERMINE CUSTOMER ID
        # =================================================

        if authenticated_user["role"] == "ADMIN":

            if requested_customer_id:

                try:

                    customer_id = int(
                        requested_customer_id
                    )

                except (
                    TypeError,
                    ValueError
                ):

                    return response(
                        400,
                        {
                            "message":
                                "customerId must be an integer"
                        }
                    )

            else:

                customer_id = None

        else:

            # USER can only query their own orders.

            customer_id = (
                authenticated_user["user_id"]
            )


        # =================================================
        # CONNECT TO DATABASE
        # =================================================

        connection = get_connection()

        with connection.cursor() as cursor:

            # =============================================
            # ADMIN → ALL ORDERS
            # =============================================

            if customer_id is None:

                cursor.execute(
                    """
                    SELECT
                        o.order_id,
                        o.customer_id,
                        u.name AS customer_name,
                        u.email AS customer_email,
                        o.product_id,
                        p.name AS product_name,
                        o.quantity,
                        o.total_amount,
                        o.status,
                        o.created_at,
                        o.updated_at
                    FROM orders o

                    INNER JOIN users u
                        ON o.customer_id = u.user_id

                    INNER JOIN products p
                        ON o.product_id = p.product_id

                    ORDER BY o.created_at DESC
                    """
                )

            else:

                cursor.execute(
                    """
                    SELECT
                        o.order_id,
                        o.customer_id,
                        u.name AS customer_name,
                        u.email AS customer_email,
                        o.product_id,
                        p.name AS product_name,
                        o.quantity,
                        o.total_amount,
                        o.status,
                        o.created_at,
                        o.updated_at
                    FROM orders o

                    INNER JOIN users u
                        ON o.customer_id = u.user_id

                    INNER JOIN products p
                        ON o.product_id = p.product_id

                    WHERE o.customer_id = %s

                    ORDER BY o.created_at DESC
                    """,
                    (customer_id,)
                )

            orders = cursor.fetchall()


        # =================================================
        # CONVERT DATETIME VALUES
        # =================================================

        for order in orders:

            if order.get("created_at"):

                order["created_at"] = (
                    order["created_at"]
                    .isoformat()
                )

            if order.get("updated_at"):

                order["updated_at"] = (
                    order["updated_at"]
                    .isoformat()
                )


        return response(
            200,
            {
                "count": len(orders),
                "orders": orders
            }
        )


    except Exception as error:

        print(json.dumps({
            "event": "get_orders_failed",
            "error": str(error)
        }))

        return response(
            500,
            {
                "message": "Internal server error"
            }
        )


    finally:

        if connection:

            connection.close()


# =========================================================
# LAMBDA HANDLER
# =========================================================

def lambda_handler(
    event,
    context
):

    print(json.dumps({
        "event": "order_request_started",
        "http_method": event.get(
            "httpMethod"
        ),
        "path": event.get(
            "path"
        )
    }))


    try:

        # =================================================
        # GET AUTHENTICATED USER
        # =================================================

        authenticated_user = (
            get_authorizer_context(
                event
            )
        )

        print(json.dumps({
            "event": "authenticated_user",
            "user_id":
                authenticated_user[
                    "user_id"
                ],
            "role":
                authenticated_user[
                    "role"
                ]
        }))


        # =================================================
        # GET HTTP METHOD
        # =================================================

        http_method = (
            event.get(
                "httpMethod"
            )
            or event.get(
                "requestContext",
                {}
            ).get(
                "http",
                {}
            ).get(
                "method"
            )
        )

        http_method = (
            http_method.upper()
            if http_method
            else ""
        )


        # =================================================
        # GET PATH
        # =================================================

        path = event.get(
            "path",
            ""
        )


        # =================================================
        # POST /orders
        # =================================================

        if (
            http_method == "POST"
            and path == "/orders"
        ):

            return create_order(
                event,
                authenticated_user
            )


        # =================================================
        # GET /orders/{id}
        # =================================================

        if (
            http_method == "GET"
            and event.get(
                "pathParameters"
            )
            and event[
                "pathParameters"
            ].get("id")
        ):

            return get_order_by_id(
                event,
                authenticated_user
            )


        # =================================================
        # GET /orders
        # =================================================

        if (
            http_method == "GET"
            and path == "/orders"
        ):

            return get_orders(
                event,
                authenticated_user
            )


        # =================================================
        # INVALID ROUTE
        # =================================================

        return response(
            404,
            {
                "message": "Order endpoint not found"
            }
        )


    except Exception as error:

        print(json.dumps({
            "event": "order_request_failed",
            "error": str(error)
        }))

        return response(
            500,
            {
                "message": "Internal server error"
            }
        )