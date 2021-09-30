import datetime
import unittest
import uuid

from stopcovid.dialog.models.events import (
    UserValidated,
    UserValidationFailed,
    DrillStarted,
    CompletedPrompt,
    FailedPrompt,
    AdvancedToNextPrompt,
    DrillCompleted,
    OptedOut,
    NextDrillRequested,
    SchedulingDrillRequested,
    DialogEvent,
    event_from_dict,
    AdHocMessageSent,
    NameChangeDrillRequested,
    LanguageChangeDrillRequested,
    MenuRequested,
    UnhandledMessageReceived,
    SupportRequested,
    ThankYouReceived,
    UserUpdated,
)
from stopcovid.dialog.models.state import UserProfile, DialogState, PromptState
from stopcovid.dialog.registration import CodeValidationPayload
from stopcovid.sms.types import SMS

from stopcovid.drills.drills import Prompt, PromptMessage, Drill

DRILL = Drill(
    name="test-drill",
    slug="test-drill",
    prompts=[
        Prompt(slug="ignore-response-1", messages=[PromptMessage(text="{{msg1}}")]),
        Prompt(
            slug="store-response",
            messages=[PromptMessage(text="{{msg1}}")],
            response_user_profile_key="self_rating_1",
        ),
        Prompt(
            slug="graded-response-1",
            messages=[PromptMessage(text="{{msg1}}")],
            correct_response="{{response1}}",
        ),
        Prompt(
            slug="graded-response-2",
            messages=[PromptMessage(text="{{msg1}}")],
            correct_response="{{response1}}",
        ),
        Prompt(slug="ignore-response-2", messages=[PromptMessage(text="{{msg1}}")]),
    ],
)

NOW = datetime.datetime.now(datetime.timezone.utc)


class TestUserValidationEvents(unittest.TestCase):
    def test_user_validated(self):
        profile = UserProfile(validated=False)
        dialog_state = DialogState(phone_number="123456789", seq="0", user_profile=profile)
        event = UserValidated(
            phone_number="123456789",
            user_profile=profile,
            code_validation_payload=CodeValidationPayload(
                valid=True,
                is_demo=False,
                account_info={
                    "employer_id": 1,
                    "unit_id": 1,
                    "employer_name": "employer_name",
                    "unit_name": "unit_name",
                },
            ),
        )
        event.apply_to(dialog_state)
        self.assertTrue(dialog_state.user_profile.validated)
        self.assertEqual(
            {
                "employer_id": 1,
                "unit_id": 1,
                "employer_name": "employer_name",
                "unit_name": "unit_name",
            },
            dialog_state.user_profile.account_info,
        )

    def test_user_revalidated(self):
        profile = UserProfile(validated=True, is_demo=True)
        dialog_state = DialogState(
            phone_number="123456789",
            seq="0",
            user_profile=profile,
            current_drill=DRILL,
            drill_instance_id=uuid.uuid4(),
            current_prompt_state=PromptState(slug=DRILL.prompts[0].slug, start_time=NOW),
        )
        event = UserValidated(
            phone_number="123456789",
            user_profile=profile,
            code_validation_payload=CodeValidationPayload(
                valid=True,
                is_demo=False,
                account_info={
                    "employer_id": 1,
                    "unit_id": 1,
                    "employer_name": "employer_name",
                    "unit_name": "unit_name",
                },
            ),
        )
        event.apply_to(dialog_state)
        self.assertTrue(dialog_state.user_profile.validated)
        self.assertFalse(dialog_state.user_profile.is_demo)
        self.assertIsNone(dialog_state.current_drill)
        self.assertIsNone(dialog_state.current_prompt_state)
        self.assertIsNone(dialog_state.drill_instance_id)
        self.assertEqual(
            {
                "employer_id": 1,
                "unit_id": 1,
                "employer_name": "employer_name",
                "unit_name": "unit_name",
            },
            dialog_state.user_profile.account_info,
        )

    def test_user_validation_failed(self):
        profile = UserProfile(validated=False)
        dialog_state = DialogState(phone_number="123456789", seq="0", user_profile=profile)
        event = UserValidationFailed(phone_number="123456789", user_profile=profile)
        event.apply_to(dialog_state)
        self.assertFalse(dialog_state.user_profile.validated)


