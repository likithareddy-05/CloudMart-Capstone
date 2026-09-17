import csv
import io
import json
import os
import traceback
from datetime import datetime, timezone

import boto3
import pymysql


s3 = boto3.client("s3")
cloudwatch = boto3.client("cloudwatch")
ssm = boto3.client("ssm")


REPORTS_BUCKET = os.environ["REPORTS_BUCKET"]

DB_HOST_PARAMETER = os.environ["DB_HOST_PARAMETER"]
DB_PORT_PARAMETER = os.environ["DB_PORT_PARAMETER"]
DB_NAME_PARAMETER = os.environ["DB_NAME_PARAMETER"]
DB_USERNAME_PARAMETER = os.environ["DB_USERNAME_PARAMETER"]
DB_PASSWORD_PARAMETER = os.environ["DB_PASSWORD_PARAMETER"]


def log_event(event_name, **details):
    log_data = {
        "event": event_name,
        **details
    }

    print(
        json.dumps(
            log_data,
            default=str
        )
    )


def log_error(event_name, error, **details):
    log_data = {
        "event": event_name,
        "error_type": type(error).__name__,
        "error": str(error),
        **details
    }

    print(
        json.dumps(
            log_data,
            default=str
        )
    )

    print(
        json.dumps(
            {
                "event": f"{event_name}_traceback",
                "traceback": traceback.format_exc()
            },
            default=str
        )
    )


def get_parameter(name, with_decryption=False):
    log_event(
        "ssm_parameter_fetch_started",
        parameter_name=name
    )

    try:
        response = ssm.get_parameter(
            Name=name,
            WithDecryption=with_decryption
        )
    except Exception as error:
        log_error(
            "ssm_parameter_fetch_failed",
            error,
            parameter_name=name
        )
        raise

    log_event(
        "ssm_parameter_fetch_succeeded",
        parameter_name=name
    )

    return response["Parameter"]["Value"]


def get_db_connection():
    log_event("database_connection_setup_started")

    try:
        db_host = get_parameter(
            DB_HOST_PARAMETER
        )
        log_event("database_host_parameter_retrieved")

        db_port = int(
            get_parameter(
                DB_PORT_PARAMETER
            )
        )
        log_event("database_port_parameter_retrieved")

        db_name = get_parameter(
            DB_NAME_PARAMETER
        )
        log_event("database_name_parameter_retrieved")

        db_username = get_parameter(
            DB_USERNAME_PARAMETER
        )
        log_event("database_username_parameter_retrieved")

        db_password = get_parameter(
            DB_PASSWORD_PARAMETER,
            with_decryption=True
        )
        log_event("database_password_parameter_retrieved")

    except Exception as error:
        log_error(
            "database_credentials_fetch_failed",
            error,
            parameter_group="database_parameters"
        )
        raise

    log_event(
        "rds_connection_started",
        database_name=db_name,
        port=db_port
    )

    try:
        connection = pymysql.connect(
            host=db_host,
            port=db_port,
            user=db_username,
            password=db_password,
            database=db_name,
            cursorclass=pymysql.cursors.DictCursor,
            connect_timeout=10
        )
    except Exception as error:
        log_error(
            "rds_connection_failed",
            error,
            database_name=db_name,
            port=db_port
        )
        raise

    log_event(
        "rds_connection_succeeded",
        database_name=db_name
    )

    return connection


def publish_metric(metric_name, value):
    log_event(
        "cloudwatch_metric_publish_started",
        metric_name=metric_name,
        value=value,
        namespace="CloudMart"
    )

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
    except Exception as error:
        log_error(
            "cloudwatch_metric_publish_failed",
            error,
            metric_name=metric_name,
            value=value,
            namespace="CloudMart"
        )
        raise

    log_event(
        "cloudwatch_metric_publish_succeeded",
        metric_name=metric_name,
        value=value,
        namespace="CloudMart"
    )


