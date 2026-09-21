import os
import hashlib
import logging
from datetime import datetime, timedelta, timezone
from functools import wraps

import boto3
import pymysql
from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    session,
    send_file,
    flash
)


# ============================================================
# LOGGING
# ============================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s"
)

logger = logging.getLogger("cloudmart-dashboard")


# ============================================================
# APPLICATION
# ============================================================

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

app = Flask(
    __name__,
    template_folder=BASE_DIR
)


# ============================================================
# ENVIRONMENT
# ============================================================

ENVIRONMENT = os.getenv(
    "ENVIRONMENT",
    "dev"
).lower()


# ============================================================
# AWS CONFIGURATION
# ============================================================

AWS_REGION = os.getenv(
    "AWS_REGION",
    "ap-south-1"
)

REPORTS_BUCKET = os.getenv(
    "REPORTS_BUCKET",
    "cloudmart-dev-reports-430155298316"
)


# ============================================================
# SSM PARAMETER NAMES
# ============================================================

DB_HOST_PARAMETER = os.getenv(
    "DB_HOST_PARAMETER",
    "/cloudmart/dev/db/host"
)

DB_PORT_PARAMETER = os.getenv(
    "DB_PORT_PARAMETER",
    "/cloudmart/dev/db/port"
)

DB_NAME_PARAMETER = os.getenv(
    "DB_NAME_PARAMETER",
    "/cloudmart/dev/db/name"
)

DB_USERNAME_PARAMETER = os.getenv(
    "DB_USERNAME_PARAMETER",
    "/cloudmart/dev/db/username"
)

DB_PASSWORD_PARAMETER = os.getenv(
    "DB_PASSWORD_PARAMETER",
    "/cloudmart/dev/db/password"
)


# ============================================================
# SESSION CONFIGURATION
# ============================================================

SESSION_TIMEOUT_MINUTES = 60

SESSION_SECRET_FILE = "/etc/cloudmart-dashboard-secret"


def load_session_secret():

    """
    Load the Flask session secret.

    The secret is stored on the EC2 instance instead of
    hard-coding it inside the source code.
    """

    try:

        if os.path.exists(SESSION_SECRET_FILE):

            with open(
                SESSION_SECRET_FILE,
                "r",
                encoding="utf-8"
            ) as secret_file:

                secret = secret_file.read().strip()

                if secret:
                    return secret

    except Exception as error:

        logger.warning(
            "Unable to read session secret file: %s",
            error
        )


    # Development fallback.
    # In the deployed EC2 environment the file is created
    # by the CloudFormation UserData.
    return os.getenv(
        "FLASK_SECRET_KEY",
        "cloudmart-development-secret-change-me"
    )


app.secret_key = load_session_secret()

app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(
    minutes=SESSION_TIMEOUT_MINUTES
)

app.config["SESSION_COOKIE_HTTPONLY"] = True

app.config["SESSION_COOKIE_SAMESITE"] = "Lax"


# ============================================================
# AWS CLIENTS
# ============================================================

session_boto = boto3.Session(
    region_name=AWS_REGION
)

ssm = session_boto.client("ssm")

s3 = session_boto.client("s3")


# ============================================================
# DATABASE CONNECTION
# ============================================================

def get_ssm_parameter(parameter_name, with_decryption=False):

    response = ssm.get_parameter(
        Name=parameter_name,
        WithDecryption=with_decryption
    )

    return response["Parameter"]["Value"]


def get_db_connection():

    """
    Get database connection information from SSM Parameter Store
    and create a MySQL connection to RDS.
    """

    db_host = get_ssm_parameter(
        DB_HOST_PARAMETER
    )

    db_port = int(
        get_ssm_parameter(
            DB_PORT_PARAMETER
        )
    )

    db_name = get_ssm_parameter(
        DB_NAME_PARAMETER
    )

    db_username = get_ssm_parameter(
        DB_USERNAME_PARAMETER
    )

    db_password = get_ssm_parameter(
        DB_PASSWORD_PARAMETER,
        with_decryption=True
    )


    connection = pymysql.connect(
        host=db_host,
        port=db_port,
        user=db_username,
        password=db_password,
        database=db_name,
        cursorclass=pymysql.cursors.DictCursor,
        connect_timeout=10,
        read_timeout=15,
        write_timeout=15,
        autocommit=True
    )

    return connection


# ============================================================
# AUTHENTICATION HELPERS
# ============================================================

def hash_token(token):

    return hashlib.sha256(
        token.encode("utf-8")
    ).hexdigest()


def is_authenticated():

    return (
        session.get("authenticated") is True
        and session.get("admin_role") == "ADMIN"
    )


