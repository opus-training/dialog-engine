import logging
import unittest
import datetime
import uuid

from stopcovid.dialog.models.events import (
    DrillStarted,
    UserValidated,
    CompletedPrompt,
    FailedPrompt,
    AdvancedToNextPrompt,
    DrillCompleted,
    OptedOut,
    DialogEventBatch,
)
from stopcovid.dialog.registration import CodeValidationPayload
from stopcovid.dialog.models.state import UserProfile
from stopcovid.drills.drills import Drill, Prompt
from stopcovid.drill_progress.drill_progress import DrillProgressRepository, DrillInstance
from stopcovid import db
from __tests__.utils.factories import make_drill_instance


class TestDrillInstances(unittest.TestCase):
    def setUp(self):
        logging.disable(logging.CRITICAL)
        self.repo = DrillProgressRepository(db.get_test_sqlalchemy_engine)
        self.repo.drop_and_recreate_tables_testing_only()
        self.phone_number = "123456789"
        self.prompt1 = Prompt(slug="first", messages=[])
        self.prompt2 = Prompt(slug="second", messages=[])
        self.drill = Drill(slug="slug", name="name", prompts=[self.prompt1])
        self.seq = 1
        self.user_id = self.repo._create_or_update_user(
            DialogEventBatch(
                events=[
                    UserValidated(self.phone_number, UserProfile(True), CodeValidationPayload(True))
                ],
                phone_number=self.phone_number,
                seq="0",
                batch_id=uuid.uuid4(),
            ),
            None,
            self.repo.engine,
        )
        self.drill_instance = self._make_drill_instance()

    def _seq(self) -> str:
        result = str(self.seq)
        self.seq += 1
        return result

    def _make_drill_instance(self, **overrides) -> DrillInstance:
        return make_drill_instance(
            user_id=self.user_id, phone_number=self.phone_number, **overrides
        )

    def _make_batch(self, events):
        return DialogEventBatch(phone_number=self.phone_number, events=events, seq=self._seq())

    def test_get_and_save(self):
        self.assertIsNone(self.repo.get_drill_instance(self.drill_instance.drill_instance_id))
        self.repo._save_drill_instance(self.drill_instance)
        retrieved = self.repo.get_drill_instance(self.drill_instance.drill_instance_id)
        self.assertEqual(self.drill_instance, retrieved)

    def test_user_revalidated(self):
        drill_instance1 = self._make_drill_instance()
        drill_instance2 = self._make_drill_instance()
        self.repo._save_drill_instance(drill_instance1)
        self.repo._save_drill_instance(drill_instance2)
        self.assertTrue(drill_instance1.is_valid)
        self.assertTrue(drill_instance2.is_valid)

        self.repo.update_user(
            self._make_batch(
                [
                    UserValidated(
                        phone_number=self.phone_number,
                        user_profile=UserProfile(True),
                        code_validation_payload=CodeValidationPayload(valid=True, is_demo=True),
                    )
                ]
            )
        )
        drill_instance1 = self.repo.get_drill_instance(drill_instance1.drill_instance_id)
        drill_instance2 = self.repo.get_drill_instance(drill_instance2.drill_instance_id)
        self.assertFalse(drill_instance1.is_valid)
        self.assertFalse(drill_instance2.is_valid)

    def test_drill_started(self):
        event = DrillStarted(
            phone_number=self.phone_number,
            user_profile=UserProfile(True),
            drill=self.drill,
            first_prompt=self.prompt1,
        )
        self.repo.update_user(self._make_batch([event]))
        drill_instance = self.repo.get_drill_instance(event.drill_instance_id)
        self.assertIsNotNone(drill_instance)
        self.assertEqual(event.created_time, drill_instance.current_prompt_start_time)
        self.assertEqual(self.prompt1.slug, drill_instance.current_prompt_slug)
        self.assertIsNone(drill_instance.completion_time)
        self.assertTrue(drill_instance.is_valid)

    def test_drill_completed(self):
        self.repo._save_drill_instance(self.drill_instance)
        event = DrillCompleted(
            phone_number=self.phone_number,
            user_profile=UserProfile(True),
            drill_instance_id=self.drill_instance.drill_instance_id,
        )
        self.repo.update_user(self._make_batch([event]))
        retrieved = self.repo.get_drill_instance(self.drill_instance.drill_instance_id)
        self.assertEqual(event.created_time, retrieved.completion_time)
        self.assertIsNone(retrieved.current_prompt_last_response_time)
        self.assertIsNone(retrieved.current_prompt_start_time)
        self.assertIsNone(retrieved.current_prompt_slug)

    def test_opted_out_during_drill(self):
        self.repo._save_drill_instance(self.drill_instance)
        event = OptedOut(
            phone_number=self.phone_number,
            user_profile=UserProfile(True),
            drill_instance_id=self.drill_instance.drill_instance_id,
        )
        self.repo.update_user(self._make_batch([event]))
        retrieved = self.repo.get_drill_instance(self.drill_instance.drill_instance_id)
        self.assertFalse(retrieved.is_valid)

    def test_opted_out_not_during_drill(self):
        event = OptedOut(
            phone_number=self.phone_number, user_profile=UserProfile(True), drill_instance_id=None
        )
        self.repo.update_user(self._make_batch([event]))
        # make sure we don't crash

    def test_prompt_completed(self):
        self.repo._save_drill_instance(self.drill_instance)
        event = CompletedPrompt(
            phone_number=self.phone_number,
            user_profile=UserProfile(True),
            prompt=self.prompt1,
            drill_instance_id=self.drill_instance.drill_instance_id,
            response="go",
        )
        self.repo.update_user(self._make_batch([event]))
        retrieved = self.repo.get_drill_instance(self.drill_instance.drill_instance_id)
        self.assertEqual(event.created_time, retrieved.current_prompt_last_response_time)

    def test_prompt_failed(self):
        self.repo._save_drill_instance(self.drill_instance)
        event = FailedPrompt(
            phone_number=self.phone_number,
            user_profile=UserProfile(True),
            prompt=self.prompt1,
            drill_instance_id=self.drill_instance.drill_instance_id,
            response="go",
            abandoned=False,
        )
        self.repo.update_user(self._make_batch([event]))
        retrieved = self.repo.get_drill_instance(self.drill_instance.drill_instance_id)
        self.assertEqual(event.created_time, retrieved.current_prompt_last_response_time)

    def test_advanced_to_next_prompt(self):
        self.repo._save_drill_instance(self.drill_instance)
        event = CompletedPrompt(
            phone_number=self.phone_number,
            user_profile=UserProfile(True),
            prompt=self.prompt1,
            drill_instance_id=self.drill_instance.drill_instance_id,
            response="go",
        )
        self.repo.update_user(self._make_batch([event]))
        event = AdvancedToNextPrompt(
            phone_number=self.phone_number,
            user_profile=UserProfile(True),
            prompt=self.prompt2,
            drill_instance_id=self.drill_instance.drill_instance_id,
        )
        self.repo.update_user(self._make_batch([event]))
        retrieved = self.repo.get_drill_instance(self.drill_instance.drill_instance_id)
        self.assertEqual(self.prompt2.slug, retrieved.current_prompt_slug)
        self.assertIsNone(retrieved.current_prompt_last_response_time)
        self.assertEqual(event.created_time, retrieved.current_prompt_start_time)

    def test_get_incomplete_drills(self):
        incomplete_drill_instance = self._make_drill_instance(completion_time=None)
        complete_drill_instance = self._make_drill_instance(
            completion_time=datetime.datetime.now(datetime.timezone.utc)
        )
        self.repo._save_drill_instance(incomplete_drill_instance)
        self.repo._save_drill_instance(complete_drill_instance)
        results = self.repo.get_incomplete_drills()
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].drill_instance_id, incomplete_drill_instance.drill_instance_id)

    def test_get_incomplete_drills_with_inactive_for_minutes(self):
        just_started_drill_instance = self._make_drill_instance(
            current_prompt_start_time=datetime.datetime.now(datetime.timezone.utc)
            - datetime.timedelta(minutes=2),
            completion_time=None,
        )
        stale_drill_instance_1 = self._make_drill_instance(
            current_prompt_start_time=datetime.datetime.now(datetime.timezone.utc)
            - datetime.timedelta(minutes=61),
            completion_time=None,
        )
        stale_drill_instance_2 = self._make_drill_instance(
            current_prompt_start_time=datetime.datetime.now(datetime.timezone.utc)
            - datetime.timedelta(minutes=120),
            completion_time=None,
        )
        complete_drill_instance = self._make_drill_instance(
            completion_time=datetime.datetime.now(datetime.timezone.utc)
        )
        self.repo._save_drill_instance(just_started_drill_instance)
        self.repo._save_drill_instance(stale_drill_instance_1)
        self.repo._save_drill_instance(stale_drill_instance_2)
        self.repo._save_drill_instance(complete_drill_instance)
        results = self.repo.get_incomplete_drills(inactive_for_minutes_floor=60)
        self.assertEqual(len(results), 2)
        self.assertEqual(results[0].drill_instance_id, stale_drill_instance_1.drill_instance_id)
        self.assertEqual(results[1].drill_instance_id, stale_drill_instance_2.drill_instance_id)

    def test_get_incomplete_drills_with_inactive_for_minutes_ceil(self):
        recent_drill_instance = self._make_drill_instance(
            current_prompt_start_time=datetime.datetime.now(datetime.timezone.utc)
            - datetime.timedelta(minutes=65),
            completion_time=None,
        )
        really_old_drill_instance = self._make_drill_instance(
            current_prompt_start_time=datetime.datetime.now(datetime.timezone.utc)
            - datetime.timedelta(days=40),
            completion_time=None,
        )

        self.repo._save_drill_instance(recent_drill_instance)
        self.repo._save_drill_instance(really_old_drill_instance)

        results = self.repo.get_incomplete_drills(
            inactive_for_minutes_floor=60, inactive_for_minutes_ceil=60 * 24
        )
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].drill_instance_id, recent_drill_instance.drill_instance_id)

    def test_general_idempotence(self):
        self.repo._save_drill_instance(self.drill_instance)
        event = FailedPrompt(
            phone_number=self.phone_number,
            user_profile=UserProfile(True),
            prompt=self.prompt1,
            drill_instance_id=self.drill_instance.drill_instance_id,
            response="go",
            abandoned=False,
        )
        batch = self._make_batch([event])
        batch.seq = "0"
        self.repo.update_user(batch)
        retrieved = self.repo.get_drill_instance(self.drill_instance.drill_instance_id)
        self.assertNotEqual(event.created_time, retrieved.current_prompt_last_response_time)
