import json
import os

import boto3
import rollbar

from stopcovid.utils.idempotency import IdempotencyChecker
from stopcovid.utils.kinesis import get_payload_from_kinesis_record
from stopcovid.utils.rollbar import configure_rollbar

from stopcovid.dialog.command_stream.types import (
    InboundCommandType,
    InboundCommand,
)
from stopcovid.utils.logging import configure_logging
from stopcovid.utils.verify_deploy_stage import verify_deploy_stage

configure_logging()
configure_rollbar()

IDEMPOTENCY_REALM = "inbound-sms"
IDEMPOTENCY_EXPIRATION_MINUTES = 60


def _make_inbound_command(record: dict) -> InboundCommand:
    event = get_payload_from_kinesis_record(record)
    return InboundCommand(
        payload=event["payload"],
        command_type=event["type"],
        sequence_number=record["kinesis"]["sequenceNumber"],
    )


@rollbar.lambda_function  # type: ignore
def handler(event: dict, context: dict) -> dict:
    verify_deploy_stage()
    kinesis = boto3.client("kinesis")
    stage = os.environ["STAGE"]
    idempotency_checker = IdempotencyChecker()

    inbound_commands = [_make_inbound_command(record) for record in event["Records"]]
    for command in inbound_commands:
        if command.command_type is InboundCommandType.INBOUND_SMS:
            if not idempotency_checker.already_processed(
                command.sequence_number, IDEMPOTENCY_REALM
            ):
                twilio_webhook = command.payload["twilio_webhook"]
                kinesis.put_record(
                    Data=json.dumps({"type": "INBOUND_SMS", "payload": twilio_webhook}),
                    PartitionKey=command.payload["From"],
                    StreamName=f"message-log-{stage}",
                )
                idempotency_checker.record_as_processed(
                    command.sequence_number,
                    IDEMPOTENCY_REALM,
                    IDEMPOTENCY_EXPIRATION_MINUTES,
                )

    return {"statusCode": 200}