def login_required(function):

    @wraps(function)
    def decorated_function(*args, **kwargs):

        if not is_authenticated():

            return redirect(
                url_for("index")
            )

        return function(*args, **kwargs)

    return decorated_function


# ============================================================
# SESSION ACTIVITY
# ============================================================

@app.before_request
def refresh_session_activity():

    """
    Keep the session alive while the administrator is active.

    Every request resets the inactivity timer.

    After 60 minutes without a request, the session expires.
    """

    if request.endpoint == "static":
        return

    if not session.get("authenticated"):
        return

    last_activity = session.get(
        "last_activity"
    )

    if not last_activity:

        session.clear()
        return

    try:

        last_activity_time = datetime.fromisoformat(
            last_activity
        )

        current_time = datetime.now(
            timezone.utc
        )

        elapsed = (
            current_time - last_activity_time
        ).total_seconds()

        if elapsed > SESSION_TIMEOUT_MINUTES * 60:

            session.clear()

            if request.endpoint != "index":

                return redirect(
                    url_for("index")
                )

            return


        # Activity detected.
        # Reset the inactivity timer.
        session["last_activity"] = (
            current_time.isoformat()
        )

        session.permanent = True

    except Exception:

        session.clear()


# ============================================================
# DATABASE QUERY HELPER
# ============================================================

def execute_query(query, params=None):

    connection = None

    try:

        connection = get_db_connection()

        with connection.cursor() as cursor:

            cursor.execute(
                query,
                params or ()
            )

            return cursor.fetchall()

    finally:

        if connection:

            connection.close()


# ============================================================
# DASHBOARD STATISTICS
# ============================================================

def get_dashboard_stats():

    stats = {
        "total_orders": 0,
        "confirmed_orders": 0,
        "failed_orders": 0,
        "order_items": 0,
        "active_products": 0,
        "total_users": 0,
        "total_revenue": 0,
        "reports_generated": 0
    }


    # --------------------------------------------------------
    # TOTAL ORDERS
    # --------------------------------------------------------

    result = execute_query(
        """
        SELECT COUNT(*) AS count
        FROM orders
        """
    )

    stats["total_orders"] = result[0]["count"]


    # --------------------------------------------------------
    # CONFIRMED ORDERS
    # --------------------------------------------------------

    result = execute_query(
        """
        SELECT COUNT(*) AS count
        FROM orders
        WHERE UPPER(status) = 'CONFIRMED'
        """
    )

    stats["confirmed_orders"] = result[0]["count"]


    # --------------------------------------------------------
    # FAILED ORDERS
    # --------------------------------------------------------

    result = execute_query(
        """
        SELECT COUNT(*) AS count
        FROM orders
        WHERE UPPER(status) = 'FAILED'
        """
    )

    stats["failed_orders"] = result[0]["count"]


    # --------------------------------------------------------
    # ORDER ITEMS
    # --------------------------------------------------------

    result = execute_query(
        """
        SELECT COUNT(*) AS count
        FROM order_items
        """
    )

    stats["order_items"] = result[0]["count"]


    # --------------------------------------------------------
    # ACTIVE PRODUCTS
    # --------------------------------------------------------

    result = execute_query(
        """
        SELECT COUNT(*) AS count
        FROM products
        WHERE is_deleted = FALSE
        """
    )

    stats["active_products"] = result[0]["count"]


    # --------------------------------------------------------
    # USERS
    # --------------------------------------------------------

    result = execute_query(
        """
        SELECT COUNT(*) AS count
        FROM users
        """
    )

    stats["total_users"] = result[0]["count"]


    # --------------------------------------------------------
    # TOTAL REVENUE
    #
    # Revenue is calculated from CONFIRMED orders only.
    # --------------------------------------------------------

    result = execute_query(
        """
        SELECT COALESCE(
            SUM(total_amount),
            0
        ) AS revenue
        FROM orders
        WHERE UPPER(status) = 'CONFIRMED'
        """
    )

    stats["total_revenue"] = (
        result[0]["revenue"] or 0
    )


    # --------------------------------------------------------
    # REPORT COUNT
    # --------------------------------------------------------

    try:

        response = s3.list_objects_v2(
            Bucket=REPORTS_BUCKET,
            Prefix="reports/"
        )

        reports = response.get(
            "Contents",
            []
        )

        stats["reports_generated"] = len(
            [
                item
                for item in reports
                if item["Key"].lower().endswith(".csv")
            ]
        )

    except Exception as error:

        logger.warning(
            "Unable to count reports: %s",
            error
        )

        stats["reports_generated"] = 0


    return stats


