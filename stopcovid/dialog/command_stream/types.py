from dataclasses import dataclass
from marshmallow import Schema, fields, post_load


class InboundCommandType:
    INBOUND_SMS = "INBOUND_SMS"
    START_DRILL = "START_DRILL"
    TRIGGER_REMINDER = "TRIGGER_REMINDER"
    SEND_AD_HOC_MESSAGE = "SEND_AD_HOC_MESSAGE"


@dataclass
class InboundCommand:
    command_type: str
    sequence_number: str
    payload: dict


class InboundCommandSchema(Schema):
    command_type = fields.Str(required=True)
    sequence_number = fields.Str(required=True)
    payload = fields.Dict(required=True)

    @post_load
    def make_sms(self, data, **kwargs):
        return InboundCommand(**data)
