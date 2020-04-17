from datetime import datetime
from dataclasses import dataclass
from marshmallow import Schema, fields, post_load


class LogMessageCommandType:
    INBOUND_SMS = "INBOUND_SMS"
    STATUS_UPDATE = "STATUS_UPDATE"
    OUTBOUND_SMS = "OUTBOUND_SMS"


@dataclass
class LogMessageCommand:
    command_type: str
    payload: dict
    approximate_arrival: datetime


class LogMessageCommandSchema(Schema):
    command_type = fields.Str(required=True)
    payload = fields.Dict(required=True)
    approximate_arrival = fields.DateTime(required=True)

    @post_load
    def make_sms(self, data, **kwargs):
        return LogMessageCommand(**data)
