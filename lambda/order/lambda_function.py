import json
import os
import traceback

import boto3
import pymysql


# =========================================================
# AWS CLIENT
# =========================================================

ssm = boto3.client("ssm")
events_client = boto3.client("events")
cloudwatch = boto3.client("cloudwatch")

def log_error(event_name, error, **kwargs):
    """
    Write a structured CloudWatch error log.

    Never pass raw authorization tokens, passwords, token hashes,
    or other secrets through kwargs.
    """
    log_data = {
        "event": event_name,
        "error_type": type(error).__name__,
        "error": str(error)
    }
    log_data.update(kwargs)

    print(json.dumps(log_data))
    traceback.print_exc()



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
    """
    Retrieve a parameter from AWS SSM Parameter Store.

    WithDecryption=True allows SecureString parameters
    such as the database password to be decrypted.
    """

    try:
        response = ssm.get_parameter(
            Name=name,
            WithDecryption=True
        )

        return response["Parameter"]["Value"]

    except Exception as error:
        log_error(
            "ssm_parameter_fetch_failed",
            error,
            parameter_name=name
        )
        raise


# =========================================================
# GET DATABASE CREDENTIALS
# =========================================================

def get_database_credentials():
    """
    Get RDS connection details from SSM Parameter Store.

    Parameters:
        /cloudmart/{ENVIRONMENT}/db/host
        /cloudmart/{ENVIRONMENT}/db/port
        /cloudmart/{ENVIRONMENT}/db/name
        /cloudmart/{ENVIRONMENT}/db/username
        /cloudmart/{ENVIRONMENT}/db/password
    """

    prefix = f"/cloudmart/{ENVIRONMENT}/db"

    try:
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

    except Exception as error:
        log_error(
            "database_credentials_fetch_failed",
            error,
            parameter_prefix=prefix
        )
        raise


# =========================================================
# DATABASE CONNECTION
# =========================================================

def get_connection():
    """
    Create a connection to the RDS MySQL database.

    autocommit=False is important because an order can
    modify multiple database records and must be committed
    as one transaction.
    """

    db = get_database_credentials()

    try:
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

    except Exception as error:
        log_error(
            "rds_connection_failed",
            error,
            database=db["database"],
            port=db["port"]
        )
        raise


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
    """
    Read authenticated user information from the
    Lambda Authorizer context.

    Expected values:

        role
        user_id
    """

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
    detail,
    source="cloudmart.order"
):
    """
    Publish an event to the CloudMart EventBridge bus.
    """

    if not EVENT_BUS_NAME:

        print(json.dumps({
            "event": "eventbridge_skipped",
            "reason": "EVENT_BUS_NAME_not_configured",
            "detail_type": detail_type
        }))

        return

    event_entry = {

        "Source": source,

        "DetailType": detail_type,

        "Detail": json.dumps(detail),

        "EventBusName": EVENT_BUS_NAME
    }

    try:
        result = events_client.put_events(
            Entries=[event_entry]
        )

    except Exception as error:
        log_error(
            "eventbridge_publish_failed",
            error,
            detail_type=detail_type,
            source=source,
            event_bus=EVENT_BUS_NAME
        )
        raise

    failed_entry_count = result.get(
        "FailedEntryCount",
        0
    )

    print(json.dumps({
        "event": "eventbridge_event_published",
        "detail_type": detail_type,
        "failed_entry_count": failed_entry_count
    }))

    if failed_entry_count > 0:

        error = RuntimeError(
            f"EventBridge failed to publish {detail_type}"
        )

        log_error(
            "eventbridge_event_rejected",
            error,
            detail_type=detail_type,
            source=source,
            event_bus=EVENT_BUS_NAME,
            failed_entry_count=failed_entry_count
        )

        raise error



# =========================================================
# PUBLISH CUSTOM CLOUDWATCH METRIC
# =========================================================

def publish_metric(metric_name, value=1):
    """
    Publish a custom CloudWatch metric to the CloudMart namespace.

    Metric publication is best-effort and must not break a successful
    database transaction or API response if CloudWatch is temporarily
    unavailable.
    """

    try:
        cloudwatch.put_metric_data(
            Namespace="CloudMart",
            MetricData=[
                {
                    "MetricName": metric_name,
                    "Value": value,
                    "Unit": "Count"
                }
            ]
        )

        print(json.dumps({
            "event": "cloudwatch_metric_published",
            "metric_name": metric_name,
            "value": value
        }))

    except Exception as metric_error:
        log_error(
            "cloudwatch_metric_publish_failed",
            metric_error,
            metric_name=metric_name,
            metric_value=value
        )

