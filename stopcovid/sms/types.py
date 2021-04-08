from typing import List, Optional

import pydantic


class SMS(pydantic.BaseModel):
    body: Optional[str]
    media_url: Optional[str] = None


class SMSBatch(pydantic.BaseModel):
    phone_number: str
    messages: List[SMS]
    idempotency_key: str


class OutboundPayload(pydantic.BaseModel):
    MessageSid: str
    To: str
    Body: str
    MessageStatus: str
    MediaUrl: Optional[str] = None
