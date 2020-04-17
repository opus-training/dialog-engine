import logging
import unittest
import uuid
from unittest.mock import patch, MagicMock

from stopcovid.dialog.command_stream.publish import CommandPublisher
from stopcovid.drill_progress.drill_progress import DrillInstance


class TestCommandPublisher(unittest.TestCase):
    def setUp(self) -> None:
        logging.disable(logging.CRITICAL)
        kinesis_client = MagicMock()
        self.put_records_mock = MagicMock()
        kinesis_client.put_records = self.put_records_mock
        get_kinesis_client_patch = patch(
            "stopcovid.dialog.command_stream.publish.CommandPublisher._get_kinesis_client",
            return_value=kinesis_client,
        )
        get_kinesis_client_patch.start()
        self.addCleanup(get_kinesis_client_patch.stop)
        self.command_publisher = CommandPublisher()

    def test_publish_start_drill(self):
        self.command_publisher.publish_start_drill_command("123456789", "slug")
        self.put_records_mock.assert_called_once()
        self.assertEqual(1, len(self.put_records_mock.call_args[1]["Records"]))
        self.assertEqual(
            "123456789", self.put_records_mock.call_args[1]["Records"][0]["PartitionKey"]
        )

    def publish_process_sms(self):
        self.command_publisher.publish_process_sms_command("123456789", "lol", {"foo": "bar"})
        self.put_records_mock.assert_called_once()
        self.assertEqual(1, len(self.put_records_mock.call_args[1]["Records"]))
        self.assertEqual(
            "123456789", self.put_records_mock.call_args[1]["Records"][0]["PartitionKey"]
        )

    def publish_trigger_reminders(self):
        drill_instances = [
            DrillInstance(
                drill_instance_id=uuid.uuid4(),
                user_id=uuid.uuid4(),
                phone_number="123456789",
                drill_slug="slug",
            ),
            DrillInstance(
                drill_instance_id=uuid.uuid4(),
                user_id=uuid.uuid4(),
                phone_number="987654321",
                drill_slug="slug",
            ),
        ]
        self.command_publisher.publish_trigger_reminder_commands(drill_instances)
        self.put_records_mock.assert_called_once()
        self.assertEqual(2, len(self.put_records_mock.call_args[1]["Records"]))
        self.assertEqual(
            "123456789", self.put_records_mock.call_args[1]["Records"][0]["PartitionKey"]
        )
        self.assertEqual(
            "987654321", self.put_records_mock.call_args[1]["Records"][1]["PartitionKey"]
        )