# =========================================================
# VALIDATE CUSTOMER
# =========================================================

def validate_customer(
    cursor,
    customer_id
):
    """
    Confirm that the authenticated customer exists
    in the users table.
    """

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

    # =================================================
    # ROLE AUTHORIZATION
    # =================================================
    # ADMIN users are for monitoring/management and
    # cannot place customer orders.
    if authenticated_user["role"] == "ADMIN":
        return response(
            403,
            {
                "message":
                    "ADMIN users are not allowed to place orders"
            }
        )

    customer_id = authenticated_user["user_id"]

    order_id = None

    validated_items = []

    processed_items = []

    inventory_updates = []

    try:

        print(json.dumps({
            "event": "create_order_started",
            "customer_id": customer_id
        }))

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

        if not isinstance(
            body,
            dict
        ):

            return response(
                400,
                {
                    "message": "Request body must be a JSON object"
                }
            )


        # =================================================
        # GET ITEMS
        # =================================================

        items = body.get(
            "items"
        )

        if not isinstance(
            items,
            list
        ) or not items:

            return response(
                400,
                {
                    "message":
                        "items must be a non-empty array"
                }
            )


        # =================================================
        # VALIDATE ALL ITEMS
        # =================================================

        combined_items = {}

        for item in items:

            if not isinstance(
                item,
                dict
            ):

                return response(
                    400,
                    {
                        "message":
                            "Each item must be a JSON object"
                    }
                )

            product_id = item.get(
                "productId"
            )

            quantity = item.get(
                "quantity"
            )

            # ---------------------------------------------
            # PRODUCT ID REQUIRED
            # ---------------------------------------------

            if product_id is None:

                return response(
                    400,
                    {
                        "message":
                            "productId is required for every item"
                    }
                )

            # ---------------------------------------------
            # QUANTITY REQUIRED
            # ---------------------------------------------

            if quantity is None:

                return response(
                    400,
                    {
                        "message":
                            "quantity is required for every item"
                    }
                )

            # ---------------------------------------------
            # CONVERT PRODUCT ID
            # ---------------------------------------------

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
                        "message":
                            "productId must be an integer"
                    }
                )

            # ---------------------------------------------
            # CONVERT QUANTITY
            # ---------------------------------------------

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
                        "message":
                            "quantity must be an integer"
                    }
                )

            # ---------------------------------------------
            # VALIDATE PRODUCT ID
            # ---------------------------------------------

            if product_id <= 0:

                return response(
                    400,
                    {
                        "message":
                            "productId must be greater than 0"
                    }
                )

            # ---------------------------------------------
            # VALIDATE QUANTITY
            # ---------------------------------------------

            if quantity <= 0:

                return response(
                    400,
                    {
                        "message":
                            "quantity must be greater than 0"
                    }
                )

            # ---------------------------------------------
            # COMBINE DUPLICATE PRODUCT IDs
            # ---------------------------------------------

            if product_id in combined_items:

                combined_items[product_id] += quantity

            else:

                combined_items[product_id] = quantity


        # =================================================
        # CREATE FINAL VALIDATED ITEM LIST
        # =================================================

        validated_items = [
            {
                "product_id": product_id,
                "quantity": quantity
            }
            for product_id, quantity
            in combined_items.items()
        ]


        # =================================================
        # CONNECT TO RDS
        # =================================================

        connection = get_connection()

        print(json.dumps({
            "event": "rds_connection",
            "status": "success"
        }))


        # =================================================
        # START DATABASE TRANSACTION
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
            # GET PRODUCTS AND INVENTORY
            #
            # Products are processed in product_id order
            # to keep row-locking deterministic and reduce
            # deadlock risk when multiple orders run together.
            # =============================================

            sorted_items = sorted(
                validated_items,
                key=lambda x: x["product_id"]
            )


            for item in sorted_items:

                product_id = item["product_id"]

                quantity = item["quantity"]


                # -----------------------------------------
                # GET PRODUCT
                # -----------------------------------------

                cursor.execute(
                    """
                    SELECT
                        product_id,
                        name,
                        price
                    FROM products
                    WHERE product_id = %s
                        AND is_deleted = FALSE
                    """,
                    (product_id,)
                )

                product = cursor.fetchone()


                if not product:

                    raise ValueError(
                        f"Product {product_id} not found"
                    )


                # -----------------------------------------
                # GET AND LOCK INVENTORY
                # -----------------------------------------

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
                        f"Inventory not found for product {product_id}"
                    )


                # -----------------------------------------
                # CALCULATE SUBTOTAL
                # -----------------------------------------

                unit_price = product["price"]

                subtotal = (
                    unit_price * quantity
                )


                # -----------------------------------------
                # STORE PROCESSED ITEM
                # -----------------------------------------

                processed_items.append(
                    {
                        "product_id": product_id,
                        "product_name": product["name"],
                        "quantity": quantity,
                        "unit_price": unit_price,
                        "subtotal": subtotal,
                        "stock_before":
                            inventory["stock_count"],
                        "low_stock_threshold":
                            inventory["low_stock_threshold"]
                    }
                )


            # =============================================
            # CHECK STOCK FOR ALL PRODUCTS
            # =============================================

            insufficient_item = None

            for item in processed_items:

                if (
                    item["stock_before"]
                    < item["quantity"]
                ):

                    insufficient_item = item

                    break


            # =============================================
            # INSUFFICIENT STOCK
            #
            # No inventory is changed.
            #
            # A FAILED order is still stored so that the
            # failure can be tracked.
            # =============================================

            if insufficient_item:

                failure_reason = (
                    f"Insufficient stock for product "
                    f"{insufficient_item['product_id']}. "
                    f"Available: "
                    f"{insufficient_item['stock_before']}, "
                    f"Requested: "
                    f"{insufficient_item['quantity']}"
                )


                # -----------------------------------------
                # CALCULATE TOTAL
                # -----------------------------------------

                total_amount = sum(
                    item["subtotal"]
                    for item in processed_items
                )


                # -----------------------------------------
                # INSERT FAILED ORDER
                # -----------------------------------------

                cursor.execute(
                    """
                    INSERT INTO orders
                        (
                            customer_id,
                            total_amount,
                            status,
                            failure_reason
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
                        customer_id,
                        total_amount,
                        "FAILED",
                        failure_reason
                    )
                )

                order_id = cursor.lastrowid


                # -----------------------------------------
                # INSERT ORDER ITEMS
                # -----------------------------------------

                for item in processed_items:

                    cursor.execute(
                        """
                        INSERT INTO order_items
                            (
                                order_id,
                                product_id,
                                quantity,
                                unit_price,
                                subtotal
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
                            order_id,
                            item["product_id"],
                            item["quantity"],
                            item["unit_price"],
                            item["subtotal"]
                        )
                    )


                # -----------------------------------------
                # COMMIT FAILED ORDER
                # -----------------------------------------

                connection.commit()

                # -----------------------------------------
                # PUBLISH ORDERS FAILED METRIC
                # -----------------------------------------
                # The failed order has been committed to RDS,
                # so publish the metric only after the order is
                # successfully persisted.
                publish_metric("OrdersFailed", 1)


                print(json.dumps({
                    "event": "order_failed",
                    "order_id": order_id,
                    "customer_id": customer_id,
                    "reason": failure_reason
                }))


                # -----------------------------------------
                # ORDER FAILED EVENT
                # -----------------------------------------

                try:

                    publish_event(
                        "OrderFailed",
                        {
                            "order_id": order_id,
                            "customer_id": customer_id,

                            "items": [
                                {
                                    "product_id":
                                        item["product_id"],

                                    "quantity":
                                        item["quantity"],

                                    "unit_price":
                                        float(item["unit_price"]),

                                    "subtotal":
                                        float(item["subtotal"])
                                }

                                for item in processed_items
                            ],

                            "total_amount":
                                float(total_amount),

                            "status": "FAILED",

                            "reason":
                                failure_reason
                        }
                    )

                except Exception as event_error:

                    print(json.dumps({
                        "event":
                            "order_failed_event_error",

                        "order_id":
                            order_id,

                        "error":
                            str(event_error)
                    }))


                return response(
                    400,
                    {
                        "message":
                            "Order could not be processed",

                        "order_id":
                            order_id,

                        "status":
                            "FAILED",

                        "reason":
                            failure_reason
                    }
                )


            # =============================================
            # CALCULATE TOTAL ORDER AMOUNT
            # =============================================

            total_amount = sum(
                item["subtotal"]
                for item in processed_items
            )


            # =============================================
            # INSERT PENDING ORDER
            # =============================================

            cursor.execute(
                """
                INSERT INTO orders
                    (
                        customer_id,
                        total_amount,
                        status
                    )
                VALUES
                    (
                        %s,
                        %s,
                        %s
                    )
                """,
                (
                    customer_id,
                    total_amount,
                    "PENDING"
                )
            )

            order_id = cursor.lastrowid


            # =============================================
            # INSERT ORDER ITEMS
            # =============================================

            for item in processed_items:

                cursor.execute(
                    """
                    INSERT INTO order_items
                        (
                            order_id,
                            product_id,
                            quantity,
                            unit_price,
                            subtotal
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
                        order_id,
                        item["product_id"],
                        item["quantity"],
                        item["unit_price"],
                        item["subtotal"]
                    )
                )


            # =============================================
            # ORDER PLACED EVENT
            # =============================================

            publish_event(
                "OrderPlaced",
                {
                    "order_id":
                        order_id,

                    "customer_id":
                        customer_id,

                    "items": [
                        {
                            "product_id":
                                item["product_id"],

                            "product_name":
                                item["product_name"],

                            "quantity":
                                item["quantity"],

                            "unit_price":
                                float(item["unit_price"]),

                            "subtotal":
                                float(item["subtotal"])
                        }

                        for item in processed_items
                    ],

                    "total_amount":
                        float(total_amount),

                    "status":
                        "PENDING"
                }
            )


            # =============================================
            # DEDUCT INVENTORY FOR EVERY PRODUCT
            # =============================================

            for item in processed_items:

                new_stock = (
                    item["stock_before"]
                    - item["quantity"]
                )


                cursor.execute(
                    """
                    UPDATE inventory
                    SET stock_count = %s
                    WHERE product_id = %s
                    """,
                    (
                        new_stock,
                        item["product_id"]
                    )
                )


                inventory_updates.append(
                    {
                        "product_id":
                            item["product_id"],

                        "product_name":
                            item["product_name"],

                        "stock_count":
                            new_stock,

                        "low_stock_threshold":
                            item["low_stock_threshold"]
                    }
                )


            # =============================================
            # UPDATE ORDER
            # PENDING → CONFIRMED
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
            # COMMIT COMPLETE TRANSACTION
            # =============================================

            connection.commit()

        # =================================================
        # PUBLISH ORDERS PLACED METRIC
        # =================================================
        # Publish only after the complete order transaction
        # has been committed successfully.
        publish_metric("OrdersPlaced", 1)


        # =================================================
        # INVENTORY UPDATED EVENTS
        #
        # One event is published for every product whose
        # inventory changed.
        # =================================================

        for inventory_update in inventory_updates:

            publish_event(
                "InventoryUpdated",
                inventory_update,
                source="cloudmart.product"
            )


        # =================================================
        # ORDER CONFIRMED EVENT
        # =================================================

        publish_event(
            "OrderConfirmed",
            {
                "order_id":
                    order_id,

                "customer_id":
                    customer_id,

                "customer_email":
                    customer["email"],

                "items": [
                    {
                        "product_id":
                            item["product_id"],

                        "product_name":
                            item["product_name"],

                        "quantity":
                            item["quantity"],

                        "unit_price":
                            float(item["unit_price"]),

                        "subtotal":
                            float(item["subtotal"])
                    }

                    for item in processed_items
                ],

                "total_amount":
                    float(total_amount),

                "stock_remaining": [
                    {
                        "product_id":
                            update["product_id"],

                        "stock_count":
                            update["stock_count"]
                    }

                    for update in inventory_updates
                ],

                "status":
                    "CONFIRMED"
            }
        )


        # =================================================
        # LOW STOCK LOGGING
        # =================================================

        for inventory_update in inventory_updates:

            if (
                inventory_update["stock_count"]
                <= inventory_update["low_stock_threshold"]
            ):

                print(json.dumps({
                    "event":
                        "low_stock_after_order",

                    "product_id":
                        inventory_update["product_id"],

                    "product_name":
                        inventory_update["product_name"],

                    "stock_count":
                        inventory_update["stock_count"],

                    "low_stock_threshold":
                        inventory_update["low_stock_threshold"]
                }))


        # =================================================
        # SUCCESS LOG
        # =================================================

        print(json.dumps({
            "event":
                "order_created",

            "order_id":
                order_id,

            "customer_id":
                customer_id,

            "item_count":
                len(processed_items),

            "total_amount":
                float(total_amount),

            "status":
                "CONFIRMED"
        }))


        # =================================================
        # SUCCESS RESPONSE
        # =================================================

        return response(
            201,
            {
                "message":
                    "Order placed successfully",

                "order": {
                    "order_id":
                        order_id,

                    "customer_id":
                        customer_id,

                    "items": [
                        {
                            "product_id":
                                item["product_id"],

                            "product_name":
                                item["product_name"],

                            "quantity":
                                item["quantity"],

                            "unit_price":
                                float(item["unit_price"]),

                            "subtotal":
                                float(item["subtotal"]),

                            "stock_remaining":
                                inventory_updates[
                                    index
                                ]["stock_count"]
                        }

                        for index, item
                        in enumerate(processed_items)
                    ],

                    "total_amount":
                        float(total_amount),

                    "status":
                        "CONFIRMED"
                }
            }
        )


    # =====================================================
    # INVALID JSON
    # =====================================================

    except json.JSONDecodeError:

        if connection:

            connection.rollback()

        return response(
            400,
            {
                "message":
                    "Invalid JSON request body"
            }
        )


    # =====================================================
    # VALIDATION / BUSINESS ERROR
    # =====================================================

    except ValueError as error:

        if connection:

            connection.rollback()


        print(json.dumps({
            "event":
                "order_failed",

            "reason":
                str(error),

            "customer_id":
                customer_id
        }))


        # ---------------------------------------------
        # ORDER FAILED EVENT
        # ---------------------------------------------

        try:

            publish_event(
                "OrderFailed",
                {
                    "order_id":
                        order_id,

                    "customer_id":
                        customer_id,

                    "items": [
                        {
                            "product_id":
                                item["product_id"],

                            "quantity":
                                item["quantity"]
                        }

                        for item in validated_items
                    ],

                    "status":
                        "FAILED",

                    "reason":
                        str(error)
                }
            )

        except Exception as event_error:

            print(json.dumps({
                "event":
                    "order_failed_event_error",

                "error":
                    str(event_error)
            }))


        return response(
            400,
            {
                "message":
                    "Order could not be processed",

                "reason":
                    str(error)
            }
        )


    # =====================================================
    # UNEXPECTED ERROR
    # =====================================================

    except Exception as error:

        if connection:

            connection.rollback()


        print(json.dumps({
            "event":
                "order_processing_failed",

            "customer_id":
                customer_id,

            "error":
                str(error)
        }))


        # ---------------------------------------------
        # ORDER FAILED EVENT
        # ---------------------------------------------

        try:

            publish_event(
                "OrderFailed",
                {
                    "order_id":
                        order_id,

                    "customer_id":
                        customer_id,

                    "items": [
                        {
                            "product_id":
                                item["product_id"],

                            "quantity":
                                item["quantity"]
                        }

                        for item in validated_items
                    ],

                    "status":
                        "FAILED",

                    "reason":
                        str(error)
                }
            )

        except Exception as event_error:

            print(json.dumps({
                "event":
                    "order_failed_event_error",

                "error":
                    str(event_error)
            }))


        return response(
            500,
            {
                "message":
                    "Internal server error"
            }
        )


    # =====================================================
    # CLOSE DATABASE CONNECTION
    # =====================================================

    finally:

        if connection:

            connection.close()

# =========================================================
# CANCEL ORDER
# PATCH /orders/{id}
# =========================================================
def cancel_order(
    event,
    authenticated_user
):
    connection = None

    try:

        print(json.dumps({
            "event": "cancel_order_started",
            "user_id": authenticated_user.get("user_id"),
            "role": authenticated_user.get("role")
        }))

        # =================================================
        # GET ORDER ID
        # =================================================
        path_parameters = (
            event.get("pathParameters")
            or {}
        )

        order_id = path_parameters.get("id")

        if not order_id:
            return response(
                400,
                {
                    "message": "Order ID is required"
                }
            )

        try:
            order_id = int(order_id)

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

        # =================================================
        # GET REQUEST BODY
        # =================================================
        body = event.get("body")

        if not body:
            return response(
                400,
                {
                    "message": "Request body is required"
                }
            )

        try:
            body = json.loads(body)

        except json.JSONDecodeError:
            return response(
                400,
                {
                    "message": "Request body must be valid JSON"
                }
            )

        requested_status = body.get("status")

        if requested_status != "CANCELLED":
            return response(
                400,
                {
                    "message":
                        "Only status CANCELLED is supported"
                }
            )

        # =================================================
        # CONNECT TO RDS
        # =================================================
        connection = get_connection()

        print(json.dumps({
            "event": "cancel_order_rds_connection",
            "status": "success",
            "order_id": order_id
        }))

        # =================================================
        # START TRANSACTION
        # =================================================
        with connection.cursor() as cursor:

            # =============================================
            # GET ORDER AND LOCK IT
            # =============================================
            cursor.execute(
                """
                SELECT
                    order_id,
                    customer_id,
                    total_amount,
                    status
                FROM orders
                WHERE order_id = %s
                FOR UPDATE
                """,
                (order_id,)
            )

            order = cursor.fetchone()

            # =============================================
            # ORDER NOT FOUND
            # =============================================
            if not order:
                connection.rollback()

                return response(
                    404,
                    {
                        "message": "Order not found"
                    }
                )

            # =============================================
            # ROLE AND OWNERSHIP AUTHORIZATION
            # =============================================

            # ADMIN users cannot cancel orders.
            if authenticated_user["role"] == "ADMIN":
                connection.rollback()

                return response(
                    403,
                    {
                        "message":
                            "ADMIN users are not allowed to cancel orders"
                    }
                )

            # USER can cancel only their own order.
            if order["customer_id"] != authenticated_user["user_id"]:
                connection.rollback()

                return response(
                    403,
                    {
                        "message":
                            "You are not allowed to cancel this order"
                    }
                )

            # =============================================
            # CHECK CURRENT STATUS
            # =============================================
            current_status = order["status"]

            if current_status == "CANCELLED":

                connection.rollback()

                return response(
                    409,
                    {
                        "message":
                            "Order is already cancelled",
                        "order_id": order_id,
                        "status": current_status
                    }
                )

            if current_status not in (
                "PENDING",
                "CONFIRMED"
            ):

                connection.rollback()

                return response(
                    409,
                    {
                        "message":
                            "Order cannot be cancelled",
                        "order_id": order_id,
                        "status": current_status
                    }
                )

            # =============================================
            # GET ORDER ITEMS
            # =============================================
            cursor.execute(
                """
                SELECT
                    order_item_id,
                    product_id,
                    quantity
                FROM order_items
                WHERE order_id = %s
                ORDER BY product_id
                """,
                (order_id,)
            )

            order_items = cursor.fetchall()

            if not order_items:

                connection.rollback()

                return response(
                    409,
                    {
                        "message":
                            "Order has no items to restore"
                    }
                )

            # =============================================
            # RESTORE INVENTORY
            #
            # FOR UPDATE prevents another transaction
            # from changing the same inventory row while
            # cancellation is in progress.
            # =============================================
            restored_items = []

            for item in order_items:

                product_id = item["product_id"]
                quantity = item["quantity"]

                cursor.execute(
                    """
                    SELECT
                        inventory_id,
                        product_id,
                        stock_count
                    FROM inventory
                    WHERE product_id = %s
                    FOR UPDATE
                    """,
                    (product_id,)
                )

                inventory = cursor.fetchone()

                if not inventory:

                    raise ValueError(
                        f"Inventory not found for product {product_id}"
                    )

                old_stock = inventory["stock_count"]

                new_stock = (
                    old_stock + quantity
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

                restored_items.append({
                    "product_id": product_id,
                    "quantity_restored": quantity,
                    "old_stock": old_stock,
                    "new_stock": new_stock
                })

            # =============================================
            # UPDATE ORDER STATUS
            # =============================================
            cursor.execute(
                """
                UPDATE orders
                SET status = %s
                WHERE order_id = %s
                """,
                (
                    "CANCELLED",
                    order_id
                )
            )

            # =============================================
            # COMMIT TRANSACTION
            # =============================================
            connection.commit()

            # =================================================
            # PUBLISH ORDERS CANCELLED METRIC
            # =================================================
            try:

                cloudwatch.put_metric_data(
                    Namespace="CloudMart",
                    MetricData=[
                        {
                            "MetricName": "OrdersCancelled",
                            "Value": 1,
                            "Unit": "Count"
                        }
                    ]
                )

                print(json.dumps({
                    "event": "orders_cancelled_metric_published",
                    "order_id": order_id
                }))

            except Exception as metric_error:

                log_error(
                    "orders_cancelled_metric_error",
                    metric_error,
                    order_id=order_id,
                    metric_name="OrdersCancelled"
                )



        

        # =================================================
        # LOG SUCCESS
        # =================================================
        print(json.dumps({
            "event": "order_cancelled",
            "order_id": order_id,
            "customer_id": order["customer_id"],
            "previous_status": current_status,
            "status": "CANCELLED",
            "restored_items": restored_items
        }))

        # =================================================
        # PUBLISH ORDER CANCELLED EVENT
        # =================================================
        try:

            publish_event(
                "OrderCancelled",
                {
                    "order_id": order_id,
                    "customer_id": order["customer_id"],
                    "total_amount": float(
                        order["total_amount"]
                    ),
                    "previous_status": current_status,
                    "status": "CANCELLED",
                    "items": [
                        {
                            "product_id":
                                item["product_id"],
                            "quantity":
                                item["quantity"]
                        }
                        for item in order_items
                    ]
                }
            )

        except Exception as event_error:

            log_error(
                "order_cancelled_event_error",
                event_error,
                order_id=order_id,
                detail_type="OrderCancelled"
            )

        # =================================================
        # PUBLISH INVENTORY UPDATED EVENTS
        # =================================================
        for item in restored_items:

            try:

                publish_event(
                    "InventoryUpdated",
                    {
                        "product_id":
                            item["product_id"],
                        "stock_count":
                            item["new_stock"],
                        "change":
                            item["quantity_restored"],
                        "reason":
                            "ORDER_CANCELLED",
                        "order_id":
                            order_id
                    }
                )

            except Exception as event_error:

                log_error(
                    "inventory_updated_event_error",
                    event_error,
                    order_id=order_id,
                    product_id=item["product_id"],
                    detail_type="InventoryUpdated"
                )

        # =================================================
        # RESPONSE
        # =================================================
        return response(
            200,
            {
                "message":
                    "Order cancelled successfully",
                "order_id":
                    order_id,
                "status":
                    "CANCELLED",
                "restored_items":
                    restored_items
            }
        )

    except Exception as error:

        # =============================================
        # ROLLBACK
        # =============================================
        if connection:
            try:
                connection.rollback()
            except Exception as rollback_error:
                log_error(
                    "cancel_order_rollback_failed",
                    rollback_error,
                    order_id=locals().get("order_id")
                )

        log_error(
            "cancel_order_failed",
            error,
            order_id=locals().get("order_id")
        )

        return response(
            500,
            {
                "message":
                    "Internal server error"
            }
        )

    finally:

        if connection:
            try:
                connection.close()
            except Exception as close_error:
                log_error(
                    "database_connection_close_failed",
                    close_error
                )

# =========================================================
# GET ORDER BY ID
# =========================================================

def get_order_by_id(
    event,
    authenticated_user
):

    connection = None

    try:

        # =================================================
        # GET ORDER ID
        # =================================================

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
                    "message":
                        "Order ID is required"
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
                    "message":
                        "Order ID must be an integer"
                }
            )


        # =================================================
        # CONNECT TO RDS
        # =================================================

        connection = get_connection()


        with connection.cursor() as cursor:

            # =============================================
            # GET ORDER
            # =============================================

            cursor.execute(
                """
                SELECT
                    o.order_id,
                    o.customer_id,
                    u.name AS customer_name,
                    u.email AS customer_email,
                    o.total_amount,
                    o.status,
                    o.failure_reason,
                    o.created_at,
                    o.updated_at
                FROM orders o

                INNER JOIN users u
                    ON o.customer_id = u.user_id

                WHERE o.order_id = %s
                """,
                (order_id,)
            )

            order = cursor.fetchone()


            # =============================================
            # ORDER NOT FOUND
            # =============================================

            if not order:

                return response(
                    404,
                    {
                        "message":
                            "Order not found"
                    }
                )


            # =============================================
            # USER CAN ONLY VIEW OWN ORDER
            # =============================================

            if (
                authenticated_user["role"]
                != "ADMIN"

                and order["customer_id"]
                != authenticated_user["user_id"]
            ):

                return response(
                    403,
                    {
                        "message":
                            "You are not allowed to view this order"
                    }
                )


            # =============================================
            # GET ORDER ITEMS
            # =============================================

            cursor.execute(
                """
                SELECT
                    oi.order_item_id,
                    oi.product_id,
                    p.name AS product_name,
                    oi.quantity,
                    oi.unit_price,
                    oi.subtotal
                FROM order_items oi

                INNER JOIN products p
                    ON oi.product_id = p.product_id

                WHERE oi.order_id = %s

                ORDER BY oi.order_item_id
                """,
                (order_id,)
            )

            items = cursor.fetchall()


        # =================================================
        # CONVERT DATETIME
        # =================================================

        if order.get(
            "created_at"
        ):

            order["created_at"] = (
                order["created_at"].isoformat()
            )


        if order.get(
            "updated_at"
        ):

            order["updated_at"] = (
                order["updated_at"].isoformat()
            )


        # =================================================
        # CONVERT DECIMAL VALUES
        # =================================================

        order["total_amount"] = float(
            order["total_amount"]
        )


        for item in items:

            item["unit_price"] = float(
                item["unit_price"]
            )

            item["subtotal"] = float(
                item["subtotal"]
            )


        # =================================================
        # ADD ITEMS TO ORDER
        # =================================================

        order["items"] = items


        # =================================================
        # RESPONSE
        # =================================================

        return response(
            200,
            {
                "order":
                    order
            }
        )


    except Exception as error:

        print(json.dumps({
            "event":
                "get_order_failed",

            "error":
                str(error)
        }))


        return response(
            500,
            {
                "message":
                    "Internal server error"
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

        print(json.dumps({
            "event": "get_orders_started",
            "user_id": authenticated_user.get("user_id"),
            "role": authenticated_user.get("role")
        }))

        # =================================================
        # GET QUERY PARAMETERS
        # =================================================

        query_parameters = event.get(
            "queryStringParameters"
        ) or {}

        requested_customer_id = (
            query_parameters.get(
                "customerId"
            )
        )


        # =================================================
        # DETERMINE CUSTOMER FILTER
        # =================================================

        if authenticated_user["role"] == "ADMIN":

            # ---------------------------------------------
            # ADMIN CAN FILTER BY CUSTOMER
            # ---------------------------------------------

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

                # ADMIN WITHOUT FILTER → ALL ORDERS

                customer_id = None


        else:

            # ---------------------------------------------
            # USER CAN ONLY SEE OWN ORDERS
            # ---------------------------------------------

            customer_id = (
                authenticated_user["user_id"]
            )


        # =================================================
        # CONNECT TO DATABASE
        # =================================================

        connection = get_connection()


        with connection.cursor() as cursor:

            # =================================================
            # GET ORDERS
            # =================================================

            if customer_id is None:

                # -----------------------------------------
                # ADMIN → ALL ORDERS
                # -----------------------------------------

                cursor.execute(
                    """
                    SELECT
                        o.order_id,
                        o.customer_id,
                        u.name AS customer_name,
                        u.email AS customer_email,
                        o.total_amount,
                        o.status,
                        o.failure_reason,
                        o.created_at,
                        o.updated_at

                    FROM orders o

                    INNER JOIN users u
                        ON o.customer_id = u.user_id

                    ORDER BY o.created_at DESC
                    """
                )

            else:

                # -----------------------------------------
                # USER → OWN ORDERS
                #
                # ADMIN → REQUESTED CUSTOMER ORDERS
                # -----------------------------------------

                cursor.execute(
                    """
                    SELECT
                        o.order_id,
                        o.customer_id,
                        u.name AS customer_name,
                        u.email AS customer_email,
                        o.total_amount,
                        o.status,
                        o.failure_reason,
                        o.created_at,
                        o.updated_at

                    FROM orders o

                    INNER JOIN users u
                        ON o.customer_id = u.user_id

                    WHERE o.customer_id = %s

                    ORDER BY o.created_at DESC
                    """,
                    (customer_id,)
                )


            orders = cursor.fetchall()


            # =================================================
            # GET ITEMS FOR EVERY ORDER
            # =================================================

            for order in orders:

                cursor.execute(
                    """
                    SELECT
                        oi.order_item_id,
                        oi.product_id,
                        p.name AS product_name,
                        oi.quantity,
                        oi.unit_price,
                        oi.subtotal

                    FROM order_items oi

                    INNER JOIN products p
                        ON oi.product_id = p.product_id

                    WHERE oi.order_id = %s

                    ORDER BY oi.order_item_id
                    """,
                    (order["order_id"],)
                )

                order_items = cursor.fetchall()


                # -----------------------------------------
                # ADD ITEMS TO ORDER
                # -----------------------------------------

                order["items"] = order_items


        # =================================================
        # CONVERT VALUES
        # =================================================

        for order in orders:

            if order.get(
                "created_at"
            ):

                order["created_at"] = (
                    order["created_at"].isoformat()
                )


            if order.get(
                "updated_at"
            ):

                order["updated_at"] = (
                    order["updated_at"].isoformat()
                )


            order["total_amount"] = float(
                order["total_amount"]
            )


            for item in order["items"]:

                item["unit_price"] = float(
                    item["unit_price"]
                )

                item["subtotal"] = float(
                    item["subtotal"]
                )


        # =================================================
        # RESPONSE
        # =================================================

        return response(
            200,
            {
                "count":
                    len(orders),

                "orders":
                    orders
            }
        )


    except Exception as error:

        print(json.dumps({
            "event":
                "get_orders_failed",

            "error":
                str(error)
        }))


        return response(
            500,
            {
                "message":
                    "Internal server error"
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
        "event":
            "order_request_started",

        "http_method":
            event.get("httpMethod"),

        "path":
            event.get("path")
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
            "event":
                "authenticated_user",

            "user_id":
                authenticated_user["user_id"],

            "role":
                authenticated_user["role"]
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
        # PATCH /orders/{id}
        # CANCEL ORDER
        # =================================================
        if (
            http_method == "PATCH"
            and event.get("pathParameters")
            and event[
                "pathParameters"
            ].get("id")
        ):
            return cancel_order(
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
                "message":
                    "Order endpoint not found"
            }
        )


    except Exception as error:

        print(json.dumps({
            "event":
                "order_request_failed",

            "error":
                str(error)
        }))


        return response(
            500,
            {
                "message":
                    "Internal server error"
            }
        )
