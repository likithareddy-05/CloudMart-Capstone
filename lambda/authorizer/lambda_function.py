import json
import os
import boto3
import hmac


ssm = boto3.client("ssm")

TOKEN_PARAMETER = os.environ["TOKEN_PARAMETER"]


def lambda_handler(event, context):

    try:

        # -------------------------------------------------
        # Get Authorization header
        # -------------------------------------------------

        headers = event.get("headers") or {}

        authorization = (
            headers.get("Authorization")
            or headers.get("authorization")
        )

        if not authorization:
            print(json.dumps({
                "event": "authorization_failed",
                "reason": "missing_authorization_header"
            }))

            raise Exception("Unauthorized")


        # -------------------------------------------------
        # Validate Bearer token format
        # -------------------------------------------------

        parts = authorization.split(" ", 1)

        if len(parts) != 2 or parts[0].lower() != "bearer":

            print(json.dumps({
                "event": "authorization_failed",
                "reason": "invalid_authorization_format"
            }))

            raise Exception("Unauthorized")


        provided_token = parts[1]


        # -------------------------------------------------
        # Read expected token from SSM
        # -------------------------------------------------

        response = ssm.get_parameter(
            Name=TOKEN_PARAMETER,
            WithDecryption=True
        )

        expected_token = response["Parameter"]["Value"]


        # -------------------------------------------------
        # Compare tokens securely
        # -------------------------------------------------

        if not hmac.compare_digest(
            provided_token,
            expected_token
        ):

            print(json.dumps({
                "event": "authorization_failed",
                "reason": "invalid_token"
            }))

            raise Exception("Unauthorized")


        # -------------------------------------------------
        # Token is valid
        # -------------------------------------------------

        print(json.dumps({
            "event": "authorization_success"
        }))


        # -------------------------------------------------
        # IAM policy for API Gateway
        # -------------------------------------------------

        method_arn = event.get("methodArn", "*")

        policy = {
            "principalId": "cloudmart-user",
            "policyDocument": {
                "Version": "2012-10-17",
                "Statement": [
                    {
                        "Action": "execute-api:Invoke",
                        "Effect": "Allow",
                        "Resource": method_arn
                    }
                ]
            }
        }

        return policy


    except Exception as error:

        print(json.dumps({
            "event": "authorization_error",
            "reason": str(error)
        }))

        raise Exception("Unauthorized")