import logging
import unittest
import uuid
from unittest.mock import patch, MagicMock

from stopcovid.drill_progress.initiation import DrillInitiator
from stopcovid.drill_progress.drill_progress import DrillProgress


@patch("stopcovid.dialog.command_stream.publish.CommandPublisher.publish_start_drill_command")
class TestInitiation(unittest.TestCase):
    def setUp(self):
        logging.disable(logging.CRITICAL)
        mock_checker = MagicMock()
        mock_checker.already_processed = MagicMock(return_value=False)
        idempotency_checker_patch = patch(
            "stopcovid.drill_progress.initiation.IdempotencyChecker", return_value=mock_checker
        )
        idempotency_checker_patch.start()
        self.addCleanup(idempotency_checker_patch.stop)

        self.initiator = DrillInitiator()
        self.first_drill_slug = "foo"
        get_all_drill_slugs_patch = patch(
            "stopcovid.drill_progress.initiation.get_first_drill_slug",
            return_value=self.first_drill_slug,
        )
        get_all_drill_slugs_patch.start()
        self.addCleanup(get_all_drill_slugs_patch.stop)

    def test_initiation_first_drill(self, publish_mock):
        # we aren't erasing our DB between test runs, so let's ensure the phone number is unique
        phone_number = str(uuid.uuid4())
        idempotency_key = str(uuid.uuid4())

        self.initiator.trigger_first_drill(phone_number, idempotency_key)
        publish_mock.assert_called_once_with(phone_number, self.first_drill_slug)

    def test_initiation_next_drill_for_user(self, publish_mock):
        phone_number = str(uuid.uuid4())
        user_id = uuid.uuid4()
        idempotency_key = str(uuid.uuid4())
        with patch(
            "stopcovid.drill_progress.initiation.DrillProgressRepository.get_progress_for_user",
            return_value=DrillProgress(
                phone_number=phone_number,
                user_id=user_id,
                first_incomplete_drill_slug="02-sample-drill",
                first_unstarted_drill_slug="03-sample-drill",
            ),
        ):
            self.initiator.trigger_next_drill_for_user(phone_number, idempotency_key)
            publish_mock.assert_called_once_with(phone_number, "03-sample-drill")
            publish_mock.reset_mock()

    def test_initiation_out_of_drills(self, publish_mock):
        phone_number = str(uuid.uuid4())
        user_id = uuid.uuid4()
        idempotency_key = str(uuid.uuid4())
        with patch(
            "stopcovid.drill_progress.initiation.DrillProgressRepository.get_progress_for_user",
            return_value=DrillProgress(
                phone_number=phone_number,
                user_id=user_id,
                first_incomplete_drill_slug=None,
                first_unstarted_drill_slug=None,
            ),
        ):
            self.initiator.trigger_next_drill_for_user(phone_number, idempotency_key)
            publish_mock.assert_not_called()

    def test_trigger_drill_if_not_stale(self, publish_mock):
        phone_number = str(uuid.uuid4())
        user_id = uuid.uuid4()

        with patch(
            "stopcovid.drill_progress.initiation.DrillProgressRepository.get_progress_for_user",
            return_value=DrillProgress(
                phone_number=phone_number,
                user_id=user_id,
                first_incomplete_drill_slug="02-sample-drill",
                first_unstarted_drill_slug="03-sample-drill",
            ),
        ):
            self.initiator.trigger_drill_if_not_stale(phone_number, "01-sample-drill", "foo")
            publish_mock.assert_not_called()
            self.initiator.trigger_drill_if_not_stale(
                phone_number, "03-sample-drill", str(uuid.uuid4())
            )
            publish_mock.assert_called_once_with(phone_number, "03-sample-drill")

    def test_trigger_drill(self, publish_mock):
        phone_number = str(uuid.uuid4())
        slug = "02-sample-drill"
        idempotency_key = str(uuid.uuid4())
        self.initiator.trigger_drill(phone_number, slug, idempotency_key)
        publish_mock.assert_called_once_with(phone_number, slug)

    def test_trigger_drill_none(self, publish_mock):
        phone_number = str(uuid.uuid4())
        idempotency_key = str(uuid.uuid4())
        self.initiator.trigger_drill(phone_number, None, idempotency_key)
        publish_mock.assert_not_called()
