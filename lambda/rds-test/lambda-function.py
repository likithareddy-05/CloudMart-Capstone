import json
import os
import pymysql


def lambda_handler(event, context):

    host = os.environ["DB_HOST"]
    port = int(os.environ.get("DB_PORT", "3306"))
    database = os.environ["DB_NAME"]
    username = os.environ["DB_USERNAME"]
    password = os.environ["DB_PASSWORD"]

    try:

        connection = pymysql.connect(
            host=host,
            port=port,
            user=username,
            password=password,
            database=database,
            connect_timeout=10
        )

        with connection.cursor() as cursor:

            cursor.execute("SELECT 1")

            result = cursor.fetchone()

        connection.close()

        print(json.dumps({
            "message": "RDS connection successful",
            "query_result": result[0]
        }))

        return {
            "statusCode": 200,
            "body": json.dumps({
                "message": "RDS connection successful",
                "query_result": result[0]
            })
        }

    except Exception as e:

        print(json.dumps({
            "message": "RDS connection failed",
            "error": str(e)
        }))

        return {
            "statusCode": 500,
            "body": json.dumps({
                "message": "RDS connection failed",
                "error": str(e)
            })
        }