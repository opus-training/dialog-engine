import unittest
import uuid
from unittest.mock import patch
import datetime
import os

from stopcovid import db
from stopcovid.dialog.models.events import DialogEventBatch, UserValidated
from stopcovid.dialog.models.state import UserProfile
from stopcovid.dialog.registration import CodeValidationPayload
from stopcovid.drill_progress.trigger_reminders import ReminderTriggerer, IDEMPOTENCY_REALM
from stopcovid.drill_progress.drill_progress import DrillProgressRepository
from stopcovid.utils.idempotency import IdempotencyChecker
from __tests__.utils.factories import make_drill_instance


@patch("stopcovid.dialog.command_stream.publish.CommandPublisher.publish_trigger_reminder_commands")
class TestReminderTriggers(unittest.TestCase):
    def setUp(self):
        os.environ["STAGE"] = "test"
        self.drill_progress_repo = DrillProgressRepository(db.get_test_sqlalchemy_engine)
        self.drill_progress_repo.drop_and_recreate_tables_testing_only()
        self.phone_number = "123456789"
        self.user_id = self.drill_progress_repo._create_or_update_user(
            DialogEventBatch(
                events=[
                    UserValidated(self.phone_number, UserProfile(True), CodeValidationPayload(True))
                ],
                phone_number=self.phone_number,
                seq="0",
                batch_id=uuid.uuid4(),
            ),
            None,
            self.drill_progress_repo.engine,
        )

        drill_db_patch = patch(
            "stopcovid.drill_progress.trigger_reminders.ReminderTriggerer._get_drill_progress_repo",
            return_value=self.drill_progress_repo,
        )
        drill_db_patch.start()

        self.addCleanup(drill_db_patch.stop)

        self.idempotency_checker = IdempotencyChecker(
            region_name="us-west-2",
            endpoint_url="http://localhost:9000",
            aws_access_key_id="fake-key",
            aws_secret_access_key="fake-secret",
        )
        self.idempotency_checker.drop_and_recreate_table()

        idempotency_patch = patch(
            "stopcovid.drill_progress.trigger_reminders.IdempotencyChecker",
            return_value=self.idempotency_checker,
        )
        idempotency_patch.start()
        self.addCleanup(idempotency_patch.stop)

    def _get_incomplete_drill_with_last_prompt_started_min_ago(self, min_ago):
        return make_drill_instance(
            current_prompt_start_time=datetime.datetime.now(datetime.timezone.utc)
            - datetime.timedelta(minutes=min_ago),
            completion_time=None,
            user_id=self.user_id,
        )

    def test_reminder_triggerer_ignores_drills_below_inactivity_threshold(self, publish_mock):
        drill_instance = self._get_incomplete_drill_with_last_prompt_started_min_ago(10)
        self.drill_progress_repo._save_drill_instance(drill_instance)
        ReminderTriggerer().trigger_reminders()
        publish_mock.assert_not_called()

    def test_reminder_triggerer_ignores_drills_above_inactivity_threshold(self, publish_mock):
        two_day_old_drill_instance = self._get_incomplete_drill_with_last_prompt_started_min_ago(
            60 * 24 * 2
        )
        self.drill_progress_repo._save_drill_instance(two_day_old_drill_instance)
        ReminderTriggerer().trigger_reminders()
        publish_mock.assert_not_called()

    def test_reminder_triggerer_triggers_reminder_and_persists_idempotency_key(self, publish_mock):
        drill_instance = self._get_incomplete_drill_with_last_prompt_started_min_ago(5 * 60)
        self.drill_progress_repo._save_drill_instance(drill_instance)
        expected_idempotency_key = (
            f"{drill_instance.drill_instance_id}-{drill_instance.current_prompt_slug}"
        )
        self.assertFalse(
            self.idempotency_checker.already_processed(expected_idempotency_key, IDEMPOTENCY_REALM)
        )
        ReminderTriggerer().trigger_reminders()
        publish_mock.assert_called_once_with([drill_instance])
        self.assertTrue(
            self.idempotency_checker.already_processed(expected_idempotency_key, IDEMPOTENCY_REALM)
        )

    def test_does_not_double_trigger_reminders(self, publish_mock):
        drill_instance = self._get_incomplete_drill_with_last_prompt_started_min_ago(5 * 60)
        self.drill_progress_repo._save_drill_instance(drill_instance)
        ReminderTriggerer().trigger_reminders()
        publish_mock.assert_called_once_with([drill_instance])
        publish_mock.reset_mock()
        ReminderTriggerer().trigger_reminders()
        publish_mock.assert_not_called()
