import json
import logging
import os

import boto3

from stopcovid.utils.idempotency import IdempotencyChecker
from stopcovid.utils.kinesis import get_payload_from_kinesis_record

from stopcovid.dialog.command_stream.types import (
    InboundCommandSchema,
    InboundCommandType,
    InboundCommand,
)
from stopcovid.utils.logging import configure_logging
from stopcovid.utils.verify_deploy_stage import verify_deploy_stage

configure_logging()

IDEMPOTENCY_REALM = "inbound-sms"
IDEMPOTENCY_EXPIRATION_MINUTES = 60


def _make_inbound_command(record) -> InboundCommand:
    event = get_payload_from_kinesis_record(record)
    return InboundCommandSchema().load(
        {
            "payload": event["payload"],
            "command_type": event["type"],
            "sequence_number": record["kinesis"]["sequenceNumber"],
        }
    )


def handler(event, context):
    verify_deploy_stage()
    kinesis = boto3.client("kinesis")
    stage = os.environ["STAGE"]
    idempotency_checker = IdempotencyChecker()

    inbound_commands = [_make_inbound_command(record) for record in event["Records"]]
    for command in inbound_commands:
        if command.command_type == InboundCommandType.INBOUND_SMS:
            if not idempotency_checker.already_processed(
                command.sequence_number, IDEMPOTENCY_REALM
            ):
                logging.info(f"Logging an INBOUND_SMS message in the message log")
                twilio_webhook = command.payload["twilio_webhook"]
                kinesis.put_record(
                    Data=json.dumps({"type": "INBOUND_SMS", "payload": twilio_webhook}),
                    PartitionKey=command.payload["From"],
                    StreamName=f"message-log-{stage}",
                )
                idempotency_checker.record_as_processed(
                    command.sequence_number, IDEMPOTENCY_REALM, IDEMPOTENCY_EXPIRATION_MINUTES
                )

    return {"statusCode": 200}
