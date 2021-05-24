from typing import Optional

from twilio.rest import Client
import os
import logging
from twilio.rest.api.v2010.account.message import MessageInstance

from ..utils.phones import is_fake_phone_number


def send_message(
    to: str, body: Optional[str], media_url: Optional[str]
) -> Optional[MessageInstance]:
    if is_fake_phone_number(to):
        logging.info(f"({to}) Abandoning message to fake phone number")
        return None

    client = Client(os.environ["TWILIO_ACCOUNT_SID"], os.environ["TWILIO_AUTH_TOKEN"])
    if body is None:
        emoji_escaped_body = None
    else:
        emoji_escaped_body = body.encode("utf-16", "surrogatepass").decode("utf-16")
    return client.messages.create(
        to=to,
        body=emoji_escaped_body,
        media_url=media_url,
        messaging_service_sid=os.environ["TWILIO_MESSAGING_SERVICE_SID"],
    )
