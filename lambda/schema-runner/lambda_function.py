import json
import os

import boto3
import pymysql


ssm = boto3.client("ssm")


def get_parameter(name):
    response = ssm.get_parameter(
        Name=name,
        WithDecryption=True
    )

    return response["Parameter"]["Value"]


def get_database_credentials():

    environment = os.environ.get("ENVIRONMENT", "dev")

    prefix = f"/cloudmart/{environment}/db"

    return {
        "host": get_parameter(f"{prefix}/host"),
        "port": int(get_parameter(f"{prefix}/port")),
        "database": get_parameter(f"{prefix}/name"),
        "username": get_parameter(f"{prefix}/username"),
        "password": get_parameter(f"{prefix}/password")
    }


def execute_schema(connection):

    schema_path = os.path.join(
        os.path.dirname(__file__),
        "schema.sql"
    )

    with open(schema_path, "r", encoding="utf-8") as file:
        sql = file.read()

    # Remove SQL comments
    lines = []

    for line in sql.splitlines():

        stripped = line.strip()

        if stripped.startswith("--"):
            continue

        lines.append(line)

    cleaned_sql = "\n".join(lines)

    # The schema contains simple statements separated by ;
    statements = [
        statement.strip()
        for statement in cleaned_sql.split(";")
        if statement.strip()
    ]

    with connection.cursor() as cursor:

        for statement in statements:

            cursor.execute(statement)

            print(
                json.dumps(
                    {
                        "event": "sql_statement_executed",
                        "status": "success"
                    }
                )
            )

    connection.commit()


def lambda_handler(event, context):

    print(
        json.dumps(
            {
                "event": "schema_deployment_started",
                "environment": os.environ.get(
                    "ENVIRONMENT",
                    "dev"
                )
            }
        )
    )

    connection = None

    try:

        db = get_database_credentials()

        connection = pymysql.connect(
            host=db["host"],
            port=db["port"],
            user=db["username"],
            password=db["password"],
            database=db["database"],
            connect_timeout=10,
            read_timeout=30,
            write_timeout=30,
            autocommit=False
        )

        print(
            json.dumps(
                {
                    "event": "rds_connection",
                    "status": "success"
                }
            )
        )

        execute_schema(connection)

        print(
            json.dumps(
                {
                    "event": "schema_deployment_completed",
                    "status": "success"
                }
            )
        )

        return {
            "statusCode": 200,
            "body": json.dumps(
                {
                    "message": "RDS schema deployed successfully"
                }
            )
        }

    except Exception as error:

        print(
            json.dumps(
                {
                    "event": "schema_deployment_failed",
                    "status": "failed",
                    "error": str(error)
                }
            )
        )

        if connection:
            connection.rollback()

        raise

    finally:

        if connection:
            connection.close()