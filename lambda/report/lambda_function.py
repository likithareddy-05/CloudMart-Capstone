import csv
import io
import json
import os
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


def get_parameter(name, with_decryption=False):
    response = ssm.get_parameter(
        Name=name,
        WithDecryption=with_decryption
    )

    return response["Parameter"]["Value"]


def get_db_connection():

    db_host = get_parameter(
        DB_HOST_PARAMETER
    )

    db_port = int(
        get_parameter(
            DB_PORT_PARAMETER
        )
    )

    db_name = get_parameter(
        DB_NAME_PARAMETER
    )

    db_username = get_parameter(
        DB_USERNAME_PARAMETER
    )

    db_password = get_parameter(
        DB_PASSWORD_PARAMETER,
        with_decryption=True
    )

    return pymysql.connect(
        host=db_host,
        port=db_port,
        user=db_username,
        password=db_password,
        database=db_name,
        cursorclass=pymysql.cursors.DictCursor,
        connect_timeout=10
    )

def publish_metric(metric_name, value):
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


def generate_report():

    connection = get_db_connection()

    try:
        with connection.cursor() as cursor:

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

    finally:
        connection.close()

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

    report_date = now.strftime("%Y-%m-%d")

    key = f"reports/daily-report-{report_date}.csv"

    s3.put_object(
        Bucket=REPORTS_BUCKET,
        Key=key,
        Body=output.getvalue().encode("utf-8"),
        ContentType="text/csv"
    )

    publish_metric("OrdersPlaced", orders_placed)
    publish_metric("OrdersFailed", orders_failed)
    publish_metric("LowStockEvents", low_stock_count)

    return {
        "bucket": REPORTS_BUCKET,
        "key": key,
        "ordersPlaced": orders_placed,
        "ordersFailed": orders_failed,
        "lowStockEvents": low_stock_count
    }


def lambda_handler(event, context):

    print(json.dumps({
        "message": "Generating CloudMart daily report",
        "event": event
    }))

    result = generate_report()

    print(json.dumps({
        "message": "Report generated successfully",
        "result": result
    }))

    return {
        "statusCode": 200,
        "body": json.dumps(result)
    }