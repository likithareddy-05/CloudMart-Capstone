import json
import os
import hashlib
import traceback

import boto3
import pymysql


# =========================================================
# AWS CLIENT
# =========================================================

ssm = boto3.client("ssm")


def log_error(event_name, error, **kwargs):
    """Write structured CloudWatch error logs without logging secrets/tokens."""
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

DB_HOST_PARAMETER = os.environ["DB_HOST_PARAMETER"]
DB_PORT_PARAMETER = os.environ["DB_PORT_PARAMETER"]
DB_NAME_PARAMETER = os.environ["DB_NAME_PARAMETER"]
DB_USERNAME_PARAMETER = os.environ["DB_USERNAME_PARAMETER"]
DB_PASSWORD_PARAMETER = os.environ["DB_PASSWORD_PARAMETER"]


# =========================================================
# GET PARAMETER FROM SSM
# =========================================================

def get_parameter(parameter_name):
    try:
        response = ssm.get_parameter(
            Name=parameter_name,
            WithDecryption=True
        )
        return response["Parameter"]["Value"]
    except Exception as error:
        log_error(
            "ssm_parameter_fetch_failed",
            error,
            parameter_name=parameter_name
        )
        raise


# =========================================================
# GET DATABASE CONNECTION
# =========================================================

def get_db_connection():
    try:
        host = get_parameter(DB_HOST_PARAMETER)
        port = int(get_parameter(DB_PORT_PARAMETER))
        database = get_parameter(DB_NAME_PARAMETER)
        username = get_parameter(DB_USERNAME_PARAMETER)
        password = get_parameter(DB_PASSWORD_PARAMETER)
    except Exception as error:
        log_error(
            "database_credentials_fetch_failed",
            error,
            parameter_group="DB_*_PARAMETER"
        )
        raise

    try:
        return pymysql.connect(
            host=host,
            port=port,
            user=username,
            password=password,
            database=database,
            connect_timeout=5,
            read_timeout=5,
            write_timeout=5,
            cursorclass=pymysql.cursors.DictCursor
        )
    except Exception as error:
        log_error(
            "rds_connection_failed",
            error,
            database=database
        )
        raise


# =========================================================
# HASH TOKEN
# =========================================================

def hash_token(token):
    return hashlib.sha256(
        token.encode("utf-8")
    ).hexdigest()


# =========================================================
# FIND USER BY TOKEN
# =========================================================

