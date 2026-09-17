import json
import os
import boto3
import traceback


# =========================================================
# AWS CLIENTS
# =========================================================

sns = boto3.client("sns")
cloudwatch = boto3.client("cloudwatch")


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


def log_error(event_name, error, **details):

    log_data = {
        "event": event_name,
        "error_type": type(error).__name__,
        "error": str(error),
        **details
    }

    print(
        json.dumps(
            log_data,
            default=str
        )
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

        log_event(
            "inventory_alert_event_detail_parsed",
            has_detail=isinstance(detail, dict)
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

        log_event(
            "inventory_alert_event_values_extracted",
            product_id=product_id,
            product_name=product_name,
            stock_count=stock_count,
            low_stock_threshold=low_stock_threshold
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

        log_event(
            "inventory_alert_event_validated",
            product_id=product_id,
            status="success"
        )


        # =================================================
        # LOW STOCK CHECK
        # =================================================

        log_event(
            "inventory_threshold_check_started",
            product_id=product_id,
            stock_count=stock_count,
            low_stock_threshold=low_stock_threshold
        )

        if stock_count <= low_stock_threshold:

            log_event(
                "low_stock_condition_detected",
                product_id=product_id,
                stock_count=stock_count,
                low_stock_threshold=low_stock_threshold
            )

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

            log_event(
                "sns_publish_started",
                product_id=product_id,
                topic_arn=SNS_TOPIC_ARN
            )

            try:
                response = sns.publish(
                    TopicArn=SNS_TOPIC_ARN,
                    Subject=subject,
                    Message=message
                )
            except Exception as sns_error:
                log_error(
                    "sns_publish_failed",
                    sns_error,
                    product_id=product_id,
                    topic_arn=SNS_TOPIC_ARN
                )
                raise

            log_event(
                "sns_publish_succeeded",
                product_id=product_id,
                message_id=response.get("MessageId"),
                status="success"
            )


            # =============================================
            # PUBLISH INVENTORY ALERT METRIC
            # =============================================

            log_event(
                "inventory_alert_metric_publish_started",
                product_id=product_id,
                metric_name="InventoryAlerts",
                namespace="CloudMart"
            )

            try:

                cloudwatch.put_metric_data(

                    Namespace="CloudMart",

                    MetricData=[

                        {
                            "MetricName":
                                "InventoryAlerts",

                            "Value":
                                1,

                            "Unit":
                                "Count"
                        }

                    ]
                )


                log_event(

                    "inventory_alert_metric_published",

                    product_id=product_id,

                    product_name=product_name,

                    status="success"
                )


            except Exception as metric_error:

                log_error(
                    "inventory_alert_metric_failed",
                    metric_error,
                    product_id=product_id,
                    product_name=product_name,
                    metric_name="InventoryAlerts",
                    namespace="CloudMart",
                    status="failed"
                )

                # Metric failure should not undo a successfully
                # sent SNS notification.


            # =============================================
            # LOG SUCCESS
            # =============================================

            log_event(

                "low_stock_alert_sent",

                product_id=product_id,

                product_name=product_name,

                stock_count=stock_count,

                low_stock_threshold=low_stock_threshold,

                sns_message_id=response.get(
                    "MessageId"
                ),

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

        log_error(
            "inventory_alert_failed",
            error,
            product_id=locals().get("product_id"),
            product_name=locals().get("product_name"),
            stock_count=locals().get("stock_count"),
            low_stock_threshold=locals().get("low_stock_threshold"),
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
