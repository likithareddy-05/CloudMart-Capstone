import hashlib
import logging
import os
import time
from datetime import datetime
from io import BytesIO
from pathlib import Path

import boto3
import pymysql
from flask import (
    Flask,
    redirect,
    render_template,
    request,
    send_file,
    session,
    url_for,
)


BASE_DIR = Path(__file__).resolve().parent

app = Flask(
    __name__,
    template_folder=str(BASE_DIR)
)


# ============================================================
# SESSION CONFIGURATION
# ============================================================

# Admin session expires after 60 minutes of inactivity.
# This is NOT related to report downloads.
SESSION_TIMEOUT_MINUTES = int(
    os.environ.get(
        "SESSION_TIMEOUT_MINUTES",
        "60"
    )
)

SESSION_TIMEOUT_SECONDS = (
    SESSION_TIMEOUT_MINUTES * 60
)


# ============================================================
# FLASK SECRET
# ============================================================

DASHBOARD_SECRET_FILE = (
    "/etc/cloudmart-dashboard-secret"
)

try:

    with open(
        DASHBOARD_SECRET_FILE,
        "r",
        encoding="utf-8"
    ) as secret_file:

        app.secret_key = (
            secret_file.read().strip()
        )

except (
    FileNotFoundError,
    PermissionError,
    OSError
):

    app.secret_key = os.environ.get(
        "DASHBOARD_SECRET_KEY",
        ""
    )


if not app.secret_key:

    raise RuntimeError(
        "Dashboard session secret is not configured. "
        "Create /etc/cloudmart-dashboard-secret "
        "or set DASHBOARD_SECRET_KEY."
    )


app.config.update(

    SESSION_COOKIE_HTTPONLY=True,

    SESSION_COOKIE_SAMESITE="Lax",

    PERMANENT_SESSION_LIFETIME=(
        SESSION_TIMEOUT_SECONDS
    )
)


logging.basicConfig(
    level=logging.INFO
)


# ============================================================
# ENVIRONMENT / AWS CONFIGURATION
# ============================================================

ENVIRONMENT = os.environ.get(
    "ENVIRONMENT",
    "dev"
)


AWS_REGION = os.environ.get(
    "AWS_REGION",
    "ap-south-1"
)


REPORTS_BUCKET = os.environ.get(
    "REPORTS_BUCKET"
)


# ============================================================
# CLOUDMART SSM PATHS
# ============================================================

DB_HOST_PARAMETER = (
    f"/cloudmart/{ENVIRONMENT}/db/host"
)

DB_PORT_PARAMETER = (
    f"/cloudmart/{ENVIRONMENT}/db/port"
)

DB_NAME_PARAMETER = (
    f"/cloudmart/{ENVIRONMENT}/db/name"
)

DB_USERNAME_PARAMETER = (
    f"/cloudmart/{ENVIRONMENT}/db/username"
)

DB_PASSWORD_PARAMETER = (
    f"/cloudmart/{ENVIRONMENT}/db/password"
)


# ============================================================
# AWS CLIENTS
# ============================================================

ssm = boto3.client(
    "ssm",
    region_name=AWS_REGION
)


s3 = boto3.client(
    "s3",
    region_name=AWS_REGION
)


# ============================================================
# GET SSM PARAMETER
# ============================================================

def get_parameter(name):

    result = ssm.get_parameter(
        Name=name,
        WithDecryption=True
    )

    return result[
        "Parameter"
    ][
        "Value"
    ]


# ============================================================
# DATABASE CONNECTION
# ============================================================

def get_db_connection():

    host = get_parameter(
        DB_HOST_PARAMETER
    )

    port = int(
        get_parameter(
            DB_PORT_PARAMETER
        )
    )

    database = get_parameter(
        DB_NAME_PARAMETER
    )

    username = get_parameter(
        DB_USERNAME_PARAMETER
    )

    password = get_parameter(
        DB_PASSWORD_PARAMETER
    )

    return pymysql.connect(

        host=host,

        port=port,

        user=username,

        password=password,

        database=database,

        connect_timeout=10,

        cursorclass=(
            pymysql.cursors.DictCursor
        )
    )


