import unittest
from unittest.mock import patch

from stopcovid.sms.message_log.types import LogMessageCommand, LogMessageCommandType
from stopcovid.sms.message_log.message_log import log_messages

from __tests__.utils.time import get_timestamp_min_in_past


@patch("stopcovid.sms.message_log.message_log.persistence")
class TestMessageLog(unittest.TestCase):
    def test_calls_persistence_with_transformed_commands(self, persistence_mock):
        commands = [
            LogMessageCommand(
                command_type=LogMessageCommandType.INBOUND_SMS,
                payload={
                    "MessageSid": "twi-1",
                    "MessageStatus": "sent",
                    "From": "+1444333222",
                    "Body": "hello?",
                    "To": "+10009998888",
                },
                approximate_arrival=get_timestamp_min_in_past(5),
            ),
            LogMessageCommand(
                command_type=LogMessageCommandType.STATUS_UPDATE,
                payload={
                    "MessageSid": "twi-1",
                    "MessageStatus": "delivered",
                    "From": "+1444333222",
                    "To": "+10009998888",
                },
                approximate_arrival=get_timestamp_min_in_past(3),
            ),
            LogMessageCommand(
                command_type=LogMessageCommandType.OUTBOUND_SMS,
                payload={
                    "MessageSid": "twi-2",
                    "MessageStatus": "sent",
                    "From": "+1444333222",
                    "Body": "are you there?",
                    "To": "+10009998888",
                },
                approximate_arrival=get_timestamp_min_in_past(1),
            ),
        ]
        log_messages(commands)

        # 1 to get repo, 1 to upsert messages
        self.assertEqual(len(persistence_mock.mock_calls), 2)

        upserts = [u for u in persistence_mock.mock_calls[1][1][0]]
        self.assertEqual(len(upserts), 3)

        self.assertEqual(upserts[0]["twilio_message_id"], commands[0].payload["MessageSid"])
        self.assertEqual(upserts[0]["from_number"], commands[0].payload["From"])
        self.assertEqual(upserts[0]["to_number"], commands[0].payload["To"])
        self.assertEqual(upserts[0]["status"], commands[0].payload["MessageStatus"])
        self.assertEqual(upserts[0]["body"], commands[0].payload["Body"])
        self.assertEqual(upserts[0]["created_at"], commands[0].approximate_arrival)

        self.assertEqual(len(upserts[1].keys()), 4)
        self.assertEqual(upserts[1]["twilio_message_id"], commands[0].payload["MessageSid"])
        self.assertEqual(upserts[1]["from_number"], commands[1].payload["From"])
        self.assertEqual(upserts[1]["to_number"], commands[1].payload["To"])
        self.assertEqual(upserts[1]["status"], commands[1].payload["MessageStatus"])

        self.assertEqual(upserts[2]["twilio_message_id"], commands[2].payload["MessageSid"])
        self.assertEqual(upserts[2]["from_number"], commands[2].payload["From"])
        self.assertEqual(upserts[2]["to_number"], commands[2].payload["To"])
        self.assertEqual(upserts[2]["status"], commands[2].payload["MessageStatus"])
        self.assertEqual(upserts[2]["body"], commands[2].payload["Body"])
        self.assertEqual(upserts[2]["created_at"], commands[2].approximate_arrival)