class TestDrillStarted(unittest.TestCase):
    def test_drill_started(self):
        profile = UserProfile(validated=True)
        event = DrillStarted(
            phone_number="123456789",
            user_profile=profile,
            drill=DRILL,
            first_prompt=DRILL.prompts[0],
            drill_instance_id=uuid.uuid4(),
        )
        dialog_state = DialogState(phone_number="123456789", seq="0", user_profile=profile)
        event.apply_to(dialog_state)
        self.assertEqual(DRILL, dialog_state.current_drill)
        self.assertEqual(
            PromptState(slug=DRILL.prompts[0].slug, start_time=event.created_time),
            dialog_state.current_prompt_state,
        )
        self.assertEqual(event.drill_instance_id, dialog_state.drill_instance_id)


class TestCompletedPrompt(unittest.TestCase):
    def test_completed_and_not_stored(self):
        profile = UserProfile(validated=True)
        event = CompletedPrompt(
            phone_number="123456789",
            user_profile=profile,
            prompt=DRILL.prompts[0],
            drill_instance_id=uuid.uuid4(),
            response="go",
        )
        dialog_state = DialogState(
            phone_number="123456789",
            seq="0",
            user_profile=profile,
            current_drill=DRILL,
            current_prompt_state=PromptState(slug=DRILL.prompts[0].slug, start_time=NOW),
        )
        event.apply_to(dialog_state)
        self.assertEqual(profile, dialog_state.user_profile)
        self.assertIsNone(dialog_state.current_prompt_state)
        self.assertIsNone(event.user_profile_updates)

    def test_completed_and_stored(self):
        profile = UserProfile(validated=True)
        event = CompletedPrompt(
            phone_number="123456789",
            user_profile=profile,
            prompt=DRILL.prompts[1],
            drill_instance_id=uuid.uuid4(),
            response="7",
        )
        dialog_state = DialogState(
            phone_number="123456789",
            seq="0",
            user_profile=profile,
            current_drill=DRILL,
            current_prompt_state=PromptState(slug=DRILL.prompts[0].slug, start_time=NOW),
        )
        event.apply_to(dialog_state)
        self.assertEqual(UserProfile(validated=True, self_rating_1="7"), dialog_state.user_profile)
        self.assertIsNone(dialog_state.current_prompt_state)


class TestFailedPrompt(unittest.TestCase):
    def test_failed_and_not_abandoned(self):
        profile = UserProfile(validated=True)
        event = FailedPrompt(
            phone_number="123456789",
            user_profile=profile,
            prompt=DRILL.prompts[2],
            drill_instance_id=uuid.uuid4(),
            response="b",
            abandoned=False,
        )
        dialog_state = DialogState(
            phone_number="123456789",
            seq="0",
            user_profile=profile,
            current_drill=DRILL,
            drill_instance_id=event.drill_instance_id,
            current_prompt_state=PromptState(slug=DRILL.prompts[2].slug, start_time=NOW),
        )
        event.apply_to(dialog_state)
        self.assertEqual(
            PromptState(
                slug=DRILL.prompts[2].slug,
                start_time=NOW,
                last_response_time=event.created_time,
                failures=1,
            ),
            dialog_state.current_prompt_state,
        )

    def test_failed_and_abandoned(self):
        profile = UserProfile(validated=True)
        event = FailedPrompt(
            phone_number="123456789",
            user_profile=profile,
            prompt=DRILL.prompts[2],
            drill_instance_id=uuid.uuid4(),
            response="b",
            abandoned=True,
        )
        dialog_state = DialogState(
            phone_number="123456789",
            seq="0",
            user_profile=profile,
            current_drill=DRILL,
            drill_instance_id=event.drill_instance_id,
            current_prompt_state=PromptState(slug=DRILL.prompts[2].slug, start_time=NOW),
        )
        event.apply_to(dialog_state)
        self.assertIsNone(dialog_state.current_prompt_state)


