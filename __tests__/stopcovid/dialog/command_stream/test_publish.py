import logging
import unittest
from unittest.mock import patch, MagicMock

from stopcovid.dialog.command_stream.publish import CommandPublisher


class TestCommandPublisher(unittest.TestCase):
    def setUp(self) -> None:
        logging.disable(logging.CRITICAL)
        self.kinesis_client = MagicMock()
        self.put_records_mock = MagicMock()
        self.kinesis_client.put_records = self.put_records_mock
        get_kinesis_client_patch = patch(
            "stopcovid.dialog.command_stream.publish.CommandPublisher._get_kinesis_client",
            return_value=self.kinesis_client,
        )
        get_kinesis_client_patch.start()
        self.addCleanup(get_kinesis_client_patch.stop)
        self.command_publisher = CommandPublisher()

    def test_publish_process_sms(self):
        self.command_publisher.publish_process_sms_command(
            "123456789", "lol", {"foo": "bar"}
        )
        self.put_records_mock.assert_called_once()
        self.assertEqual(1, len(self.put_records_mock.call_args[1]["Records"]))
        self.assertEqual(
            "123456789",
            self.put_records_mock.call_args[1]["Records"][0]["PartitionKey"],
        )

    @patch("stopcovid.dialog.command_stream.publish.rollbar")
    def test_put_records_error(self, rollbar_mock):
        kinesis_response = {"FailedRecordCount": 3, "foo": "bar"}
        put_records_mock = MagicMock(return_value=kinesis_response)
        self.kinesis_client.put_records = put_records_mock
        self.command_publisher.publish_process_sms_command(
            "123456789", "lol", {"foo": "bar"}
        )
        put_records_mock.assert_called_once()
        rollbar_mock.report_exc_info.assert_called_once_with(
            extra_data=kinesis_response
        )