def generate_report():

    log_event("report_generation_started")

    connection = get_db_connection()

    log_event("database_connection_obtained")

    try:
        with connection.cursor() as cursor:

            log_event("database_cursor_created")

            log_event(
                "products_query_started",
                operation="fetch_products_and_inventory"
            )

            try:
                cursor.execute("""
                    SELECT
                        p.product_id,
                        p.name,
                        p.category,
                        p.price,
                        i.stock_count,
                        i.low_stock_threshold
                    FROM products p
                    LEFT JOIN inventory i
                        ON p.product_id = i.product_id
                    ORDER BY p.product_id
                """)
            except Exception as error:
                log_error(
                    "products_query_failed",
                    error,
                    operation="fetch_products_and_inventory"
                )
                raise

            log_event("products_query_succeeded")

            try:
                products = cursor.fetchall()
            except Exception as error:
                log_error(
                    "products_fetch_failed",
                    error,
                    operation="fetch_products_and_inventory"
                )
                raise

            log_event(
                "products_fetched",
                count=len(products)
            )

            log_event(
                "orders_query_started",
                operation="fetch_recent_orders",
                limit=100
            )

            try:
                cursor.execute("""
                    SELECT
                        o.order_id,
                        o.customer_id,
                        o.total_amount,
                        o.status,
                        o.created_at
                    FROM orders o
                    ORDER BY o.created_at DESC
                    LIMIT 100
                """)
            except Exception as error:
                log_error(
                    "orders_query_failed",
                    error,
                    operation="fetch_recent_orders",
                    limit=100
                )
                raise

            log_event("orders_query_succeeded")

            try:
                orders = cursor.fetchall()
            except Exception as error:
                log_error(
                    "orders_fetch_failed",
                    error,
                    operation="fetch_recent_orders"
                )
                raise

            log_event(
                "orders_fetched",
                count=len(orders)
            )

    except Exception as error:
        log_error(
            "report_database_operations_failed",
            error
        )
        raise

    finally:
        log_event("database_connection_close_started")
        try:
            connection.close()
        except Exception as error:
            log_error(
                "database_connection_close_failed",
                error
            )
            raise
        log_event("database_connection_closed")

    log_event("csv_generation_started")

    try:
        now = datetime.now(timezone.utc)

        output = io.StringIO()

        writer = csv.writer(output)

        writer.writerow([
            "Report Generated",
            now.isoformat()
        ])

        writer.writerow([])

        writer.writerow([
            "PRODUCTS"
        ])

        writer.writerow([
            "Product ID",
            "Name",
            "Category",
            "Price",
            "Stock",
            "Low Stock Threshold"
        ])

        low_stock_count = 0

        for product in products:

            stock = product["stock_count"] or 0
            threshold = product["low_stock_threshold"] or 0

            if stock <= threshold:
                low_stock_count += 1

            writer.writerow([
                product["product_id"],
                product["name"],
                product["category"],
                product["price"],
                stock,
                threshold
            ])

        writer.writerow([])

        writer.writerow([
            "RECENT ORDERS"
        ])

        writer.writerow([
            "Order ID",
            "Customer ID",
            "Total Amount",
            "Status",
            "Created At"
        ])

        orders_placed = 0
        orders_failed = 0

        for order in orders:

            if order["status"] == "CONFIRMED":
                orders_placed += 1

            if order["status"] == "FAILED":
                orders_failed += 1

            writer.writerow([
                order["order_id"],
                order["customer_id"],
                order["total_amount"],
                order["status"],
                order["created_at"]
            ])

    except Exception as error:
        log_error(
            "csv_generation_failed",
            error
        )
        raise

    log_event(
        "csv_generation_completed",
        product_count=len(products),
        order_count=len(orders),
        low_stock_count=low_stock_count
    )

    report_date = now.strftime("%Y-%m-%d")

    key = f"reports/daily-report-{report_date}.csv"

    log_event(
        "s3_report_upload_started",
        bucket=REPORTS_BUCKET,
        key=key
    )

    try:
        s3.put_object(
            Bucket=REPORTS_BUCKET,
            Key=key,
            Body=output.getvalue().encode("utf-8"),
            ContentType="text/csv"
        )
    except Exception as error:
        log_error(
            "s3_report_upload_failed",
            error,
            bucket=REPORTS_BUCKET,
            key=key
        )
        raise

    log_event(
        "s3_report_upload_succeeded",
        bucket=REPORTS_BUCKET,
        key=key
    )


    # =====================================================
    # PUBLISH REPORTS GENERATED METRIC
    # =====================================================

    log_event(
        "reports_generated_metric_publish_started",
        metric_name="ReportsGenerated"
    )

    publish_metric(
        "ReportsGenerated",
        1
    )


    # =====================================================
    # PUBLISH EXISTING METRICS
    # =====================================================

    log_event(
        "orders_placed_metric_publish_started",
        metric_name="OrdersPlaced",
        value=orders_placed
    )

    publish_metric(
        "OrdersPlaced",
        orders_placed
    )

    log_event(
        "orders_failed_metric_publish_started",
        metric_name="OrdersFailed",
        value=orders_failed
    )

    publish_metric(
        "OrdersFailed",
        orders_failed
    )

    log_event(
        "low_stock_events_metric_publish_started",
        metric_name="LowStockEvents",
        value=low_stock_count
    )

    publish_metric(
        "LowStockEvents",
        low_stock_count
    )

    log_event(
        "all_cloudwatch_metrics_published",
        metrics=[
            "ReportsGenerated",
            "OrdersPlaced",
            "OrdersFailed",
            "LowStockEvents"
        ],
        status="success"
    )

    return {
        "bucket": REPORTS_BUCKET,
        "key": key,
        "ordersPlaced": orders_placed,
        "ordersFailed": orders_failed,
        "lowStockEvents": low_stock_count
    }


def lambda_handler(event, context):

    log_event(
        "report_generator_event_received",
        event=event
    )

    try:
        result = generate_report()
    except Exception as error:
        log_error(
            "report_generation_failed",
            error
        )

        return {
            "statusCode": 500,
            "body": json.dumps({
                "message": "Report generation failed",
                "error": str(error)
            })
        }

    log_event(
        "report_generated_successfully",
        result=result
    )

    return {
        "statusCode": 200,
        "body": json.dumps(result)
    }
