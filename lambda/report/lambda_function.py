import csv
import io
import json
import os
import traceback
from datetime import datetime, timezone, timedelta

import boto3
import pymysql


# ==========================================================
# AWS CLIENTS
# ==========================================================

s3 = boto3.client("s3")
cloudwatch = boto3.client("cloudwatch")
ssm = boto3.client("ssm")


# ==========================================================
# ENVIRONMENT VARIABLES
# ==========================================================

REPORTS_BUCKET = os.environ["REPORTS_BUCKET"]

DB_HOST_PARAMETER = os.environ["DB_HOST_PARAMETER"]
DB_PORT_PARAMETER = os.environ["DB_PORT_PARAMETER"]
DB_NAME_PARAMETER = os.environ["DB_NAME_PARAMETER"]
DB_USERNAME_PARAMETER = os.environ["DB_USERNAME_PARAMETER"]
DB_PASSWORD_PARAMETER = os.environ["DB_PASSWORD_PARAMETER"]


# ==========================================================
# LOGGING
# ==========================================================

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


# ==========================================================
# SSM PARAMETER HELPER
# ==========================================================

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


# ==========================================================
# DATABASE CONNECTION
# ==========================================================

def get_db_connection():

    log_event("database_connection_setup_started")

    try:

        db_host = get_parameter(
            DB_HOST_PARAMETER
        )

        log_event(
            "database_host_parameter_retrieved"
        )


        db_port = int(
            get_parameter(
                DB_PORT_PARAMETER
            )
        )

        log_event(
            "database_port_parameter_retrieved"
        )


        db_name = get_parameter(
            DB_NAME_PARAMETER
        )

        log_event(
            "database_name_parameter_retrieved"
        )


        db_username = get_parameter(
            DB_USERNAME_PARAMETER
        )

        log_event(
            "database_username_parameter_retrieved"
        )


        db_password = get_parameter(
            DB_PASSWORD_PARAMETER,
            with_decryption=True
        )

        log_event(
            "database_password_parameter_retrieved"
        )

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


# ==========================================================
# CLOUDWATCH METRIC
# ==========================================================

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


# ==========================================================
# REPORT GENERATION
# ==========================================================

