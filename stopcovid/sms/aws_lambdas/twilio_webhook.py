import json
import logging
import os
from typing import Any, Dict
from urllib.parse import unquote_plus

import boto3
import rollbar
from twilio.request_validator import RequestValidator
from twilio.twiml.messaging_response import MessagingResponse

from stopcovid.dialog.command_stream.publish import CommandPublisher
from stopcovid.utils.idempotency import IdempotencyChecker

from stopcovid.utils.logging import configure_logging
from stopcovid.utils.rollbar import configure_rollbar
from stopcovid.utils.verify_deploy_stage import verify_deploy_stage

configure_logging()
configure_rollbar()

IDEMPOTENCY_REALM = "twilio-webhook"
IDEMPOTENCY_EXPIRATION_MINUTES = 60


@rollbar.lambda_function
def handler(event, context):
    verify_deploy_stage()
    kinesis = boto3.client("kinesis")
    stage = os.environ["STAGE"]
    idempotency_checker = IdempotencyChecker()

    form = extract_form(event)
    if not is_signature_valid(event, form, stage):
        logging.warning("signature validation failed")
        return {"statusCode": 403}

    idempotency_key = event["headers"]["I-Twilio-Idempotency-Token"]
    if idempotency_checker.already_processed(idempotency_key, IDEMPOTENCY_REALM):
        logging.info(
            f"Already processed webhook with idempotency key {idempotency_key}. Skipping."
        )
        return {"statusCode": 200}
    if "MessageStatus" in form:
        logging.info(
            f"Outbound message to {form['To']}: Recording STATUS_UPDATE in message log"
        )
        kinesis.put_record(
            Data=json.dumps({"type": "STATUS_UPDATE", "payload": form}),
            PartitionKey=form["To"],
            StreamName=f"message-log-{stage}",
        )
    else:
        logging.info(f"Inbound message from {form['From']}: '{form['Body']}'")
        CommandPublisher().publish_process_sms_command(form["From"], form["Body"], form)

    idempotency_checker.record_as_processed(
        idempotency_key, IDEMPOTENCY_REALM, IDEMPOTENCY_EXPIRATION_MINUTES
    )
    return {
        "statusCode": 200,
        "headers": {"content-type": "application/xml"},
        "body": str(MessagingResponse()),
    }


def extract_form(event):
    # We're getting an x-www-form-url-encoded string and we need to translate it into a dict.
    # We aren't using urllib.parse.parse_qs because it gives a slightly different answer, resulting
    # in failed signature validation.

    return {
        split_pair[0]: unquote_plus(split_pair[1])
        for split_pair in [kvpair.split("=") for kvpair in event["body"].split("&")]
    }


def is_signature_valid(event: Dict[str, Any], form: Dict[str, Any], stage: str) -> bool:
    validator = RequestValidator(os.environ["TWILIO_AUTH_TOKEN"])
    url = f"https://{event['headers']['Host']}/{stage}{event['path']}"
    signature = event["headers"].get("X-Twilio-Signature")
    return validator.validate(url, form, signature)
