from typing import Optional
import pydantic

from twilio.rest import Client
import os


class TwilioResponse(pydantic.BaseModel):
    sid: str
    to: str
    body: Optional[str]
    status: str
    error_code: Optional[str]
    error_message: Optional[str]


def send_message(
    to: str, body: Optional[str], media_url: Optional[str], messaging_service_sid: Optional[str]
) -> TwilioResponse:
    client = Client(os.environ["TWILIO_ACCOUNT_SID"], os.environ["TWILIO_AUTH_TOKEN"])
    if body is None:
        emoji_escaped_body = None
    else:
        emoji_escaped_body = body.encode("utf-16", "surrogatepass").decode("utf-16")
    message = client.messages.create(
        to=to,
        body=emoji_escaped_body,
        media_url=media_url,
        messaging_service_sid=_get_messaging_service_sid(to, messaging_service_sid),
    )
    return TwilioResponse(
        sid=message.sid,
        to=message.to,
        body=message.body,
        status=message.status,
        error_code=message.error_code,
        error_message=message.error_message,
    )


def _get_messaging_service_sid(to: str, messaging_service_sid: Optional[str]) -> Optional[str]:
    if messaging_service_sid is None or to.startswith("whatsapp"):
        return os.environ["TWILIO_MESSAGING_SERVICE_SID"]
    return messaging_service_sid
