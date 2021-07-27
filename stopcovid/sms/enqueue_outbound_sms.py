import hashlib
import json
import logging
import os
from collections import defaultdict
from typing import List, Optional, Any
from dataclasses import dataclass
import uuid

import boto3

from stopcovid.dialog.models.events import (
    DrillStarted,
    UserValidated,
    UserValidationFailed,
    CompletedPrompt,
    FailedPrompt,
    AdvancedToNextPrompt,
    DrillCompleted,
    OptedOut,
    NextDrillRequested,
    SchedulingDrillRequested,
    DialogEvent,
    DrillRequested,
    EnglishLessonDrillRequested,
    AdHocMessageSent,
)
from stopcovid.drills.drills import PromptMessage
from stopcovid.drills.content_loader import translate, SupportedTranslation, correct_answer_response

USER_VALIDATION_FAILED_COPY = (
    "Invalid Code. Check with your administrator and make sure you have the right code."
)


@dataclass
class OutboundSMS:
    event_id: uuid.UUID
    phone_number: str
    body: Optional[str]
    media_url: Optional[str] = None


def get_messages(
    dialog_event: DialogEvent,
    messages: List[PromptMessage],
) -> List[OutboundSMS]:

    return [
        OutboundSMS(
            event_id=dialog_event.event_id,
            phone_number=dialog_event.phone_number,
            body=message.text or None,
            media_url=message.media_url,
        )
        for i, message in enumerate(messages)
    ]


def get_messages_for_event(event: DialogEvent) -> List[OutboundSMS]:  # noqa: C901
    language = event.user_profile.language

    if isinstance(event, AdvancedToNextPrompt):
        return get_messages(event, event.prompt.messages)

    elif isinstance(event, FailedPrompt):
        if not event.abandoned:
            return get_messages(
                event,
                [PromptMessage(text=translate(language, SupportedTranslation.INCORRECT_ANSWER))],
            )
        elif event.prompt.correct_response:
            return get_messages(
                event,
                [
                    PromptMessage(
                        text=translate(
                            language,
                            SupportedTranslation.CORRECTED_ANSWER,
                            correct_answer=event.prompt.correct_response,
                        )
                    )
                ],
            )

    elif isinstance(event, CompletedPrompt):
        if event.prompt.correct_response is not None:
            return get_messages(
                event,
                [PromptMessage(text=correct_answer_response(language))],
            )

    elif isinstance(event, UserValidated):
        # User validated events will cause the scheduler to kick off a drill
        pass

    elif isinstance(event, UserValidationFailed):
        return get_messages(event, [PromptMessage(text=USER_VALIDATION_FAILED_COPY)])

    elif isinstance(event, DrillStarted):
        return get_messages(event, event.first_prompt.messages)

    elif isinstance(event, AdHocMessageSent):
        return get_messages(
            event, [PromptMessage(text=event.sms.body, media_url=event.sms.media_url)]
        )

    elif isinstance(
        event,
        (
            DrillCompleted,
            OptedOut,
            NextDrillRequested,
            SchedulingDrillRequested,
            EnglishLessonDrillRequested,
            DrillRequested,
        ),
    ):
        pass

    else:
        logging.info(f"Unknown event type: {event.event_type}")

    return []


def get_outbound_sms_commands(dialog_events: List[DialogEvent]) -> List[OutboundSMS]:
    outbound_messages = []

    for event in dialog_events:
        outbound_messages.extend(get_messages_for_event(event))

    return outbound_messages


def enqueue_outbound_sms_commands(dialog_events: List[DialogEvent]) -> None:
    outbound_messages = get_outbound_sms_commands(dialog_events)
    publish_outbound_sms_messages(outbound_messages)


def publish_outbound_sms_messages(outbound_sms_messages: List[OutboundSMS]) -> Any:
    if not outbound_sms_messages:
        return None

    sqs = boto3.resource("sqs", endpoint_url=f'http://{os.environ.get("LOCALSTACK_HOSTNAME")}:4566')

    queue_name = f"outbound-sms-{os.getenv('STAGE')}.fifo"
    queue = sqs.get_queue_by_name(QueueName=queue_name)

    phone_number_to_messages = defaultdict(list)
    for message in outbound_sms_messages:
        phone_number_to_messages[message.phone_number].append(message)

    entries = []
    for phone, messages in phone_number_to_messages.items():
        logging.info(f"({phone}) queuing {len(messages)} messages")
        deduplication_id = _get_message_deduplication_id(messages)
        entries.append(
            {
                "Id": str(uuid.uuid4()),
                "MessageBody": json.dumps(
                    {
                        "phone_number": phone,
                        "messages": [
                            {"body": message.body, "media_url": message.media_url}
                            for message in messages
                        ],
                        "idempotency_key": f"{phone}-{deduplication_id}",
                    }
                ),
                "MessageDeduplicationId": deduplication_id,
                "MessageGroupId": phone,
            }
        )

    return queue.send_messages(Entries=entries)


def _get_message_deduplication_id(messages: List[OutboundSMS]) -> str:
    unique_message_ids = sorted(list(set([str(message.event_id) for message in messages])))
    combined = "-".join(unique_message_ids)
    m = hashlib.shake_256()
    m.update(combined.encode("utf-8"))
    return m.hexdigest(64)  # the length of a hex digest will be up to 64 * 2 or 128