# ============================================================
# PRODUCTS / INVENTORY
# ============================================================

def get_products():

    connection = None

    try:

        connection = get_db_connection()

        with connection.cursor() as cursor:

            cursor.execute(
                """
                SELECT
                    p.product_id AS id,
                    p.name,
                    p.description,
                    p.price,
                    p.category,
                    i.stock_count
                FROM products p
                INNER JOIN inventory i
                    ON p.product_id = i.product_id
                WHERE p.is_deleted = FALSE
                ORDER BY p.product_id
                """
            )

            return cursor.fetchall()

    finally:

        if connection:
            connection.close()


# ============================================================
# RECENT ORDER ITEMS
# ============================================================

def get_recent_orders():

    connection = None

    try:

        connection = get_db_connection()

        with connection.cursor() as cursor:

            cursor.execute(
                """
                SELECT
                    o.order_id AS order_id,
                    o.customer_id,
                    o.status,
                    o.created_at,
                    oi.order_item_id,
                    oi.product_id,
                    p.name AS product_name,
                    oi.quantity,
                    oi.unit_price AS price,
                    oi.subtotal
                FROM orders o
                INNER JOIN order_items oi
                    ON o.order_id = oi.order_id
                INNER JOIN products p
                    ON oi.product_id = p.product_id
                WHERE p.is_deleted = FALSE
                ORDER BY
                    o.created_at DESC,
                    oi.order_item_id DESC
                LIMIT 50
                """
            )

            return cursor.fetchall()

    finally:

        if connection:
            connection.close()


# ============================================================
# RECENT ORDER SUMMARY
# ============================================================

def get_recent_order_summaries():

    connection = None

    try:

        connection = get_db_connection()

        with connection.cursor() as cursor:

            cursor.execute(
                """
                SELECT
                    o.order_id,
                    o.customer_id,
                    o.total_amount,
                    o.status,
                    o.created_at
                FROM orders o
                ORDER BY o.created_at DESC
                LIMIT 100
                """
            )

            return cursor.fetchall()

    finally:

        if connection:
            connection.close()


# ============================================================
# DASHBOARD KPI DATA
# ============================================================

def get_dashboard_stats():

    connection = None

    try:

        connection = get_db_connection()

        with connection.cursor() as cursor:

            # ----------------------------------------------
            # TOTAL ORDERS
            # ----------------------------------------------

            cursor.execute(
                """
                SELECT COUNT(*) AS total_orders
                FROM orders
                """
            )

            total_orders = (
                cursor.fetchone()
                ["total_orders"]
            )


            # ----------------------------------------------
            # CONFIRMED ORDERS
            # ----------------------------------------------

            cursor.execute(
                """
                SELECT COUNT(*) AS confirmed_orders
                FROM orders
                WHERE status = 'CONFIRMED'
                """
            )

            confirmed_orders = (
                cursor.fetchone()
                ["confirmed_orders"]
            )


            # ----------------------------------------------
            # FAILED ORDERS
            # ----------------------------------------------

            cursor.execute(
                """
                SELECT COUNT(*) AS failed_orders
                FROM orders
                WHERE status = 'FAILED'
                """
            )

            failed_orders = (
                cursor.fetchone()
                ["failed_orders"]
            )


            # ----------------------------------------------
            # ORDER ITEMS
            # ----------------------------------------------

            cursor.execute(
                """
                SELECT COUNT(*) AS order_items
                FROM order_items
                """
            )

            order_items = (
                cursor.fetchone()
                ["order_items"]
            )


            # ----------------------------------------------
            # ACTIVE PRODUCTS
            # ----------------------------------------------

            cursor.execute(
                """
                SELECT COUNT(*) AS active_products
                FROM products
                WHERE is_deleted = FALSE
                """
            )

            active_products = (
                cursor.fetchone()
                ["active_products"]
            )


            # ----------------------------------------------
            # TOTAL REVENUE
            # ----------------------------------------------

            cursor.execute(
                """
                SELECT
                    COALESCE(
                        SUM(total_amount),
                        0
                    ) AS total_revenue
                FROM orders
                WHERE status = 'CONFIRMED'
                """
            )

            total_revenue = (
                cursor.fetchone()
                ["total_revenue"]
            )


        return {

            "total_orders":
                total_orders,

            "confirmed_orders":
                confirmed_orders,

            "failed_orders":
                failed_orders,

            "order_items":
                order_items,

            "active_products":
                active_products,

            "total_revenue":
                total_revenue
        }


    finally:

        if connection:
            connection.close()


