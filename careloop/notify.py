"""Send messages to the family through Amazon SNS (SMS, email, or app push).

Set CARELOOP_SNS_TOPIC_ARN and subscribe family phone numbers / emails to the topic.
Without it, messages are only logged and stored, and send() returns False.
"""
from __future__ import annotations

import logging
import os

log = logging.getLogger("careloop.notify")


def send(subject: str, message: str) -> bool:
    topic = os.getenv("CARELOOP_SNS_TOPIC_ARN")
    if not topic:
        log.info("[family notification not sent: no SNS topic] %s: %s", subject, message)
        return False
    try:
        import boto3

        boto3.client("sns", region_name=os.getenv("AWS_REGION")).publish(
            TopicArn=topic, Subject=subject[:100], Message=message
        )
        return True
    except Exception as exc:
        log.warning("SNS publish failed: %s", exc)
        return False