def get_user_by_token(provided_token):
    token_hash = hash_token(provided_token)

    connection = None

    try:
        connection = get_db_connection()

        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT
                        user_id,
                        role
                    FROM users
                    WHERE token_hash = %s
                    LIMIT 1
                    """,
                    (token_hash,)
                )
                return cursor.fetchone()
        except Exception as error:
            # Never log the raw token or token hash.
            log_error(
                "user_token_lookup_failed",
                error,
                operation="user_token_database_lookup"
            )
            raise

    finally:
        if connection:
            try:
                connection.close()
            except Exception as error:
                log_error(
                    "database_connection_close_failed",
                    error
                )


# =========================================================
# CREATE IAM POLICY
# =========================================================

def create_policy(
    principal_id,
    effect,
    resources,
    role,
    user_id=None
):

    statements = []

    for resource in resources:
        statements.append(
            {
                "Action": "execute-api:Invoke",
                "Effect": effect,
                "Resource": resource
            }
        )

    context = {
        "role": role
    }

    if user_id is not None:
        context["user_id"] = str(user_id)

    return {
        "principalId": principal_id,
        "policyDocument": {
            "Version": "2012-10-17",
            "Statement": statements
        },
        "context": context
    }


# =========================================================
# CREATE API ARN BASE
# =========================================================

def get_api_arn_base(method_arn):

    arn_parts = method_arn.split("/")

    if len(arn_parts) < 3:
        raise Exception("Invalid methodArn")

    return "/".join(arn_parts[:2])


# =========================================================
# LAMBDA HANDLER
# =========================================================

def lambda_handler(event, context):

    try:

        # =================================================
        # GET AUTHORIZATION TOKEN
        # =================================================

        authorization = event.get(
            "authorizationToken"
        )

        if not authorization:

            print(json.dumps({
                "event": "authorization_failed",
                "reason": "missing_authorization_token"
            }))

            raise Exception("Unauthorized")


        # =================================================
        # VALIDATE BEARER TOKEN FORMAT
        # =================================================

        parts = authorization.split(
            " ",
            1
        )

        if (
            len(parts) != 2
            or parts[0].lower() != "bearer"
        ):

            print(json.dumps({
                "event": "authorization_failed",
                "reason": "invalid_authorization_format"
            }))

            raise Exception("Unauthorized")


        provided_token = parts[1].strip()

        if not provided_token:

            print(json.dumps({
                "event": "authorization_failed",
                "reason": "empty_token"
            }))

            raise Exception("Unauthorized")


        # =================================================
        # GET METHOD ARN
        # =================================================

        print(json.dumps({
            "event": "authorization_request_received"
        }))

        method_arn = event.get(
            "methodArn"
        )

        if not method_arn:

            print(json.dumps({
                "event": "authorization_failed",
                "reason": "missing_method_arn"
            }))

            raise Exception("Unauthorized")


        # =================================================
        # EXTRACT HTTP METHOD
        # =================================================

        arn_parts = method_arn.split("/")

        if len(arn_parts) < 3:

            print(json.dumps({
                "event": "authorization_failed",
                "reason": "invalid_method_arn"
            }))

            raise Exception("Unauthorized")


        http_method = arn_parts[2].upper()


        # =================================================
        # CREATE API ARN BASE
        # =================================================

        api_arn_base = get_api_arn_base(
            method_arn
        )


        # =================================================
        # FIND USER IN RDS
        # =================================================

        print(json.dumps({
            "event": "user_token_lookup_started",
            "method": http_method
        }))

        user = get_user_by_token(
            provided_token
        )


        # =================================================
        # INVALID TOKEN
        # =================================================

        if not user:

            print(json.dumps({
                "event": "authorization_failed",
                "reason": "invalid_token",
                "method": http_method
            }))

            raise Exception("Unauthorized")


        # =================================================
        # GET USER DETAILS
        # =================================================

        user_id = int(user["user_id"])
        role = user["role"].upper()


        print(json.dumps({
            "event": "token_validated",
            "user_id": user_id,
            "role": role,
            "method": http_method
        }))


        # =================================================
        # USER POLICY
        #
        # USER CAN:
        #
        # GET  /*
        # POST /orders
        # PATCH /orders/*
        #
        # USER CANNOT:
        #
        # POST /products
        # PUT  /products/{id}
        # DELETE /products/{id}
        # =================================================

        if role == "USER":

            user_resources = [

                # Read products/orders
                api_arn_base + "/GET/*",

                # Create orders
                api_arn_base + "/POST/orders",

                # Cancel orders
                api_arn_base + "/PATCH/orders/*"
            ]


            print(json.dumps({
                "event": "authorization_success",
                "user_id": user_id,
                "role": "USER",
                "allowed_methods": [
                    "GET",
                    "POST /orders",
                    "PATCH /orders/*"
                ]
            }))


            return create_policy(
                principal_id=f"cloudmart-user-{user_id}",
                effect="Allow",
                resources=user_resources,
                role="USER",
                user_id=user_id
            )


        # =================================================
        # ADMIN POLICY
        #
        # ADMIN CAN:
        #
        # GET
        # POST
        # PUT
        # PATCH
        # DELETE
        #
        # Allow all methods/resources under API stage.
        # =================================================

        if role == "ADMIN":

            admin_resource = [
                api_arn_base + "/GET/*",
                api_arn_base + "/POST/products",
                api_arn_base + "/PUT/products/*",
                api_arn_base + "/DELETE/products/*"
            ]


            print(json.dumps({
                "event": "authorization_success",
                "user_id": user_id,
                "role": "ADMIN",
                "allowed_methods": [
                    "GET",
                    "POST",
                    "PUT",
                    "PATCH",
                    "DELETE"
                ]
            }))


            return create_policy(
                principal_id=f"cloudmart-admin-{user_id}",
                effect="Allow",
                resources= admin_resource,
                role="ADMIN",
                user_id=user_id
            )


        # =================================================
        # UNKNOWN ROLE
        # =================================================

        print(json.dumps({
            "event": "authorization_failed",
            "reason": "unknown_role",
            "user_id": user_id
        }))

        raise Exception("Unauthorized")


    # =====================================================
    # AUTHORIZATION ERROR
    # =====================================================

    except Exception as error:

        log_error(
            "authorization_error",
            error,
            reason="authorization_failed"
        )

        raise Exception("Unauthorized")