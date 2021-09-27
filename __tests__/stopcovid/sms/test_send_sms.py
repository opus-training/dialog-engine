import unittest
from unittest.mock import patch, MagicMock

from stopcovid.sms.types import SMSBatch, SMS
from stopcovid.sms.send_sms import send_sms_batches, DELAY_SECONDS_AFTER_MEDIA


@patch("stopcovid.sms.send_sms._publish_send")
@patch("stopcovid.sms.send_sms.twilio")
@patch("stopcovid.sms.send_sms.sleep")
class TestSendSMS(unittest.TestCase):
    def setUp(self) -> None:
        idempotency_checker = MagicMock()
        idempotency_checker.already_processed = MagicMock(return_value=False)
        idempotency_checker_patch = patch(
            "stopcovid.sms.send_sms.IdempotencyChecker",
            return_value=idempotency_checker,
        )
        idempotency_checker_patch.start()
        self.addCleanup(idempotency_checker_patch.stop)

    def _get_twilio_call_args(self, twilio_mock):
        return [call[1] for call in twilio_mock.send_message.mock_calls]

    def test_calls_twilio_for_one_batch(self, sleep_mock, twilio_mock, *args):
        phone = "+14801234321"
        batches = [
            SMSBatch(
                phone_number=phone,
                messages=[
                    SMS(body="hello"),
                    SMS(body="how are you"),
                    SMS(body="goodbye"),
                ],
                idempotency_key="foo",
            )
        ]
        send_sms_batches(batches)
        self.assertEqual(twilio_mock.send_message.call_count, 3)

        call_args = self._get_twilio_call_args(twilio_mock)
        for i, args in enumerate(call_args):
            self.assertEqual(args[0], phone)
            self.assertEqual(args[1], batches[0].messages[i].body)

    def test_uses_messaging_service_sid(self, sleep_mock, twilio_mock, *args):
        phone = "+14801234321"
        batches = [
            SMSBatch(
                phone_number=phone,
                messages=[
                    SMS(body="hello"),
                    SMS(body="how are you"),
                    SMS(body="goodbye"),
                ],
                idempotency_key="foo",
                messaging_service_sid="foo-bar-baz",
            )
        ]
        send_sms_batches(batches)
        self.assertEqual(twilio_mock.send_message.call_count, 3)

        call_args = self._get_twilio_call_args(twilio_mock)
        for i, args in enumerate(call_args):
            self.assertEqual(args[0], phone)
            self.assertEqual(args[1], batches[0].messages[i].body)
            self.assertEqual(args[3], "foo-bar-baz")

    def test_doesnt_send_to_fake_phones(self, sleep_mock, twilio_mock, *args):
        phone = "+15559990000"
        batches = [
            SMSBatch(
                phone_number=phone,
                messages=[
                    SMS(body="hello"),
                    SMS(body="how are you"),
                    SMS(body="goodbye"),
                ],
                idempotency_key="foo",
            )
        ]
        send_sms_batches(batches)
        self.assertEqual(twilio_mock.send_message.call_count, 0)

    def test_calls_twilio_for_multiple_batches(self, sleep_mock, twilio_mock, *args):
        phone_1 = "+14801234321"
        phone_2 = "+14801234321"
        batches = [
            SMSBatch(
                phone_number=phone_1,
                messages=[
                    SMS(body="hello"),
                    SMS(body="how are you"),
                    SMS(body="goodbye"),
                ],
                idempotency_key="foo",
            ),
            SMSBatch(
                phone_number=phone_2,
                messages=[SMS(body="another"), SMS(body="batch")],
                idempotency_key="foo",
            ),
        ]
        send_sms_batches(batches)
        self.assertEqual(twilio_mock.send_message.call_count, 5)

        call_args = self._get_twilio_call_args(twilio_mock)
        for i, args in enumerate(call_args[:3]):
            self.assertEqual(args[0], phone_1)
            self.assertEqual(args[1], batches[0].messages[i].body)

        for i, args in enumerate(call_args[3:]):
            self.assertEqual(args[0], phone_2)
            self.assertEqual(args[1], batches[1].messages[i].body)

    def test_sleep_between_set_messages(self, sleep_mock, twilio_mock, *args):
        batches = [
            SMSBatch(
                phone_number="+14801234321",
                messages=[
                    SMS(body="hello"),
                    SMS(body="how are you"),
                    SMS(body="goodbye"),
                ],
                idempotency_key="foo",
            )
        ]
        send_sms_batches(batches)
        self.assertEqual(sleep_mock.call_count, 2)

    def test_sleeps_longer_after_media_url(self, sleep_mock, twilio_mock, *args):
        batches = [
            SMSBatch(
                phone_number="+14801234321",
                messages=[
                    SMS(body="hello", media_url="www.cat.gif"),
                    SMS(body="how are you"),
                ],
                idempotency_key="foo",
            )
        ]
        send_sms_batches(batches)
        sleep_mock.assert_called_once_with(DELAY_SECONDS_AFTER_MEDIA)

    def test_do_not_sleep_on_single_message(self, sleep_mock, twilio_mock, *args):
        batches = [
            SMSBatch(
                phone_number="+14801234321",
                messages=[SMS(body="hello")],
                idempotency_key="foo",
            )
        ]
        send_sms_batches(batches)
        self.assertEqual(sleep_mock.call_count, 0)