# ============================================================
# REPORT COUNT
# ============================================================

def get_reports_generated():

    if not REPORTS_BUCKET:
        return 0

    try:

        paginator = (
            s3.get_paginator(
                "list_objects_v2"
            )
        )

        count = 0

        for page in paginator.paginate(

            Bucket=REPORTS_BUCKET,

            Prefix="reports/"
        ):

            count += len(
                page.get(
                    "Contents",
                    []
                )
            )

        return count


    except Exception as error:

        app.logger.warning(
            "Could not get reports generated count: %s",
            error
        )

        return 0


# ============================================================
# FIND LATEST REPORT
# ============================================================

def find_latest_report():

    if not REPORTS_BUCKET:
        return None

    paginator = (
        s3.get_paginator(
            "list_objects_v2"
        )
    )

    latest = None


    for page in paginator.paginate(

        Bucket=REPORTS_BUCKET,

        Prefix="reports/"
    ):

        for item in page.get(
            "Contents",
            []
        ):

            key = item.get(
                "Key",
                ""
            )

            if not key.endswith(
                ".csv"
            ):
                continue


            if (
                latest is None
                or
                item["LastModified"]
                >
                latest["LastModified"]
            ):

                latest = item


    return latest


# ============================================================
# LATEST REPORT INFORMATION
# ============================================================

def get_latest_report():

    latest = find_latest_report()

    if not latest:
        return None

    return {

        "key":
            latest["Key"],

        "last_modified":
            latest["LastModified"]
    }


# ============================================================
# DOWNLOAD LATEST REPORT
# ============================================================
#
# There is NO presigned URL here.
#
# Therefore there is NO 1-hour URL expiration.
#
# Flask retrieves the CSV from S3 and sends it
# directly to the authenticated administrator.
# ============================================================

@app.route(
    "/download-latest-report"
)
def download_latest_report():

    if not REPORTS_BUCKET:

        return (
            "Reports bucket is not configured.",
            500
        )


    latest = find_latest_report()


    if not latest:

        return (
            "No report is currently available.",
            404
        )


    try:

        response = s3.get_object(

            Bucket=REPORTS_BUCKET,

            Key=latest["Key"]
        )


        report_bytes = (
            response["Body"].read()
        )


        filename = (
            os.path.basename(
                latest["Key"]
            )
            or
            "cloudmart-report.csv"
        )


        return send_file(

            BytesIO(report_bytes),

            mimetype="text/csv",

            as_attachment=True,

            download_name=filename
        )


    except Exception as error:

        app.logger.exception(
            "Unable to download latest report: %s",
            error
        )

        return (
            "Unable to download the latest report.",
            500
        )


# ============================================================
# ADMIN AUTHENTICATION
# ============================================================

def get_admin_user(
    email,
    provided_token
):

    connection = None

    try:

        token_hash = hashlib.sha256(

            provided_token.encode(
                "utf-8"
            )

        ).hexdigest()


        connection = (
            get_db_connection()
        )


        with connection.cursor() as cursor:

            cursor.execute(

                """
                SELECT
                    user_id,
                    name,
                    email,
                    role
                FROM users
                WHERE email = %s
                  AND token_hash = %s
                  AND UPPER(role) = 'ADMIN'
                LIMIT 1
                """,

                (
                    email.strip(),
                    token_hash
                )
            )


            return cursor.fetchone()


    finally:

        if connection:
            connection.close()


# ============================================================
# ADMIN SESSION PROTECTION
# ============================================================

