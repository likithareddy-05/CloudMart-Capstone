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

USER_TOKEN_PARAMETER = os.environ["USER_TOKEN_PARAMETER"]

ADMIN_TOKEN_PARAMETER = os.environ["ADMIN_TOKEN_PARAMETER"]


# =========================================================
# USER IDs
#
# These IDs correspond to the sample users created
# in the CloudMart users table.
# =========================================================

USER_ID = 1
ADMIN_ID = 2


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
    role,
    user_id
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

            "role": role,

            "user_id": str(user_id)

        }
    }


# =========================================================
# CREATE API ARN BASE
# =========================================================

def get_api_arn_base(method_arn):

    """
    Example methodArn:

    arn:aws:execute-api:ap-south-1:123456789012:api-id/dev/GET/products/1

    We extract:

    arn:aws:execute-api:ap-south-1:123456789012:api-id/dev
    """

    arn_parts = method_arn.split("/")

    if len(arn_parts) < 3:

        raise Exception("Invalid methodArn")

    api_arn_base = "/".join(
        arn_parts[:2]
    )

    return api_arn_base


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

            user_id = USER_ID

            print(json.dumps({
                "event": "token_validated",
                "role": role,
                "user_id": user_id,
                "method": http_method
            }))


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

                user_id = ADMIN_ID

                print(json.dumps({
                    "event": "token_validated",
                    "role": role,
                    "user_id": user_id,
                    "method": http_method
                }))


            else:

                print(json.dumps({
                    "event": "authorization_failed",
                    "reason": "invalid_token"
                }))

                raise Exception("Unauthorized")


        # =================================================
        # USER POLICY
        #
        # USER CAN READ PRODUCTS ONLY
        # =================================================

        if role == "USER":

            user_resource = (
                api_arn_base
                + "/GET/*"
            )

            print(json.dumps({
                "event": "authorization_success",
                "role": "USER",
                "user_id": user_id,
                "allowed_method": "GET"
            }))

            return create_policy(
                "cloudmart-user",
                "Allow",
                user_resource,
                "USER",
                user_id
            )


        # =================================================
        # ADMIN POLICY
        #
        # ADMIN CAN:
        #
        # GET
        # POST
        # PUT
        # DELETE
        # =================================================

        if role == "ADMIN":

            admin_resource = (
                api_arn_base
                + "/*/*"
            )

            print(json.dumps({
                "event": "authorization_success",
                "role": "ADMIN",
                "user_id": user_id,
                "allowed_methods": [
                    "GET",
                    "POST",
                    "PUT",
                    "DELETE"
                ]
            }))

            return create_policy(
                "cloudmart-admin",
                "Allow",
                admin_resource,
                "ADMIN",
                user_id
            )


        # =================================================
        # UNKNOWN ROLE
        # =================================================

        print(json.dumps({
            "event": "authorization_failed",
            "reason": "unknown_role"
        }))

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