class TestAdvancedToNextPrompt(unittest.TestCase):
    def test_advanced_to_next_prompt(self):
        profile = UserProfile(validated=True)
        event = AdvancedToNextPrompt(
            phone_number="123456789",
            user_profile=profile,
            prompt=DRILL.prompts[1],
            drill_instance_id=uuid.uuid4(),
        )
        dialog_state = DialogState(
            phone_number="123456789",
            seq="0",
            user_profile=profile,
            current_drill=DRILL,
            drill_instance_id=event.drill_instance_id,
            current_prompt_state=PromptState(slug=DRILL.prompts[0].slug, start_time=NOW),
        )
        event.apply_to(dialog_state)
        self.assertEqual(
            PromptState(slug=DRILL.prompts[1].slug, start_time=event.created_time),
            dialog_state.current_prompt_state,
        )


class TestDrillCompleted(unittest.TestCase):
    def test_drill_completed(self):
        profile = UserProfile(validated=False)
        event = DrillCompleted(
            phone_number="123456789", user_profile=profile, drill_instance_id=uuid.uuid4()
        )
        dialog_state = DialogState(
            phone_number="123456789",
            seq="0",
            user_profile=profile,
            current_drill=DRILL,
            drill_instance_id=event.drill_instance_id,
            current_prompt_state=PromptState(slug=DRILL.prompts[-1].slug, start_time=NOW),
        )
        event.apply_to(dialog_state)
        self.assertIsNone(dialog_state.drill_instance_id)
        self.assertIsNone(dialog_state.current_prompt_state)
        self.assertIsNone(dialog_state.current_drill)


class TestOptedOut(unittest.TestCase):
    def test_opted_out_during_drill(self):
        profile = UserProfile(validated=True)
        event = OptedOut(
            phone_number="123456789", user_profile=profile, drill_instance_id=uuid.uuid4()
        )
        dialog_state = DialogState(
            phone_number="123456789",
            seq="0",
            user_profile=profile,
            current_drill=DRILL,
            drill_instance_id=event.drill_instance_id,
            current_prompt_state=PromptState(slug=DRILL.prompts[-1].slug, start_time=NOW),
        )

        self.assertFalse(profile.opted_out)
        event.apply_to(dialog_state)
        self.assertTrue(dialog_state.user_profile.opted_out)
        self.assertIsNone(dialog_state.drill_instance_id)
        self.assertIsNone(dialog_state.current_prompt_state)
        self.assertIsNone(dialog_state.current_drill)

    def test_opted_out_no_drill(self):
        profile = UserProfile(validated=True)
        event = OptedOut(phone_number="123456789", user_profile=profile, drill_instance_id=None)
        dialog_state = DialogState(phone_number="123456789", seq="0", user_profile=profile)

        self.assertFalse(profile.opted_out)
        event.apply_to(dialog_state)
        self.assertTrue(dialog_state.user_profile.opted_out)
        self.assertIsNone(dialog_state.drill_instance_id)
        self.assertIsNone(dialog_state.current_prompt_state)
        self.assertIsNone(dialog_state.current_drill)


class TestNextDrillRequested(unittest.TestCase):
    def test_next_drill_requested(self):
        profile = UserProfile(validated=True, opted_out=True)
        event = NextDrillRequested(
            phone_number="123456789", user_profile=profile, drill_instance_id=uuid.uuid4()
        )
        dialog_state = DialogState(phone_number="123456789", seq="0", user_profile=profile)

        self.assertTrue(profile.opted_out)
        event.apply_to(dialog_state)
        self.assertFalse(dialog_state.user_profile.opted_out)


class TestUserUpdate(unittest.TestCase):
    def test_user_updated(self):
        phone_number = "123456789"
        profile = UserProfile(validated=True)
        event = UserUpdated(
            phone_number=phone_number,
            user_profile=profile,
            user_profile_data={"name": "Cat Stevens"},
            purge_drill_state=True,
        )
        dialog_state = DialogState(
            phone_number=phone_number,
            seq="0",
            user_profile=profile,
            drill_instance_id=uuid.uuid4(),
            current_drill=DRILL,
        )

        event.apply_to(dialog_state)
        self.assertIsNone(dialog_state.current_drill)
        self.assertIsNone(dialog_state.drill_instance_id)


