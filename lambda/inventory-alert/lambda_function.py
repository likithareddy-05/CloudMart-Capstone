import json
import os
import boto3


sns = boto3.client("sns")


SNS_TOPIC_ARN = os.environ["SNS_TOPIC_ARN"]


def log_event(event_name, **details):

    log_data = {
        "event": event_name,
        **details
    }

    print(json.dumps(log_data))


def lambda_handler(event, context):

    log_event(
        "inventory_alert_event_received",
        event=event
    )

    try:

        detail = event.get("detail", {})

        product_id = detail.get("product_id")
        product_name = detail.get("product_name")
        quantity = detail.get("quantity")
        reorder_level = detail.get("reorder_level")

        if product_id is None:
            raise ValueError(
                "Missing product_id in event"
            )

        if quantity is None:
            raise ValueError(
                "Missing quantity in event"
            )

        if reorder_level is None:
            raise ValueError(
                "Missing reorder_level in event"
            )

        # -------------------------------------------------
        # LOW STOCK CHECK
        # -------------------------------------------------

        if quantity <= reorder_level:

            subject = "CloudMart Low Stock Alert"

            message = (
                "CloudMart Low Stock Alert\n\n"
                f"Product ID: {product_id}\n"
                f"Product Name: {product_name}\n"
                f"Current Quantity: {quantity}\n"
                f"Reorder Level: {reorder_level}\n\n"
                "Please review the inventory."
            )

            response = sns.publish(
                TopicArn=SNS_TOPIC_ARN,
                Subject=subject,
                Message=message
            )

            log_event(
                "low_stock_alert_sent",
                product_id=product_id,
                product_name=product_name,
                quantity=quantity,
                reorder_level=reorder_level,
                sns_message_id=response["MessageId"],
                status="success"
            )

            return {
                "statusCode": 200,
                "body": json.dumps({
                    "message": "Low-stock alert sent",
                    "product_id": product_id
                })
            }

        # -------------------------------------------------
        # STOCK IS ABOVE THRESHOLD
        # -------------------------------------------------

        log_event(
            "low_stock_alert_not_required",
            product_id=product_id,
            product_name=product_name,
            quantity=quantity,
            reorder_level=reorder_level,
            status="success"
        )

        return {
            "statusCode": 200,
            "body": json.dumps({
                "message": "Stock level is healthy",
                "product_id": product_id
            })
        }

    except Exception as error:

        log_event(
            "inventory_alert_failed",
            error=str(error),
            status="failed"
        )

        raise