# ============================================================
# PRODUCTS
# ============================================================

def get_products():

    return execute_query(
        """
        SELECT
            p.product_id,
            p.name,
            p.category,
            p.price,
            p.is_deleted,
            COALESCE(
                i.stock_count,
                0
            ) AS stock_count,
            COALESCE(
                i.low_stock_threshold,
                0
            ) AS low_stock_threshold
        FROM products p
        LEFT JOIN inventory i
            ON p.product_id = i.product_id
        ORDER BY p.product_id
        """
    )


# ============================================================
# USERS
# ============================================================

def get_users():

    return execute_query(
        """
        SELECT
            user_id,
            name,
            email,
            role,
            created_at,
            updated_at
        FROM users
        ORDER BY user_id
        """
    )


# ============================================================
# INVENTORY
# ============================================================

def get_inventory():

    return execute_query(
        """
        SELECT
            i.inventory_id,
            i.product_id,
            p.name AS product_name,
            i.stock_count,
            i.low_stock_threshold,
            i.updated_at
        FROM inventory i
        INNER JOIN products p
            ON i.product_id = p.product_id
        ORDER BY i.product_id
        """
    )


# ============================================================
# ORDER ITEMS
# ============================================================

def get_order_items():

    return execute_query(
        """
        SELECT
            oi.order_item_id,
            oi.order_id,
            oi.product_id,
            p.name AS product_name,
            oi.quantity,
            oi.unit_price,
            oi.subtotal
        FROM order_items oi
        INNER JOIN products p
            ON oi.product_id = p.product_id
        ORDER BY oi.order_item_id DESC
        LIMIT 200
        """
    )


# ============================================================
# ORDERS
# ============================================================

