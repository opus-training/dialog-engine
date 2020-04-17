from stopcovid.utils.kinesis import get_payload_from_kinesis_record

from stopcovid.dialog.command_stream.types import InboundCommandSchema
from stopcovid.dialog.command_stream.command_stream import handle_inbound_commands
from stopcovid.utils.logging import configure_logging
from stopcovid.utils.verify_deploy_stage import verify_deploy_stage

configure_logging()


def _make_inbound_command(record):
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
    inbound_commands = [_make_inbound_command(record) for record in event["Records"]]
    handle_inbound_commands(inbound_commands)
    return {"statusCode": 200}
