from dataclasses import dataclass
from typing import List, Optional
from marshmallow import Schema, fields, post_load


@dataclass
class SMS:
    body: Optional[str]
    media_url: Optional[str] = None


class SMSSchema(Schema):
    body = fields.Str(required=True, allow_none=True)
    media_url = fields.URL(allow_none=True)

    @post_load
    def make_sms(self, data, **kwargs):
        return SMS(**data)


@dataclass
class SMSBatch:
    phone_number: str
    messages: List[SMS]
    idempotency_key: str


class SMSBatchSchema(Schema):
    phone_number = fields.Str(required=True)
    messages = fields.List(fields.Nested(SMSSchema), required=True)
    idempotency_key = fields.Str(required=True)

    @post_load
    def make_batch_sms(self, data, **kwargs):
        return SMSBatch(**data)
