import json
import os
import boto3
import hmac


# =========================================================
# AWS CLIENT
# =========================================================

ssm = boto3.client("ssm")


# =========================================================
# ENVIRONMENT VARIABLES
# =========================================================

USER_TOKEN_PARAMETER = os.environ[
    "USER_TOKEN_PARAMETER"
]

ADMIN_TOKEN_PARAMETER = os.environ[
    "ADMIN_TOKEN_PARAMETER"
]


# =========================================================
# GET TOKEN FROM SSM
# =========================================================

def get_token(parameter_name):

    response = ssm.get_parameter(
        Name=parameter_name,
        WithDecryption=True
    )

    return response["Parameter"]["Value"]


# =========================================================
# CREATE IAM POLICY
# =========================================================

def create_policy(
    principal_id,
    effect,
    resource,
    role
):

    return {

        "principalId": principal_id,

        "policyDocument": {

            "Version": "2012-10-17",

            "Statement": [

                {
                    "Action": "execute-api:Invoke",

                    "Effect": effect,

                    "Resource": resource
                }

            ]
        },

        "context": {

            "role": role

        }
    }


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

            raise Exception("Unauthorized")


        # =================================================
        # GET METHOD ARN
        # =================================================

        method_arn = event.get(
            "methodArn"
        )

        if not method_arn:

            raise Exception(
                "Missing methodArn"
            )


        # =================================================
        # EXTRACT HTTP METHOD
        # =================================================

        arn_parts = method_arn.split("/")

        if len(arn_parts) < 3:

            raise Exception(
                "Invalid methodArn"
            )

        http_method = arn_parts[2].upper()


        # =================================================
        # GET USER TOKEN
        # =================================================

        user_token = get_token(
            USER_TOKEN_PARAMETER
        )


        # =================================================
        # CHECK USER TOKEN
        # =================================================

        if hmac.compare_digest(
            provided_token,
            user_token
        ):

            role = "USER"


        else:

            # =============================================
            # GET ADMIN TOKEN
            # =============================================

            admin_token = get_token(
                ADMIN_TOKEN_PARAMETER
            )


            # =============================================
            # CHECK ADMIN TOKEN
            # =============================================

            if hmac.compare_digest(
                provided_token,
                admin_token
            ):

                role = "ADMIN"

            else:

                print(json.dumps({
                    "event": "authorization_failed",
                    "reason": "invalid_token"
                }))

                raise Exception("Unauthorized")


        # =================================================
        # USER ACCESS
        #
        # USER = READ ONLY
        # =================================================

        if role == "USER":

            if http_method == "GET":

                print(json.dumps({
                    "event": "authorization_success",
                    "role": "USER",
                    "method": http_method
                }))

                return create_policy(
                    "cloudmart-user",
                    "Allow",
                    method_arn,
                    "USER"
                )


            print(json.dumps({
                "event": "authorization_denied",
                "role": "USER",
                "method": http_method
            }))

            return create_policy(
                "cloudmart-user",
                "Deny",
                method_arn,
                "USER"
            )


        # =================================================
        # ADMIN ACCESS
        #
        # ADMIN = FULL PRODUCT CRUD
        # =================================================

        if role == "ADMIN":

            allowed_methods = {
                "GET",
                "POST",
                "PUT",
                "DELETE"
            }

            if http_method in allowed_methods:

                print(json.dumps({
                    "event": "authorization_success",
                    "role": "ADMIN",
                    "method": http_method
                }))

                return create_policy(
                    "cloudmart-admin",
                    "Allow",
                    method_arn,
                    "ADMIN"
                )


            print(json.dumps({
                "event": "authorization_denied",
                "role": "ADMIN",
                "method": http_method
            }))

            return create_policy(
                "cloudmart-admin",
                "Deny",
                method_arn,
                "ADMIN"
            )


        # =================================================
        # UNKNOWN ROLE
        # =================================================

        raise Exception("Unauthorized")


    # =====================================================
    # AUTHORIZATION ERROR
    # =====================================================

    except Exception as error:

        print(json.dumps({
            "event": "authorization_error",
            "reason": str(error)
        }))

        raise Exception("Unauthorized")