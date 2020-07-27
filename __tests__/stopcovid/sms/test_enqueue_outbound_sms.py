import json
import logging
import unittest
import uuid
from typing import List
from unittest.mock import patch, MagicMock

from stopcovid.sms.enqueue_outbound_sms import (
    get_messages,
    get_outbound_sms_commands,
    USER_VALIDATION_FAILED_COPY,
    publish_outbound_sms_messages,
    OutboundSMS,
)
from stopcovid.dialog.models.state import UserProfileSchema
from stopcovid.dialog.models.events import (
    DrillStarted,
    UserValidated,
    UserValidationFailed,
    CompletedPrompt,
    FailedPrompt,
    AdvancedToNextPrompt,
    DrillCompleted,
    DialogEvent,
    AdHocMessageSent,
)
from stopcovid.drills.drills import Drill, Prompt, PromptMessage
from stopcovid.dialog.registration import CodeValidationPayload
from stopcovid.sms.types import SMS


class TestHandleCommand(unittest.TestCase):
    def setUp(self):
        self.phone = "+15554238324"
        self.validated_user_profile = UserProfileSchema().load(
            {
                "validated": True,
                "language": "en",
                "name": "Mario",
                "is_demo": False,
                "account_info": {"employer_name": "Tacombi"},
            }
        )
        self.non_validated_user_profile = UserProfileSchema().load(
            {"validated": False, "language": "en", "name": "Luigi", "is_demo": False}
        )

        self.drill = Drill(
            name="Test Drill",
            slug="test-drill",
            prompts=[
                Prompt(slug="ignore-response-1", messages=[PromptMessage(text="Hello")]),
                Prompt(
                    slug="graded-response-1",
                    messages=[PromptMessage(text="Intro!"), PromptMessage(text="Question 1"),],
                    correct_response="a) Philadelphia",
                ),
                Prompt(
                    slug="graded-response-2",
                    messages=[PromptMessage(text="Question 2")],
                    correct_response="b",
                ),
            ],
        )

    def test_get_messages(self):
        dialog_event = CompletedPrompt(
            self.phone,
            user_profile=self.validated_user_profile,
            prompt=self.drill.prompts[1],
            response="a",
            drill_instance_id=uuid.uuid4(),
        )
        messages = [
            PromptMessage(text="Hello Mario"),
            PromptMessage(text="You work for Tacombi"),
        ]
        output = get_messages(dialog_event=dialog_event, messages=messages)
        self.assertEqual(output[0].body, "Hello Mario")
        self.assertEqual(output[1].body, "You work for Tacombi")

    def test_user_validation_failed_event(self):
        dialog_events: List[DialogEvent] = [
            UserValidationFailed(self.phone, self.non_validated_user_profile)
        ]
        outbound_messages = get_outbound_sms_commands(dialog_events)
        self.assertEqual(len(outbound_messages), 1)
        message = outbound_messages[0]
        self.assertEqual(message.phone_number, self.phone)
        self.assertEqual(message.event_id, dialog_events[0].event_id)
        self.assertEqual(message.body, USER_VALIDATION_FAILED_COPY)

    def test_user_validated_event(self):
        code_validation_payload = CodeValidationPayload(valid=True, is_demo=False)
        dialog_events: List[DialogEvent] = [
            UserValidated(self.phone, self.validated_user_profile, code_validation_payload)
        ]
        outbound_messages = get_outbound_sms_commands(dialog_events)
        self.assertEqual(len(outbound_messages), 0)

    def test_drill_completed_event(self):
        dialog_events: List[DialogEvent] = [
            DrillCompleted(self.phone, self.validated_user_profile, drill_instance_id=uuid.uuid4())
        ]
        outbound_messages = get_outbound_sms_commands(dialog_events)
        self.assertEqual(len(outbound_messages), 0)

    def test_drill_started_event(self):
        dialog_events: List[DialogEvent] = [
            DrillStarted(
                self.phone,
                self.validated_user_profile,
                drill=self.drill,
                first_prompt=self.drill.prompts[0],
            )
        ]
        outbound_messages = get_outbound_sms_commands(dialog_events)
        self.assertEqual(len(outbound_messages), 1)
        message = outbound_messages[0]
        self.assertEqual(message.phone_number, self.phone)
        self.assertEqual(message.event_id, dialog_events[0].event_id)
        self.assertEqual(message.body, "Hello")

    def test_completed_prompt_event(self):
        dialog_events: List[DialogEvent] = [
            CompletedPrompt(
                self.phone,
                self.validated_user_profile,
                prompt=self.drill.prompts[1],
                response="a",
                drill_instance_id=uuid.uuid4(),
            )
        ]
        outbound_messages = get_outbound_sms_commands(dialog_events)
        self.assertEqual(len(outbound_messages), 1)
        message = outbound_messages[0]
        self.assertEqual(message.phone_number, self.phone)
        self.assertEqual(message.event_id, dialog_events[0].event_id)
        self.assertEqual(message.body, "🤖 Correct!")

    def test_abandoned_failed_prompt_event(self):
        dialog_events: List[DialogEvent] = [
            FailedPrompt(
                self.phone,
                self.validated_user_profile,
                prompt=self.drill.prompts[1],
                response="a",
                drill_instance_id=uuid.uuid4(),
                abandoned=True,
            )
        ]
        outbound_messages = get_outbound_sms_commands(dialog_events)
        self.assertEqual(len(outbound_messages), 1)
        message = outbound_messages[0]
        self.assertEqual(message.phone_number, self.phone)
        self.assertEqual(message.event_id, dialog_events[0].event_id)
        self.assertEqual(
            message.body, "🤖 The correct answer is *a) Philadelphia*.\n\nLets move to the next one."
        )

    def test_non_abandoned_failed_prompt_event(self):
        dialog_events: List[DialogEvent] = [
            FailedPrompt(
                self.phone,
                self.validated_user_profile,
                prompt=self.drill.prompts[1],
                response="a",
                drill_instance_id=uuid.uuid4(),
                abandoned=False,
            )
        ]
        outbound_messages = get_outbound_sms_commands(dialog_events)
        self.assertEqual(len(outbound_messages), 1)
        message = outbound_messages[0]
        self.assertEqual(message.phone_number, self.phone)
        self.assertEqual(message.event_id, dialog_events[0].event_id)
        self.assertEqual(message.body, "🤖 Sorry, not correct. Try again one more time.")

    def test_advance_to_next_prompt_event(self):
        dialog_events: List[DialogEvent] = [
            AdvancedToNextPrompt(
                self.phone,
                self.validated_user_profile,
                prompt=self.drill.prompts[1],
                drill_instance_id=uuid.uuid4(),
            )
        ]
        outbound_messages = get_outbound_sms_commands(dialog_events)
        self.assertEqual(len(outbound_messages), 2)
        expected_messages = [message.text for message in self.drill.prompts[1].messages]

        self.assertEqual(outbound_messages[0].phone_number, self.phone)
        self.assertEqual(outbound_messages[0].event_id, dialog_events[0].event_id)
        self.assertEqual(outbound_messages[0].body, expected_messages[0])

        self.assertEqual(outbound_messages[1].phone_number, self.phone)
        self.assertEqual(outbound_messages[1].event_id, dialog_events[0].event_id)
        self.assertEqual(outbound_messages[1].body, expected_messages[1])

    def test_ad_hoc_message_sent(self):
        body = "we have lift off"
        dialog_events: List[DialogEvent] = [
            AdHocMessageSent(self.phone, self.validated_user_profile, sms=SMS(body=body))
        ]
        outbound_messages = get_outbound_sms_commands(dialog_events)
        self.assertEqual(len(outbound_messages), 1)
        self.assertEqual(outbound_messages[0].body, body)
        self.assertEqual(outbound_messages[0].media_url, None)


