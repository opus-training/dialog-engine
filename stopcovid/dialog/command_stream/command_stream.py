from typing import List

from stopcovid.dialog.engine import (
    process_command,
    StartDrill,
    ProcessSMSMessage,
    SendAdHocMessage,
)
from .types import InboundCommand, InboundCommandType


def handle_inbound_commands(commands: List[InboundCommand]) -> dict:

    for command in commands:
        if command.command_type is InboundCommandType.INBOUND_SMS:
            process_command(
                ProcessSMSMessage(
                    phone_number=command.payload["From"],
                    content=command.payload["Body"],
                ),
                command.sequence_number,
            )
        elif command.command_type is InboundCommandType.START_DRILL:
            process_command(
                StartDrill(
                    phone_number=command.payload["phone_number"],
                    drill_slug=command.payload["drill_slug"],
                    drill_body=command.payload["drill_body"],
                ),
                command.sequence_number,
            )
        elif command.command_type is InboundCommandType.SEND_AD_HOC_MESSAGE:
            process_command(
                SendAdHocMessage(
                    phone_number=command.payload["phone_number"],
                    message=command.payload["message"],
                    media_url=command.payload["media_url"],
                ),
                command.sequence_number,
            )
        else:
            raise RuntimeError(f"Unknown command: {command.command_type}")

    return {"statusCode": 200}
