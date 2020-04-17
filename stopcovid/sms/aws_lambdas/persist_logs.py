import datetime
from stopcovid.utils.kinesis import get_payload_from_kinesis_record
from stopcovid.sms.message_log.message_log import log_messages
from stopcovid.sms.message_log.types import LogMessageCommandSchema

from stopcovid.utils.logging import configure_logging
from stopcovid.utils.verify_deploy_stage import verify_deploy_stage

configure_logging()


def handle(event, context):
    verify_deploy_stage()
    commands = []
    for record in event["Records"]:
        command = get_payload_from_kinesis_record(record)
        approximate_arrival = (
            datetime.datetime.fromtimestamp(record["kinesis"]["approximateArrivalTimestamp"])
            .replace(tzinfo=datetime.timezone.utc)
            .isoformat()
        )
        commands.append(
            LogMessageCommandSchema().load(
                {
                    "command_type": command["type"],
                    "payload": command["payload"],
                    "approximate_arrival": approximate_arrival,
                }
            )
        )
    log_messages(commands)
    return {"statusCode": 200}