def generate_report():

    log_event("report_generation_started")


    # ======================================================
    # REPORT DATES
    # ======================================================

    now_utc = datetime.now(timezone.utc)

    # IST = UTC + 5:30
    ist_offset = timedelta(
        hours=5,
        minutes=30
    )

    now_ist = now_utc + ist_offset

    yesterday_ist_date = (
        now_ist.date() - timedelta(days=1)
    )

    today_ist_date = now_ist.date()


    # Start of yesterday in IST
    yesterday_start_ist = datetime(
        yesterday_ist_date.year,
        yesterday_ist_date.month,
        yesterday_ist_date.day
    )

    # Start of today in IST
    today_start_ist = datetime(
        today_ist_date.year,
        today_ist_date.month,
        today_ist_date.day
    )


    # Convert IST boundaries to UTC
    yesterday_start_utc = (
        yesterday_start_ist - ist_offset
    )

    today_start_utc = (
        today_start_ist - ist_offset
    )


    log_event(
        "report_period_calculated",
        report_generated_utc=now_utc,
        report_generated_ist=now_ist,
        yesterday=str(yesterday_ist_date),
        yesterday_start_utc=yesterday_start_utc,
        today_start_utc=today_start_utc
    )


    # ======================================================
    # DATABASE CONNECTION
    # ======================================================

    connection = get_db_connection()

    log_event(
        "database_connection_obtained"
    )


    try:

        with connection.cursor() as cursor:

            log_event(
                "database_cursor_created"
            )


            # ==================================================
            # 1. EXISTING PRODUCTS + INVENTORY QUERY
            # ==================================================

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

                products = cursor.fetchall()

            except Exception as error:

                log_error(
                    "products_query_failed",
                    error,
                    operation="fetch_products_and_inventory"
                )

                raise


            log_event(
                "products_query_succeeded"
            )


            log_event(
                "products_fetched",
                count=len(products)
            )


            # ==================================================
            # 2. EXISTING RECENT ORDERS QUERY
            # ==================================================

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

                orders = cursor.fetchall()

            except Exception as error:

                log_error(
                    "orders_query_failed",
                    error,
                    operation="fetch_recent_orders",
                    limit=100
                )

                raise


            log_event(
                "orders_query_succeeded"
            )


            log_event(
                "orders_fetched",
                count=len(orders)
            )


            # ==================================================
            # 3. NEW: YESTERDAY'S ORDER SUMMARY
            # ==================================================

            log_event(
                "yesterday_summary_query_started",
                report_date=str(yesterday_ist_date)
            )

            try:

                cursor.execute(
                    """
                    SELECT
                        COUNT(*) AS total_orders,

                        COALESCE(
                            SUM(
                                CASE
                                    WHEN LOWER(status) = 'confirmed'
                                    THEN 1
                                    ELSE 0
                                END
                            ),
                            0
                        ) AS confirmed_orders,

                        COALESCE(
                            SUM(
                                CASE
                                    WHEN LOWER(status) = 'failed'
                                    THEN 1
                                    ELSE 0
                                END
                            ),
                            0
                        ) AS failed_orders,

                        COALESCE(
                            SUM(
                                CASE
                                    WHEN LOWER(status) = 'cancelled'
                                    THEN 1
                                    ELSE 0
                                END
                            ),
                            0
                        ) AS cancelled_orders,

                        COALESCE(
                            SUM(total_amount),
                            0
                        ) AS revenue,

                        COALESCE(
                            AVG(total_amount),
                            0
                        ) AS average_order_value

                    FROM orders

                    WHERE created_at >= %s
                    AND created_at < %s
                    """,
                    (
                        yesterday_start_utc,
                        today_start_utc
                    )
                )

                yesterday_summary = cursor.fetchone()

            except Exception as error:

                log_error(
                    "yesterday_summary_query_failed",
                    error
                )

                raise


            log_event(
                "yesterday_summary_query_succeeded",
                report_date=str(yesterday_ist_date)
            )


            # ==================================================
            # 4. NEW: CURRENT BUSINESS SNAPSHOT
            # ==================================================

            log_event(
                "current_business_snapshot_query_started"
            )

            try:

                cursor.execute("""
                    SELECT
                        COUNT(*) AS total_orders,

                        COALESCE(
                            SUM(
                                CASE
                                    WHEN LOWER(status) = 'confirmed'
                                    THEN 1
                                    ELSE 0
                                END
                            ),
                            0
                        ) AS confirmed_orders,

                        COALESCE(
                            SUM(
                                CASE
                                    WHEN LOWER(status) = 'failed'
                                    THEN 1
                                    ELSE 0
                                END
                            ),
                            0
                        ) AS failed_orders,

                        COALESCE(
                            SUM(
                                CASE
                                    WHEN LOWER(status) = 'cancelled'
                                    THEN 1
                                    ELSE 0
                                END
                            ),
                            0
                        ) AS cancelled_orders,

                        COALESCE(
                            SUM(total_amount),
                            0
                        ) AS total_revenue,

                        COALESCE(
                            AVG(total_amount),
                            0
                        ) AS average_order_value

                    FROM orders
                """)

                current_order_summary = cursor.fetchone()


                # ----------------------------------------------
                # Total Users
                # ----------------------------------------------

                cursor.execute("""
                    SELECT
                        COUNT(*) AS total_users
                    FROM users
                """)

                user_summary = cursor.fetchone()

            except Exception as error:

                log_error(
                    "current_business_snapshot_query_failed",
                    error
                )

                raise


            log_event(
                "current_business_snapshot_query_succeeded"
            )


    except Exception as error:

        log_error(
            "report_database_operations_failed",
            error
        )

        raise


    finally:

        log_event(
            "database_connection_close_started"
        )

        try:

            connection.close()

        except Exception as error:

            log_error(
                "database_connection_close_failed",
                error
            )

            raise

        log_event(
            "database_connection_closed"
        )


    # ==========================================================
    # INVENTORY COUNTS
    # ==========================================================

    low_stock_count = 0
    out_of_stock_count = 0
    healthy_stock_count = 0


    for product in products:

        stock = product["stock_count"] or 0

        threshold = product["low_stock_threshold"] or 0


        if stock == 0:

            out_of_stock_count += 1

        elif stock <= threshold:

            low_stock_count += 1

        else:

            healthy_stock_count += 1


    total_products = len(products)


    # Keep the existing meaning of LowStockEvents:
    # stock <= threshold
    low_stock_events_count = (
        low_stock_count + out_of_stock_count
    )


    # ==========================================================
    # CSV GENERATION
    # ==========================================================

    log_event(
        "csv_generation_started"
    )

    try:

        output = io.StringIO()

        writer = csv.writer(output)


        # ======================================================
        # REPORT HEADER
        # ======================================================

        writer.writerow(
            [
                "CLOUDMART DAILY BUSINESS REPORT"
            ]
        )

        writer.writerow(
            [
                "Report Generated",
                now_ist.strftime(
                    "%Y-%m-%d %H:%M:%S IST"
                )
            ]
        )

        writer.writerow(
            [
                "Yesterday Covered",
                str(yesterday_ist_date)
            ]
        )

        writer.writerow([])


        # ======================================================
        # 1. YESTERDAY'S ACTIVITY
        # ======================================================

        writer.writerow(
            [
                "1. YESTERDAY'S ACTIVITY"
            ]
        )

        writer.writerow(
            [
                "Reporting Date",
                str(yesterday_ist_date)
            ]
        )

        writer.writerow([])

        writer.writerow(
            [
                "Metric",
                "Value"
            ]
        )

        writer.writerow(
            [
                "Total Orders",
                yesterday_summary["total_orders"]
            ]
        )

        writer.writerow(
            [
                "Confirmed Orders",
                yesterday_summary["confirmed_orders"]
            ]
        )

        writer.writerow(
            [
                "Failed Orders",
                yesterday_summary["failed_orders"]
            ]
        )

        writer.writerow(
            [
                "Cancelled Orders",
                yesterday_summary["cancelled_orders"]
            ]
        )

        writer.writerow(
            [
                "Revenue Generated",
                yesterday_summary["revenue"]
            ]
        )

        writer.writerow(
            [
                "Average Order Value",
                yesterday_summary["average_order_value"]
            ]
        )

        writer.writerow([])


        # ======================================================
        # 2. CURRENT BUSINESS SNAPSHOT
        # ======================================================

        writer.writerow(
            [
                "2. CURRENT BUSINESS SNAPSHOT"
            ]
        )

        writer.writerow(
            [
                "Data Up To",
                now_ist.strftime(
                    "%Y-%m-%d %H:%M:%S IST"
                )
            ]
        )

        writer.writerow([])

        writer.writerow(
            [
                "Metric",
                "Value"
            ]
        )

        writer.writerow(
            [
                "Total Orders",
                current_order_summary["total_orders"]
            ]
        )

        writer.writerow(
            [
                "Confirmed Orders",
                current_order_summary["confirmed_orders"]
            ]
        )

        writer.writerow(
            [
                "Failed Orders",
                current_order_summary["failed_orders"]
            ]
        )

        writer.writerow(
            [
                "Cancelled Orders",
                current_order_summary["cancelled_orders"]
            ]
        )

        writer.writerow(
            [
                "Total Revenue",
                current_order_summary["total_revenue"]
            ]
        )

        writer.writerow(
            [
                "Average Order Value",
                current_order_summary["average_order_value"]
            ]
        )

        writer.writerow(
            [
                "Total Users",
                user_summary["total_users"]
            ]
        )

        writer.writerow(
            [
                "Total Products",
                total_products
            ]
        )

        writer.writerow(
            [
                "Healthy Stock Products",
                healthy_stock_count
            ]
        )

        writer.writerow(
            [
                "Low Stock Products",
                low_stock_count
            ]
        )

        writer.writerow(
            [
                "Out Of Stock Products",
                out_of_stock_count
            ]
        )

        writer.writerow([])


        # ======================================================
        # 3. PRODUCTS & INVENTORY
        # ======================================================

        writer.writerow(
            [
                "3. PRODUCTS & INVENTORY"
            ]
        )

        writer.writerow([])

        writer.writerow(
            [
                "Product ID",
                "Name",
                "Category",
                "Price",
                "Stock",
                "Low Stock Threshold",
                "Stock Status"
            ]
        )


        for product in products:

            stock = product["stock_count"] or 0

            threshold = product["low_stock_threshold"] or 0


            if stock == 0:

                stock_status = "OUT OF STOCK"

            elif stock <= threshold:

                stock_status = "LOW STOCK"

            else:

                stock_status = "HEALTHY"


            writer.writerow(
                [
                    product["product_id"],
                    product["name"],
                    product["category"],
                    product["price"],
                    stock,
                    threshold,
                    stock_status
                ]
            )


        writer.writerow([])


        # ======================================================
        # 4. RECENT ORDERS
        # ======================================================

        writer.writerow(
            [
                "4. RECENT ORDERS"
            ]
        )

        writer.writerow(
            [
                "Latest 100 orders"
            ]
        )

        writer.writerow([])

        writer.writerow(
            [
                "Order ID",
                "Customer ID",
                "Total Amount",
                "Status",
                "Created At"
            ]
        )


        for order in orders:

            writer.writerow(
                [
                    order["order_id"],
                    order["customer_id"],
                    order["total_amount"],
                    order["status"],
                    order["created_at"]
                ]
            )


        writer.writerow([])


        # ======================================================
        # 5. ALERTS & EXCEPTIONS
        # ======================================================

        writer.writerow(
            [
                "5. ALERTS & EXCEPTIONS"
            ]
        )

        writer.writerow([])

        writer.writerow(
            [
                "Alert / Exception",
                "Count"
            ]
        )

        writer.writerow(
            [
                "Low Stock Products",
                low_stock_count
            ]
        )

        writer.writerow(
            [
                "Out Of Stock Products",
                out_of_stock_count
            ]
        )

        writer.writerow(
            [
                "Failed Orders",
                current_order_summary["failed_orders"]
            ]
        )

        writer.writerow(
            [
                "Cancelled Orders",
                current_order_summary["cancelled_orders"]
            ]
        )


    except Exception as error:

        log_error(
            "csv_generation_failed",
            error
        )

        raise


    # ==========================================================
    # CSV GENERATION COMPLETED
    # ==========================================================

    log_event(
        "csv_generation_completed",
        product_count=len(products),
        order_count=len(orders),
        low_stock_count=low_stock_events_count,
        report_date=str(yesterday_ist_date)
    )


    # ==========================================================
    # S3 UPLOAD
    # ==========================================================

    report_date = now_ist.strftime(
        "%Y-%m-%d"
    )

    key = (
        f"reports/daily-report-{report_date}.csv"
    )


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


    # ==========================================================
    # REPORTS GENERATED METRIC
    # ==========================================================

    log_event(
        "reports_generated_metric_publish_started",
        metric_name="ReportsGenerated"
    )


    publish_metric(
        "ReportsGenerated",
        1
    )


    # ==========================================================
    # LOW STOCK EVENTS METRIC
    # ==========================================================

    log_event(
        "low_stock_events_metric_publish_started",
        metric_name="LowStockEvents",
        value=low_stock_events_count
    )


    publish_metric(
        "LowStockEvents",
        low_stock_events_count
    )


    log_event(
        "all_cloudwatch_metrics_published",
        metrics=[
            "ReportsGenerated",
            "LowStockEvents"
        ],
        status="success"
    )


    # ==========================================================
    # RETURN RESULT
    # ==========================================================

    return {
        "bucket": REPORTS_BUCKET,
        "key": key,
        "reportDate": report_date,
        "yesterday": str(yesterday_ist_date),
        "lowStockEvents": low_stock_events_count
    }


# ==========================================================
# LAMBDA HANDLER
# ==========================================================

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
            "body": json.dumps(
                {
                    "message": "Report generation failed",
                    "error": str(error)
                }
            )
        }


    log_event(
        "report_generated_successfully",
        result=result
    )


    return {
        "statusCode": 200,
        "body": json.dumps(result)
    }