@app.before_request
def require_admin_login():

    # These endpoints are public.
    if request.endpoint in {

        "login",

        "health",

        "static"

    }:

        return None


    # No authenticated session.
    if not session.get(
        "admin_authenticated"
    ):

        return redirect(
            url_for("login")
        )


    # --------------------------------------------------------
    # CHECK INACTIVITY TIMEOUT
    # --------------------------------------------------------

    now = time.time()

    last_activity = session.get(
        "last_activity",
        now
    )


    if (
        now - last_activity
        >
        SESSION_TIMEOUT_SECONDS
    ):

        session.clear()

        return redirect(
            url_for(
                "login",
                expired=1
            )
        )


    # --------------------------------------------------------
    # REFRESH INACTIVITY WINDOW
    # --------------------------------------------------------

    session["last_activity"] = now

    session.permanent = True

    return None


# ============================================================
# LOGIN
# ============================================================

@app.route(
    "/login",
    methods=["GET", "POST"]
)
def login():

    if session.get(
        "admin_authenticated"
    ):

        return redirect(
            url_for("dashboard")
        )


    error = None

    expired = (
        request.args.get(
            "expired"
        )
        ==
        "1"
    )


    if request.method == "POST":

        email = request.form.get(
            "email",
            ""
        ).strip()


        admin_token = request.form.get(
            "admin_token",
            ""
        )


        if (
            not email
            or
            not admin_token
        ):

            error = (
                "Please enter the "
                "admin email and token."
            )


        else:

            try:

                admin = get_admin_user(

                    email,

                    admin_token
                )


                if admin:

                    session.clear()

                    session.permanent = True

                    session[
                        "admin_authenticated"
                    ] = True

                    session[
                        "admin_user_id"
                    ] = int(
                        admin["user_id"]
                    )

                    session[
                        "admin_name"
                    ] = admin["name"]

                    session[
                        "admin_email"
                    ] = admin["email"]

                    session[
                        "admin_role"
                    ] = admin["role"]

                    session[
                        "last_activity"
                    ] = time.time()


                    return redirect(
                        url_for(
                            "dashboard"
                        )
                    )


                error = (
                    "Invalid admin credentials."
                )


            except Exception:

                app.logger.exception(
                    "Admin login failed"
                )

                error = (
                    "Unable to authenticate. "
                    "Please try again."
                )


    return render_template(

        "login.html",

        environment=ENVIRONMENT,

        error=error,

        expired=expired,

        session_timeout_minutes=(
            SESSION_TIMEOUT_MINUTES
        )
    )


# ============================================================
# LOGOUT
# ============================================================

@app.route("/logout")
def logout():

    expired = (
        request.args.get(
            "expired"
        )
        ==
        "1"
    )


    session.clear()


    if expired:

        return redirect(
            url_for(
                "login",
                expired=1
            )
        )


    return redirect(
        url_for("login")
    )


# ============================================================
# DASHBOARD
# ============================================================

@app.route("/")
def dashboard():

    try:

        products = get_products()

        orders = get_recent_orders()

        order_summaries = (
            get_recent_order_summaries()
        )

        stats = get_dashboard_stats()

        reports_generated = (
            get_reports_generated()
        )

        latest_report = (
            get_latest_report()
        )


        return render_template(

            "index.html",

            products=products,

            orders=orders,

            order_summaries=(
                order_summaries
            ),

            stats=stats,

            environment=ENVIRONMENT,

            reports_generated=(
                reports_generated
            ),

            latest_report=(
                latest_report
            ),

            generated_at=datetime.now(),

            session_timeout_minutes=(
                SESSION_TIMEOUT_MINUTES
            )
        )


    except Exception as error:

        app.logger.exception(
            "Dashboard error"
        )


        return (

            "<h1>CloudMart Dashboard</h1>"

            "<h2>Dashboard Error</h2>"

            f"<pre>{error}</pre>",

            500
        )


# ============================================================
# HEALTH CHECK
# ============================================================

@app.route("/health")
def health():

    return {

        "status":
            "healthy",

        "service":
            "cloudmart-dashboard"
    }


# ============================================================
# LOCAL DEVELOPMENT
# ============================================================

if __name__ == "__main__":

    app.run(

        host="127.0.0.1",

        port=5000
    )