class TestSerialization(unittest.TestCase):
    def setUp(self) -> None:
        self.prompt = Prompt(
            slug="my-prompt",
            messages=[
                PromptMessage(text="one", media_url="http://giphy.com/puppies/1"),
                PromptMessage(text="two"),
            ],
        )
        self.drill = Drill(name="01 START", slug="01-start", prompts=[self.prompt])

    def _make_base_assertions(self, original: DialogEvent, deserialized: DialogEvent):
        self.assertEqual(original.event_id, deserialized.event_id)
        self.assertEqual(original.event_type, deserialized.event_type)
        self.assertEqual(original.phone_number, deserialized.phone_number)
        self.assertEqual(original.created_time, deserialized.created_time)

    def test_advanced_to_next_prompt(self):
        original = AdvancedToNextPrompt(
            phone_number="123456789",
            user_profile=UserProfile(validated=True),
            prompt=self.prompt,
            drill_instance_id=uuid.uuid4(),
        )
        serialized = original.dict()
        deserialized: AdvancedToNextPrompt = event_from_dict(serialized)  # type: ignore
        self._make_base_assertions(original, deserialized)
        self.assertEqual(original.prompt.slug, deserialized.prompt.slug)
        self.assertEqual(original.drill_instance_id, deserialized.drill_instance_id)

    def test_completed_prompt(self):
        original = CompletedPrompt(
            phone_number="123456789",
            user_profile=UserProfile(validated=True),
            prompt=self.prompt,
            response="hello",
            drill_instance_id=uuid.uuid4(),
        )
        serialized = original.dict()
        deserialized: CompletedPrompt = event_from_dict(serialized)  # type: ignore
        self._make_base_assertions(original, deserialized)
        self.assertEqual(original.prompt.slug, deserialized.prompt.slug)
        self.assertEqual(original.response, deserialized.response)
        self.assertEqual(original.drill_instance_id, deserialized.drill_instance_id)

    def test_failed_prompt(self):
        original = FailedPrompt(
            phone_number="123456789",
            user_profile=UserProfile(validated=True),
            prompt=self.prompt,
            response="hello",
            abandoned=True,
            drill_instance_id=uuid.uuid4(),
        )
        serialized = original.dict()
        deserialized: FailedPrompt = event_from_dict(serialized)  # type: ignore
        self._make_base_assertions(original, deserialized)
        self.assertEqual(original.prompt.slug, deserialized.prompt.slug)
        for original_message, deserialized_message in zip(
            original.prompt.messages, deserialized.prompt.messages
        ):
            self.assertEqual(original_message.text, deserialized_message.text)
            self.assertEqual(original_message.media_url, deserialized_message.media_url)
        self.assertEqual(original.response, deserialized.response)
        self.assertEqual(original.abandoned, deserialized.abandoned)
        self.assertEqual(original.drill_instance_id, deserialized.drill_instance_id)

    def test_drill_started(self):
        original = DrillStarted(
            phone_number="12345678",
            user_profile=UserProfile(validated=True),
            drill=self.drill,
            first_prompt=self.prompt,
            drill_instance_id=uuid.uuid4(),
        )
        serialized = original.dict()
        deserialized: DrillStarted = event_from_dict(serialized)  # type: ignore
        self._make_base_assertions(original, deserialized)
        self.assertEqual(original.drill.name, deserialized.drill.name)
        self.assertEqual(original.drill_instance_id, deserialized.drill_instance_id)
        self.assertEqual(original.first_prompt.slug, deserialized.first_prompt.slug)

    def test_drill_completed(self):
        original = DrillCompleted(
            phone_number="12345678",
            user_profile=UserProfile(validated=True),
            drill_instance_id=uuid.uuid4(),
        )
        serialized = original.dict()
        deserialized: DrillCompleted = event_from_dict(serialized)  # type: ignore
        self._make_base_assertions(original, deserialized)
        self.assertEqual(original.drill_instance_id, deserialized.drill_instance_id)

    def test_user_validated(self):
        original = UserValidated(
            phone_number="123456789",
            user_profile=UserProfile(validated=True),
            code_validation_payload=CodeValidationPayload(valid=True, is_demo=True),
        )
        serialized = original.dict()
        deserialized = event_from_dict(serialized)
        self._make_base_assertions(original, deserialized)

    def test_user_validation_failed(self):
        original = UserValidationFailed(
            phone_number="123456789", user_profile=UserProfile(validated=True)
        )
        serialized = original.dict()
        deserialized = event_from_dict(serialized)
        self._make_base_assertions(original, deserialized)

    def test_opted_out(self):
        original = OptedOut(
            phone_number="123456789",
            user_profile=UserProfile(validated=True),
            drill_instance_id=uuid.uuid4(),
        )
        serialized = original.dict()
        deserialized: OptedOut = event_from_dict(serialized)  # type: ignore
        self._make_base_assertions(original, deserialized)
        self.assertEqual(original.drill_instance_id, deserialized.drill_instance_id)

    def test_next_drill_requested(self):
        original = NextDrillRequested(
            phone_number="123456789", user_profile=UserProfile(validated=True)
        )
        serialized = original.dict()
        deserialized = event_from_dict(serialized)
        self._make_base_assertions(original, deserialized)

    def test_scheduling_drill_requested(self):
        original = SchedulingDrillRequested(
            phone_number="123456789",
            user_profile=UserProfile(validated=True),
            abandoned_drill_instance_id="11111111-1111-1111-1111-111111111111",
        )
        serialized = original.dict()
        deserialized = event_from_dict(serialized)
        self._make_base_assertions(original, deserialized)
        self.assertEqual(
            deserialized.abandoned_drill_instance_id,
            uuid.UUID("11111111-1111-1111-1111-111111111111"),
        )

    def test_send_adhoc_message(self):
        original = AdHocMessageSent(
            phone_number="123456789",
            user_profile=UserProfile(validated=True),
            sms=SMS(body="foobar"),
        )
        serialized = original.dict()
        deserialized = event_from_dict(serialized)
        self._make_base_assertions(original, deserialized)

    def test_name_change_drill_requested(self):
        original = NameChangeDrillRequested(
            phone_number="123456789",
            user_profile=UserProfile(validated=True),
            abandoned_drill_instance_id="11111111-1111-1111-1111-111111111111",
        )
        serialized = original.dict()
        deserialized = event_from_dict(serialized)
        self._make_base_assertions(original, deserialized)
        self.assertEqual(
            deserialized.abandoned_drill_instance_id,
            uuid.UUID("11111111-1111-1111-1111-111111111111"),
        )

    def test_language_change_drill_requested(self):
        original = LanguageChangeDrillRequested(
            phone_number="123456789",
            user_profile=UserProfile(validated=True),
            abandoned_drill_instance_id="11111111-1111-1111-1111-111111111111",
        )
        serialized = original.dict()
        deserialized = event_from_dict(serialized)
        self._make_base_assertions(original, deserialized)
        self.assertEqual(
            deserialized.abandoned_drill_instance_id,
            uuid.UUID("11111111-1111-1111-1111-111111111111"),
        )

    def test_support_requested(self):
        original = SupportRequested(
            phone_number="123456789",
            user_profile=UserProfile(validated=True),
        )
        serialized = original.dict()
        deserialized = event_from_dict(serialized)
        self._make_base_assertions(original, deserialized)

    def test_menu_requested(self):
        original = MenuRequested(
            phone_number="123456789",
            user_profile=UserProfile(validated=True),
        )
        serialized = original.dict()
        deserialized = event_from_dict(serialized)
        self._make_base_assertions(original, deserialized)

    def test_unhandled_message_received(self):
        original = UnhandledMessageReceived(
            phone_number="123456789", user_profile=UserProfile(validated=True), message="blabla"
        )
        serialized = original.dict()
        deserialized = event_from_dict(serialized)
        self._make_base_assertions(original, deserialized)

    def test_thank_you_received(self):
        original = ThankYouReceived(
            phone_number="123456789", user_profile=UserProfile(validated=True)
        )
        serialized = original.dict()
        deserialized = event_from_dict(serialized)
        self._make_base_assertions(original, deserialized)
