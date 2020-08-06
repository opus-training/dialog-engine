from enum import Enum

import pydantic


class InboundCommandType(Enum):
    INBOUND_SMS = "INBOUND_SMS"
    START_DRILL = "START_DRILL"
    SEND_AD_HOC_MESSAGE = "SEND_AD_HOC_MESSAGE"


class InboundCommand(pydantic.BaseModel):
    command_type: InboundCommandType
    sequence_number: str
    payload: dict
