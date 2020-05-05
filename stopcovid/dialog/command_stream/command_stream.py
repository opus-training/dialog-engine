from typing import List
import uuid

from stopcovid.dialog.engine import process_command, StartDrill, TriggerReminder, ProcessSMSMessage
from .types import InboundCommand, InboundCommandType


def handle_inbound_commands(commands: List[InboundCommand]):

    for command in commands:
        if command.command_type == InboundCommandType.INBOUND_SMS:
            process_command(
                ProcessSMSMessage(
                    phone_number=command.payload["From"], content=command.payload["Body"]
                ),
                command.sequence_number,
            )
        elif command.command_type == InboundCommandType.START_DRILL:
            process_command(
                StartDrill(
                    phone_number=command.payload["phone_number"],
                    drill_slug=command.payload["drill_slug"],
                    drill_body=command.payload["drill_body"],
                ),
                command.sequence_number,
            )
        elif command.command_type == InboundCommandType.TRIGGER_REMINDER:
            process_command(
                TriggerReminder(
                    phone_number=command.payload["phone_number"],
                    drill_instance_id=uuid.UUID(command.payload["drill_instance_id"]),
                    prompt_slug=command.payload["prompt_slug"],
                ),
                command.sequence_number,
            )
        else:
            raise RuntimeError(f"Unknown command: {command.command_type}")

    return {"statusCode": 200}
