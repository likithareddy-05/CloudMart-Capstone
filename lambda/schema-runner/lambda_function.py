import json
import os
import traceback

# to setup database schema
import boto3
import pymysql

# Gets DB credentials from SSM
ssm = boto3.client("ssm")


def log_event(event_name, **details):
    print(
        json.dumps(
            {
                "event": event_name,
                **details
            },
            default=str
        )
    )


def log_error(event_name, error, **details):
    log_event(
        event_name,
        error_type=type(error).__name__,
        error=str(error),
        **details
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


def get_parameter(name):
    try:
        response = ssm.get_parameter(
            Name=name,
            WithDecryption=True
        )

        return response["Parameter"]["Value"]

    except Exception as error:
        log_error(
            "ssm_parameter_fetch_failed",
            error,
            parameter_name=name
        )
        raise


def get_database_credentials():

    environment = os.environ.get(
        "ENVIRONMENT",
        "dev"
    )

    prefix = f"/cloudmart/{environment}/db"

    try:
        return {
            "host": get_parameter(f"{prefix}/host"),
            "port": int(get_parameter(f"{prefix}/port")),
            "database": get_parameter(f"{prefix}/name"),
            "username": get_parameter(f"{prefix}/username"),
            "password": get_parameter(f"{prefix}/password")
        }

    except Exception as error:
        log_error(
            "database_credentials_fetch_failed",
            error,
            environment=environment
        )
        raise


# Connects to RDS MySQL
def execute_schema(connection):

    schema_path = os.path.join(
        os.path.dirname(__file__),
        "schema.sql"
    )

    # Reads schema.sql
    try:
        with open(
            schema_path,
            "r",
            encoding="utf-8"
        ) as file:
            sql = file.read()

    except Exception as error:
        log_error(
            "schema_file_read_failed",
            error,
            schema_file="schema.sql"
        )
        raise

    # Remove SQL comments
    lines = []

    for line in sql.splitlines():

        stripped = line.strip()

        if stripped.startswith("--"):
            continue

        lines.append(line)

    # Splits SQL statements
    statements = [
        statement.strip()
        for statement in "\n".join(lines).split(";")
        if statement.strip()
    ]

    with connection.cursor() as cursor:

        for statement_number, statement in enumerate(
            statements,
            start=1
        ):

            try:
                cursor.execute(statement)

                print(
                    json.dumps(
                        {
                            "event": "sql_statement_executed",
                            "statement_number": statement_number,
                            "status": "success"
                        }
                    )
                )

            except Exception as error:
                log_error(
                    "sql_statement_execution_failed",
                    error,
                    statement_number=statement_number,
                    statement_count=len(statements)
                )
                raise

    try:
        connection.commit()

    except Exception as error:
        log_error(
            "schema_transaction_commit_failed",
            error
        )
        raise


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

        try:
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

        except Exception as error:
            log_error(
                "rds_connection_failed",
                error,
                database=db["database"],
                port=db["port"]
            )
            raise

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

        log_error(
            "schema_deployment_failed",
            error,
            environment=os.environ.get(
                "ENVIRONMENT",
                "dev"
            )
        )

        if connection:

            try:
                connection.rollback()

            except Exception as rollback_error:
                log_error(
                    "schema_transaction_rollback_failed",
                    rollback_error
                )

        raise

    finally:

        if connection:

            try:
                connection.close()

            except Exception as error:
                log_error(
                    "rds_connection_close_failed",
                    error
                )
