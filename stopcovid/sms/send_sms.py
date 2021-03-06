from time import sleep
import logging
import json


from typing import List, Any, Optional

from twilio.rest.api.v2010.account.message import MessageInstance

from . import twilio
from stopcovid.sms.types import SMSBatch, OutboundPayload

from . import publish
from ..utils.idempotency import IdempotencyChecker

DELAY_SECONDS_BETWEEN_MESSAGES = 3
DELAY_SECONDS_AFTER_MEDIA = 10

IDEMPOTENCY_REALM = "send-sms"
IDEMPOTENCY_EXPIRATION_MINUTES = 24 * 60  # one day


def _publish_send(twilio_response: Any, media_url: Optional[str] = None) -> None:
    try:
        publish.publish_outbound_sms(
            OutboundPayload(
                MessageSid=twilio_response.sid,
                To=twilio_response.to,
                Body=twilio_response.body,
                MessageStatus=twilio_response.status,
                MediaUrl=media_url,
            )
        )
    except Exception:
        twilio_dict = {
            "twilio_message_id": twilio_response.sid,
            "to": twilio_response.to,
            "body": twilio_response.body,
            "status": twilio_response.status,
            "error_code": twilio_response.error_code,
            "error_message": twilio_response.error_message,
        }
        logging.info(f"Failed to publish to kinesis log: {json.dumps(twilio_dict)}")


def _send_batch(batch: SMSBatch) -> Optional[List[MessageInstance]]:
    idempotency_checker = IdempotencyChecker()
    if idempotency_checker.already_processed(batch.idempotency_key, IDEMPOTENCY_REALM):
        logging.info(f"SMS Batch already processed. Skipping. {batch}")
        return None
    twilio_responses = []
    for i, message in enumerate(batch.messages):
        if (message.body is None) and (message.media_url is None):
            logging.info(f"Skipped messages to {batch.phone_number}; no body or media_url")
            continue
        res = twilio.send_message(batch.phone_number, message.body, message.media_url)
        _publish_send(res, message.media_url)
        twilio_responses.append(res)

        # sleep after every message besides the last one
        if i < len(batch.messages) - 1:
            if message.media_url:
                sleep(DELAY_SECONDS_AFTER_MEDIA)
            else:
                sleep(DELAY_SECONDS_BETWEEN_MESSAGES)

    idempotency_checker.record_as_processed(
        batch.idempotency_key, IDEMPOTENCY_REALM, IDEMPOTENCY_EXPIRATION_MINUTES
    )
    return twilio_responses


def send_sms_batches(batches: List[SMSBatch]) -> None:
    for batch in batches:
        _send_batch(batch)