def get_orders():

    return execute_query(
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
        LEFT JOIN users u
            ON o.customer_id = u.user_id
        ORDER BY o.created_at DESC
        LIMIT 200
        """
    )


# ============================================================
# REPORTS
# ============================================================

def get_reports():

    reports = []

    try:

        response = s3.list_objects_v2(
            Bucket=REPORTS_BUCKET,
            Prefix="reports/"
        )

        for item in response.get(
            "Contents",
            []
        ):

            key = item["Key"]

            if not key.lower().endswith(".csv"):
                continue

            reports.append(
                {
                    "key": key,
                    "name": key.split("/")[-1],
                    "size": item.get("Size", 0),
                    "last_modified": item.get(
                        "LastModified"
                    )
                }
            )

    except Exception as error:

        logger.exception(
            "Unable to load reports: %s",
            error
        )


    reports.sort(
        key=lambda item: item["last_modified"] or datetime.min.replace(
            tzinfo=timezone.utc
        ),
        reverse=True
    )

    return reports


# ============================================================
# LOGIN
# ============================================================

@app.route(
    "/",
    methods=["GET"]
)
def index():

    if is_authenticated():

        try:

            stats = get_dashboard_stats()

            products = get_products()

            users = get_users()

            inventory = get_inventory()

            order_items = get_order_items()

            orders = get_orders()

            reports = get_reports()


            return render_template(
                "index.html",
                authenticated=True,
                admin_name=session.get(
                    "admin_name",
                    "Administrator"
                ),
                admin_role=session.get(
                    "admin_role",
                    "ADMIN"
                ),
                stats=stats,
                products=products,
                users=users,
                inventory=inventory,
                order_items=order_items,
                orders=orders,
                reports=reports,
                environment=ENVIRONMENT.upper(),
                session_timeout_minutes=SESSION_TIMEOUT_MINUTES
            )

        except Exception as error:

            logger.exception(
                "Dashboard loading failed"
            )

            return render_template(
                "index.html",
                authenticated=True,
                admin_name=session.get(
                    "admin_name",
                    "Administrator"
                ),
                admin_role=session.get(
                    "admin_role",
                    "ADMIN"
                ),
                stats={
                    "total_orders": 0,
                    "confirmed_orders": 0,
                    "failed_orders": 0,
                    "order_items": 0,
                    "active_products": 0,
                    "total_users": 0,
                    "total_revenue": 0,
                    "reports_generated": 0
                },
                products=[],
                users=[],
                inventory=[],
                order_items=[],
                orders=[],
                reports=[],
                environment=ENVIRONMENT.upper(),
                session_timeout_minutes=SESSION_TIMEOUT_MINUTES,
                dashboard_error=str(error)
            )


    # --------------------------------------------------------
    # LOGIN PAGE
    #
    # Login is contained inside index.html.
    # --------------------------------------------------------

    return render_template(
        "index.html",
        authenticated=False,
        environment=ENVIRONMENT.upper(),
        session_timeout_minutes=SESSION_TIMEOUT_MINUTES
    )


# ============================================================
# LOGIN PROCESS
# ============================================================

@app.route(
    "/login",
    methods=["POST"]
)
def login():

    email = (
        request.form.get(
            "email",
            ""
        )
        .strip()
        .lower()
    )

    admin_token = request.form.get(
        "admin_token",
        ""
    )


    if not email or not admin_token:

        return render_template(
            "index.html",
            authenticated=False,
            environment=ENVIRONMENT.upper(),
            login_error="Email and admin token are required."
        )


    token_hash = hash_token(
        admin_token
    )


    connection = None

    try:

        connection = get_db_connection()

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
                    email,
                    token_hash
                )
            )

            admin = cursor.fetchone()


        if not admin:

            logger.warning(
                "Invalid admin login attempt for %s",
                email
            )

            return render_template(
                "index.html",
                authenticated=False,
                environment=ENVIRONMENT.upper(),
                login_error="Invalid administrator credentials."
            )


        # ----------------------------------------------------
        # CREATE ADMIN SESSION
        # ----------------------------------------------------

        session.clear()

        session.permanent = True

        session["authenticated"] = True

        session["admin_id"] = admin["user_id"]

        session["admin_name"] = admin["name"]

        session["admin_email"] = admin["email"]

        session["admin_role"] = "ADMIN"

        session["last_activity"] = (
            datetime.now(
                timezone.utc
            ).isoformat()
        )


        logger.info(
            "Administrator login successful: %s",
            email
        )


        return redirect(
            url_for("index")
        )


    except Exception as error:

        logger.exception(
            "Admin login failed"
        )

        return render_template(
            "index.html",
            authenticated=False,
            environment=ENVIRONMENT.upper(),
            login_error="Unable to connect to the CloudMart database."
        )


    finally:

        if connection:

            connection.close()


# ============================================================
# LOGOUT
# ============================================================

@app.route(
    "/logout",
    methods=["GET"]
)
def logout():

    admin_email = session.get(
        "admin_email"
    )

    session.clear()

    logger.info(
        "Administrator logged out: %s",
        admin_email
    )

    return redirect(
        url_for("index")
    )


# ============================================================
# REPORT DOWNLOAD
# ============================================================

@app.route(
    "/reports/<path:report_key>",
    methods=["GET"]
)
@login_required
def download_report(report_key):

    """
    Download a report directly through Flask.

    This does NOT create a presigned URL, so there is no
    one-hour URL expiration.
    """

    if not report_key.startswith(
        "reports/"
    ):

        return "Invalid report path.", 400


    try:

        response = s3.get_object(
            Bucket=REPORTS_BUCKET,
            Key=report_key
        )

        filename = os.path.basename(
            report_key
        )


        return send_file(
            response["Body"],
            mimetype=response.get(
                "ContentType",
                "text/csv"
            ),
            as_attachment=True,
            download_name=filename
        )


    except Exception as error:

        logger.exception(
            "Report download failed: %s",
            report_key
        )

        return (
            "Unable to download the requested report.",
            404
        )


# ============================================================
# HEALTH CHECK
# ============================================================

@app.route(
    "/health",
    methods=["GET"]
)
def health():

    return {
        "status": "healthy",
        "application": "CloudMart Dashboard",
        "environment": ENVIRONMENT
    }, 200


# ============================================================
# ERROR HANDLERS
# ============================================================

@app.errorhandler(404)
def page_not_found(error):

    if is_authenticated():

        return render_template(
            "index.html",
            authenticated=True,
            admin_name=session.get(
                "admin_name",
                "Administrator"
            ),
            admin_role="ADMIN",
            stats=get_dashboard_stats(),
            products=get_products(),
            users=get_users(),
            inventory=get_inventory(),
            order_items=get_order_items(),
            orders=get_orders(),
            reports=get_reports(),
            environment=ENVIRONMENT.upper(),
            session_timeout_minutes=SESSION_TIMEOUT_MINUTES
        ), 404


    return render_template(
        "index.html",
        authenticated=False,
        environment=ENVIRONMENT.upper()
    ), 404


@app.errorhandler(500)
def internal_server_error(error):

    logger.exception(
        "Internal server error"
    )

    return (
        "CloudMart Dashboard internal server error.",
        500
    )


# ============================================================
# APPLICATION START
# ============================================================

if __name__ == "__main__":

    app.run(
        host="0.0.0.0",
        port=5000,
        debug=False
    )