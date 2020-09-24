import rollbar

from stopcovid.utils.kinesis import get_payload_from_kinesis_record
from stopcovid.dialog.command_stream.types import InboundCommand
from stopcovid.dialog.command_stream.command_stream import handle_inbound_commands
from stopcovid.utils.logging import configure_logging
from stopcovid.utils.rollbar import configure_rollbar
from stopcovid.utils.verify_deploy_stage import verify_deploy_stage

configure_logging()
configure_rollbar()


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
    inbound_commands = [_make_inbound_command(record) for record in event["Records"]]
    handle_inbound_commands(inbound_commands)
    return {"statusCode": 200}
