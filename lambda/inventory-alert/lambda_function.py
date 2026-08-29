import json
import os
import boto3


# =========================================================
# AWS CLIENTS
# =========================================================

sns = boto3.client("sns")


# =========================================================
# ENVIRONMENT VARIABLES
# =========================================================

SNS_TOPIC_ARN = os.environ["SNS_TOPIC_ARN"]


# =========================================================
# STRUCTURED LOGGING
# =========================================================

def log_event(event_name, **details):

    log_data = {
        "event": event_name,
        **details
    }

    print(
        json.dumps(
            log_data,
            default=str
        )
    )


# =========================================================
# LAMBDA HANDLER
# =========================================================

def lambda_handler(event, context):

    log_event(
        "inventory_alert_event_received",
        event=event
    )

    try:

        # =================================================
        # GET EVENT DETAIL
        # =================================================

        detail = event.get(
            "detail",
            {}
        )

        product_id = detail.get(
            "product_id"
        )

        product_name = detail.get(
            "product_name"
        )

        stock_count = detail.get(
            "stock_count"
        )

        low_stock_threshold = detail.get(
            "low_stock_threshold"
        )


        # =================================================
        # VALIDATE EVENT
        # =================================================

        if product_id is None:

            raise ValueError(
                "Missing product_id in event"
            )


        if stock_count is None:

            raise ValueError(
                "Missing stock_count in event"
            )


        if low_stock_threshold is None:

            raise ValueError(
                "Missing low_stock_threshold in event"
            )


        # =================================================
        # LOW STOCK CHECK
        # =================================================

        if stock_count <= low_stock_threshold:

            subject = (
                "CloudMart Low Stock Alert"
            )

            message = (
                "CloudMart Low Stock Alert\n\n"

                f"Product ID: {product_id}\n"

                f"Product Name: {product_name}\n"

                f"Current Stock: {stock_count}\n"

                f"Low Stock Threshold: "
                f"{low_stock_threshold}\n\n"

                "Please review the inventory."
            )


            # =============================================
            # SEND SNS NOTIFICATION
            # =============================================

            response = sns.publish(

                TopicArn=SNS_TOPIC_ARN,

                Subject=subject,

                Message=message
            )


            # =============================================
            # LOG SUCCESS
            # =============================================

            log_event(

                "low_stock_alert_sent",

                product_id=product_id,

                product_name=product_name,

                stock_count=stock_count,

                low_stock_threshold=low_stock_threshold,

                sns_message_id=response[
                    "MessageId"
                ],

                status="success"
            )


            return {

                "statusCode": 200,

                "body": json.dumps({

                    "message":
                        "Low-stock alert sent",

                    "product_id":
                        product_id

                })
            }


        # =================================================
        # STOCK IS ABOVE THRESHOLD
        # =================================================

        log_event(

            "low_stock_alert_not_required",

            product_id=product_id,

            product_name=product_name,

            stock_count=stock_count,

            low_stock_threshold=low_stock_threshold,

            status="success"
        )


        return {

            "statusCode": 200,

            "body": json.dumps({

                "message":
                    "Stock level is healthy",

                "product_id":
                    product_id

            })
        }


    # =====================================================
    # ERROR HANDLING
    # =====================================================

    except Exception as error:

        log_event(

            "inventory_alert_failed",

            error=str(error),

            status="failed"
        )


        return {

            "statusCode": 500,

            "body": json.dumps({

                "message":
                    "Inventory alert processing failed",

                "error":
                    str(error)

            })
        }