@patch("stopcovid.sms.enqueue_outbound_sms.boto3")
class TestPublishOutboundSMS(unittest.TestCase):
    def setUp(self) -> None:
        logging.disable(logging.CRITICAL)

    def _get_mocked_send_messages(self, boto_mock):
        sqs_mock = MagicMock()
        boto_mock.resource.return_value = sqs_mock
        queue = MagicMock(name="queue")
        send_messages_mock = MagicMock()
        queue.send_messages = send_messages_mock
        sqs_mock.get_queue_by_name = MagicMock(return_value=queue)
        return send_messages_mock

    def _get_send_message_entries(self, send_messages_mock):
        send_messages_mock.assert_called_once()
        call = send_messages_mock.mock_calls[0]
        _, *kwargs = call
        return kwargs[1]["Entries"]  # type: ignore

    def test_no_messages(self, boto_mock):
        send_messages_mock = self._get_mocked_send_messages(boto_mock)
        publish_outbound_sms_messages([])
        send_messages_mock.assert_not_called()

    def test_sends_messages_to_one_phone_number_for_one_event(self, boto_mock):
        send_messages_mock = self._get_mocked_send_messages(boto_mock)
        phone_number = "+15551234321"

        event_id = uuid.uuid4()
        messages = [
            OutboundSMS(event_id=event_id, phone_number=phone_number, body="message 1"),
            OutboundSMS(event_id=event_id, phone_number=phone_number, body="message 2"),
            OutboundSMS(event_id=event_id, phone_number=phone_number, body="message 3"),
        ]

        publish_outbound_sms_messages(messages)
        entries = self._get_send_message_entries(send_messages_mock)

        self.assertEqual(len(entries), 1)
        entry = entries[0]
        self.assertTrue(1 <= len(entry["MessageDeduplicationId"]) <= 128)
        sqs_message = json.loads(entry["MessageBody"])
        self.assertEqual(sqs_message["phone_number"], phone_number)
        self.assertEqual(
            sqs_message["messages"],
            [
                {"body": "message 1", "media_url": None},
                {"body": "message 2", "media_url": None},
                {"body": "message 3", "media_url": None},
            ],
        )
        self.assertEqual(entry["MessageGroupId"], phone_number)

    def test_sends_messages_to_one_phone_number_for_multiple_events(self, boto_mock):
        send_messages_mock = self._get_mocked_send_messages(boto_mock)
        phone_number = "+15551234321"

        event_1_id = uuid.uuid4()
        event_2_id = uuid.uuid4()
        messages = [
            OutboundSMS(event_id=event_1_id, phone_number=phone_number, body="message 1"),
            OutboundSMS(event_id=event_1_id, phone_number=phone_number, body="message 2"),
            OutboundSMS(event_id=event_2_id, phone_number=phone_number, body="message 3"),
        ]

        publish_outbound_sms_messages(messages)
        entries = self._get_send_message_entries(send_messages_mock)

        self.assertEqual(len(entries), 1)
        entry = entries[0]
        self.assertTrue(1 <= len(entry["MessageDeduplicationId"]) <= 128)
        sqs_message = json.loads(entry["MessageBody"])
        self.assertEqual(sqs_message["phone_number"], phone_number)
        self.assertEqual(
            sqs_message["messages"],
            [
                {"body": "message 1", "media_url": None},
                {"body": "message 2", "media_url": None},
                {"body": "message 3", "media_url": None},
            ],
        ),
        self.assertEqual(entry["MessageGroupId"], phone_number)

    def test_sends_messages_to_multiple_phone_numbers_for_one_event_each(self, boto_mock):
        send_messages_mock = self._get_mocked_send_messages(boto_mock)
        phone_number_1 = "+15551234321"
        phone_number_2 = "+15559998888"
        event_1_id = uuid.uuid4()
        event_2_id = uuid.uuid4()

        messages = [
            OutboundSMS(event_id=event_1_id, phone_number=phone_number_1, body="message 1"),
            OutboundSMS(event_id=event_1_id, phone_number=phone_number_1, body="message 2"),
            OutboundSMS(event_id=event_2_id, phone_number=phone_number_2, body="message 3"),
        ]

        publish_outbound_sms_messages(messages)
        entries = self._get_send_message_entries(send_messages_mock)

        self.assertEqual(len(entries), 2)

        # first entry
        entry = entries[0]
        self.assertTrue(1 <= len(entry["MessageDeduplicationId"]) <= 128)
        sqs_message = json.loads(entry["MessageBody"])
        self.assertEqual(sqs_message["phone_number"], phone_number_1)
        self.assertEqual(
            sqs_message["messages"],
            [{"body": "message 1", "media_url": None}, {"body": "message 2", "media_url": None},],
        )
        self.assertEqual(entry["MessageGroupId"], phone_number_1)

        # second entry
        entry = entries[1]
        self.assertTrue(1 <= len(entry["MessageDeduplicationId"]) <= 128)
        sqs_message = json.loads(entry["MessageBody"])
        self.assertEqual(sqs_message["phone_number"], phone_number_2)
        self.assertEqual(sqs_message["messages"], [{"body": "message 3", "media_url": None}])
        self.assertEqual(entry["MessageGroupId"], phone_number_2)

    def test_sends_messages_to_multiple_phone_numbers_for_multiple_events_each(self, boto_mock):
        send_messages_mock = self._get_mocked_send_messages(boto_mock)
        phone_number_1 = "+15551234321"
        phone_number_2 = "+15559998888"
        phone_number_3 = "+15551110000"

        phone_number_1_event_ids = [uuid.uuid4(), uuid.uuid4()]
        phone_number_2_event_ids = [uuid.uuid4(), uuid.uuid4()]
        phone_number_3_event_ids = [uuid.uuid4(), uuid.uuid4(), uuid.uuid4()]

        messages = [
            OutboundSMS(
                event_id=phone_number_1_event_ids[0], phone_number=phone_number_1, body="message 1",
            ),
            OutboundSMS(
                event_id=phone_number_1_event_ids[1], phone_number=phone_number_1, body="message 2",
            ),
            OutboundSMS(
                event_id=phone_number_2_event_ids[0], phone_number=phone_number_2, body="message 3",
            ),
            OutboundSMS(
                event_id=phone_number_2_event_ids[1], phone_number=phone_number_2, body="message 4",
            ),
            OutboundSMS(
                event_id=phone_number_3_event_ids[0], phone_number=phone_number_3, body="message 5",
            ),
            OutboundSMS(
                event_id=phone_number_3_event_ids[1], phone_number=phone_number_3, body="message 6",
            ),
            OutboundSMS(
                event_id=phone_number_3_event_ids[2], phone_number=phone_number_3, body="message 7",
            ),
        ]

        publish_outbound_sms_messages(messages)
        entries = self._get_send_message_entries(send_messages_mock)

        self.assertEqual(len(entries), 3)

        # first entry
        entry = entries[0]
        self.assertTrue(1 <= len(entry["MessageDeduplicationId"]) <= 128)
        sqs_message = json.loads(entry["MessageBody"])
        self.assertEqual(sqs_message["phone_number"], phone_number_1)
        self.assertEqual(
            sqs_message["messages"],
            [{"body": "message 1", "media_url": None}, {"body": "message 2", "media_url": None},],
        )
        self.assertEqual(entry["MessageGroupId"], phone_number_1)

        # second entry
        entry = entries[1]
        self.assertTrue(1 <= len(entry["MessageDeduplicationId"]) <= 128)
        sqs_message = json.loads(entry["MessageBody"])
        self.assertEqual(sqs_message["phone_number"], phone_number_2)
        self.assertEqual(
            sqs_message["messages"],
            [{"body": "message 3", "media_url": None}, {"body": "message 4", "media_url": None},],
        )
        self.assertEqual(entry["MessageGroupId"], phone_number_2)

        # third entry
        entry = entries[2]
        self.assertTrue(1 <= len(entry["MessageDeduplicationId"]) <= 128)
        sqs_message = json.loads(entry["MessageBody"])
        self.assertEqual(sqs_message["phone_number"], phone_number_3)
        self.assertEqual(
            sqs_message["messages"],
            [
                {"body": "message 5", "media_url": None},
                {"body": "message 6", "media_url": None},
                {"body": "message 7", "media_url": None},
            ],
        )
        self.assertEqual(entry["MessageGroupId"], phone_number_3)
