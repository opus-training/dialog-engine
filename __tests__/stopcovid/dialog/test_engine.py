import logging
import unittest
from unittest.mock import MagicMock, Mock, patch
from typing import Optional
import uuid
from datetime import datetime, timedelta
from pytz import UTC

from stopcovid.dialog.engine import (
    process_command,
    ProcessSMSMessage,
    StartDrill,
    SendAdHocMessage,
    UpdateUser,
)
from stopcovid.dialog.models.events import (
    DialogEventBatch,
    DialogEventType,
    DrillStarted,
    CompletedPrompt,
    AdvancedToNextPrompt,
    FailedPrompt,
    DrillCompleted,
)
from stopcovid.dialog.models.state import DialogState, PromptState, AccountInfo

from stopcovid.dialog.registration import CodeValidationPayload
from stopcovid.drills.drills import Drill, Prompt, PromptMessage


class TestProcessCommand(unittest.TestCase):
    def setUp(self) -> None:
        logging.disable(logging.CRITICAL)
        self.drill_instance_id = uuid.UUID("11111111-1111-1111-1111-111111111111")
        self.phone_number = "123456789"
        self.dialog_state = DialogState(
            phone_number=self.phone_number,
            seq="0",
            drill_instance_id=self.drill_instance_id,
        )
        self.drill = Drill(
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
        self.repo = MagicMock()
        self.repo.fetch_dialog_state = MagicMock(return_value=self.dialog_state)
        self.repo.persist_dialog_state = MagicMock()
        self.next_seq = 1
        self.now = datetime.now(UTC)

    def _process_command(self, command) -> DialogEventBatch:
        persist_dialog_call_count = self.repo.persist_dialog_state.call_count
        process_command(command, str(self.next_seq), repo=self.repo)
        self.next_seq += 1
        self.assertEqual(
            persist_dialog_call_count + 1,
            len(self.repo.persist_dialog_state.call_args_list),
        )
        return self.repo.persist_dialog_state.call_args[0][0]

    def _assert_event_types(self, batch: DialogEventBatch, *args: DialogEventType):
        self.assertEqual(len(args), len(batch.events), f"{args} vs {batch.events}")
        for i in range(len(batch.events)):
            self.assertEqual(args[i], batch.events[i].event_type)

    def _set_current_prompt(self, prompt_index: int, drill: Optional[Drill] = None):
        if not drill:
            drill = self.drill
        self.dialog_state.current_drill = drill
        prompt = drill.prompts[prompt_index]
        self.dialog_state.current_prompt_state = PromptState(slug=prompt.slug, start_time=self.now)

    def test_skip_processed_sequence_numbers(self):
        command = Mock(wraps=ProcessSMSMessage(self.phone_number, "hey"))
        process_command(command, "0", repo=self.repo)
        self.assertFalse(command.execute.called)

    def test_advance_sequence_numbers(self):
        validator = MagicMock()
        validation_payload = CodeValidationPayload(
            valid=True,
            account_info={
                "employer_id": 1,
                "unit_id": 1,
                "employer_name": "employer_name",
                "unit_name": "unit_name",
            },
        )
        validator.validate_code = MagicMock(return_value=validation_payload)
        command = ProcessSMSMessage(self.phone_number, "hey", registration_validator=validator)
        batch = self._process_command(command)
        self.assertEqual(1, len(batch.events))
        self.assertEqual("1", self.dialog_state.seq)

    def test_first_message_validates_user(self):
        validator = MagicMock()
        validation_payload = CodeValidationPayload(
            valid=True,
            account_info={
                "employer_id": 1,
                "unit_id": 1,
                "employer_name": "employer_name",
                "unit_name": "unit_name",
            },
        )
        validator.validate_code = MagicMock(return_value=validation_payload)
        command = ProcessSMSMessage(self.phone_number, "hey", registration_validator=validator)
        self.assertFalse(self.dialog_state.user_profile.validated)

        batch = self._process_command(command)
        self._assert_event_types(batch, DialogEventType.USER_VALIDATED)
        self.assertEqual(
            validation_payload, batch.events[0].code_validation_payload  # type: ignore
        )
        # and account info is set on the event and user profile
        self.assertEqual(
            batch.events[0].user_profile.account_info,
            AccountInfo(
                employer_id=1, unit_id=1, employer_name="employer_name", unit_name="unit_name"
            ),
        )

    def test_advance_demo_user(self):
        validator = MagicMock()
        validation_payload = CodeValidationPayload(valid=True, is_demo=True)
        validator.validate_code = MagicMock(return_value=validation_payload)
        self.assertFalse(self.dialog_state.user_profile.validated)
        command = ProcessSMSMessage(self.phone_number, "hey", registration_validator=validator)

        batch = self._process_command(command)
        self._assert_event_types(batch, DialogEventType.USER_VALIDATED)

        command = StartDrill(self.phone_number, self.drill.slug, self.drill.dict(), uuid.uuid4())
        self._process_command(command)

        # the user's next message isn't a validation code - so we just keep going
        validation_payload = CodeValidationPayload(valid=False)
        validator.validate_code = MagicMock(return_value=validation_payload)
        command = ProcessSMSMessage(self.phone_number, "hey", registration_validator=validator)

        batch = self._process_command(command)
        self._assert_event_types(
            batch,
            DialogEventType.COMPLETED_PROMPT,
            DialogEventType.ADVANCED_TO_NEXT_PROMPT,
        )

    def test_first_message_does_not_validate_user(self):
        validator = MagicMock()
        validation_payload = CodeValidationPayload(valid=False)
        validator.validate_code = MagicMock(return_value=validation_payload)
        command = ProcessSMSMessage(self.phone_number, "hey", registration_validator=validator)
        self.assertFalse(self.dialog_state.user_profile.validated)

        batch = self._process_command(command)

        self._assert_event_types(batch, DialogEventType.USER_VALIDATION_FAILED)

    def test_start_drill(self):
        self.dialog_state.user_profile.validated = True
        command = StartDrill(self.phone_number, self.drill.slug, self.drill.dict(), uuid.uuid4())

        batch = self._process_command(command)

        self._assert_event_types(batch, DialogEventType.DRILL_STARTED)
        event: DrillStarted = batch.events[0]  # type: ignore
        self.assertEqual(self.drill.dict(), event.drill.dict())
        self.assertEqual(self.drill.first_prompt().slug, event.first_prompt.slug)
        self.assertIsNotNone(event.drill_instance_id)

    def test_start_drill_not_validated(self):
        self.dialog_state.user_profile.validated = False
        self.dialog_state.user_profile.opted_out = False
        command = StartDrill(self.phone_number, self.drill.slug, self.drill.dict(), uuid.uuid4())

        batch = self._process_command(command)
        self._assert_event_types(batch, DialogEventType.DRILL_STARTED)

    def test_revalidate_demo_user(self):
        validator = MagicMock()
        validation_payload = CodeValidationPayload(valid=True, is_demo=True)
        validator.validate_code = MagicMock(return_value=validation_payload)
        self.assertFalse(self.dialog_state.user_profile.validated)
        command = ProcessSMSMessage(self.phone_number, "hey", registration_validator=validator)

        batch = self._process_command(command)
        self._assert_event_types(batch, DialogEventType.USER_VALIDATED)

        command = StartDrill(self.phone_number, self.drill.slug, self.drill.dict(), uuid.uuid4())
        self._process_command(command)

        validation_payload = CodeValidationPayload(
            valid=True,
            account_info={
                "employer_id": 1,
                "unit_id": 1,
                "employer_name": "employer_name",
                "unit_name": "unit_name",
            },
        )
        validator.validate_code = MagicMock(return_value=validation_payload)
        command = ProcessSMSMessage(self.phone_number, "hey", registration_validator=validator)

        batch = self._process_command(command)
        self._assert_event_types(batch, DialogEventType.USER_VALIDATED)

    def test_revalidate_user_without_org(self):
        validator = MagicMock()
        validation_payload = CodeValidationPayload(valid=True, is_demo=True)
        validator.validate_code = MagicMock(return_value=validation_payload)
        self.dialog_state.user_profile.validated = True
        self.dialog_state.user_profile.account_info = AccountInfo(employer_id=None)
        command = ProcessSMSMessage(self.phone_number, "hey", registration_validator=validator)
        batch = self._process_command(command)
        self._assert_event_types(batch, DialogEventType.USER_VALIDATED)
        validation_payload = CodeValidationPayload(
            valid=True,
            account_info={
                "employer_id": 1,
                "unit_id": 1,
                "employer_name": "employer_name",
                "unit_name": "unit_name",
            },
        )

    def test_doesnt_revalidate_someone_with_an_org(self):
        validator = MagicMock()
        validation_payload = CodeValidationPayload(valid=True, is_demo=True)
        validator.validate_code = MagicMock(return_value=validation_payload)
        self.dialog_state.user_profile.validated = True
        self.dialog_state.user_profile.account_info = AccountInfo(employer_id=1)
        command = ProcessSMSMessage(self.phone_number, "hey", registration_validator=validator)
        batch = self._process_command(command)

        # not a USER_VALIDATED event
        self._assert_event_types(batch, DialogEventType.UNHANDLED_MESSAGE_RECEIVED)

    def test_start_drill_opted_out(self):
        self.dialog_state.user_profile.validated = True
        self.dialog_state.user_profile.opted_out = True
        command = StartDrill(self.phone_number, self.drill.slug, self.drill.dict(), uuid.uuid4())

        batch = self._process_command(command)
        self.assertEqual(0, len(batch.events))

    def test_complete_and_advance(self):
        self.dialog_state.user_profile.validated = True
        self._set_current_prompt(0)
        command = ProcessSMSMessage(self.phone_number, "go")
        batch = self._process_command(command)
        self._assert_event_types(
            batch,
            DialogEventType.COMPLETED_PROMPT,
            DialogEventType.ADVANCED_TO_NEXT_PROMPT,
        )
        completed_event: CompletedPrompt = batch.events[0]  # type: ignore
        self.assertEqual(completed_event.prompt, self.drill.prompts[0])
        self.assertEqual(completed_event.response, "go")
        self.assertEqual(completed_event.drill_instance_id, self.dialog_state.drill_instance_id)

        advanced_event: AdvancedToNextPrompt = batch.events[1]  # type: ignore
        self.assertEqual(self.drill.prompts[1], advanced_event.prompt)
        self.assertEqual(self.dialog_state.drill_instance_id, advanced_event.drill_instance_id)

    @patch("stopcovid.drills.drills.Prompt.should_advance_with_answer", return_value=False)
    def test_repeat_with_wrong_answer(self, *args):
        self.dialog_state.user_profile.validated = True
        self._set_current_prompt(2)
        command = ProcessSMSMessage(self.phone_number, "completely wrong answer")
        batch = self._process_command(command)
        self._assert_event_types(batch, DialogEventType.FAILED_PROMPT)

        failed_event: FailedPrompt = batch.events[0]  # type: ignore
        self.assertEqual(failed_event.prompt, self.drill.prompts[2])
        self.assertFalse(failed_event.abandoned)
        self.assertEqual(failed_event.response, "completely wrong answer")
        self.assertEqual(failed_event.drill_instance_id, self.dialog_state.drill_instance_id)

    @patch("stopcovid.drills.drills.Prompt.should_advance_with_answer", return_value=False)
    def test_advance_with_too_many_wrong_answers(self, *args):
        self.dialog_state.user_profile.validated = True
        self._set_current_prompt(2)
        self.dialog_state.current_prompt_state.failures = 1

        command = ProcessSMSMessage(self.phone_number, "completely wrong answer")
        batch = self._process_command(command)
        self._assert_event_types(
            batch,
            DialogEventType.FAILED_PROMPT,
            DialogEventType.ADVANCED_TO_NEXT_PROMPT,
        )

        failed_event: FailedPrompt = batch.events[0]  # type: ignore
        self.assertEqual(failed_event.prompt, self.drill.prompts[2])
        self.assertTrue(failed_event.abandoned)
        self.assertEqual(failed_event.response, "completely wrong answer")
        self.assertEqual(failed_event.drill_instance_id, self.dialog_state.drill_instance_id)

        advanced_event: AdvancedToNextPrompt = batch.events[1]  # type: ignore
        self.assertEqual(self.drill.prompts[3], advanced_event.prompt)
        self.assertEqual(self.dialog_state.drill_instance_id, advanced_event.drill_instance_id)

    @patch("stopcovid.drills.drills.Prompt.should_advance_with_answer", return_value=True)
    def test_conclude_with_right_answer(self, *args):
        self.dialog_state.user_profile.validated = True
        self._set_current_prompt(3)
        command = ProcessSMSMessage(self.phone_number, "foo")
        batch = self._process_command(command)
        self._assert_event_types(
            batch,
            DialogEventType.COMPLETED_PROMPT,
            DialogEventType.ADVANCED_TO_NEXT_PROMPT,
            DialogEventType.DRILL_COMPLETED,
        )
        completed_event: CompletedPrompt = batch.events[0]  # type: ignore
        self.assertEqual(completed_event.prompt, self.drill.prompts[3])
        self.assertEqual(completed_event.response, "foo")
        self.assertEqual(completed_event.drill_instance_id, self.drill_instance_id)

        advanced_event: AdvancedToNextPrompt = batch.events[1]  # type: ignore
        self.assertEqual(self.drill.prompts[4], advanced_event.prompt)

        self.assertEqual(advanced_event.drill_instance_id, self.drill_instance_id)

        drill_completed_event: DrillCompleted = batch.events[2]  # type: ignore
        self.assertEqual(drill_completed_event.drill_instance_id, self.drill_instance_id)
        self.assertIsNone(self.dialog_state.drill_instance_id)

    @patch("stopcovid.drills.drills.Prompt.should_advance_with_answer", return_value=True)
    def test_drill_with_one_prompt(self, *args):
        choose_language_drill = Drill(
            name="test-drill",
            slug="test-drill",
            prompts=[
                Prompt(
                    slug="ignore-response-1",
                    messages=[PromptMessage(text="{{msg1}}")],
                    response_user_profile_key="language",
                ),
            ],
        )
        self.dialog_state.user_profile.validated = True
        self.dialog_state.current_drill = choose_language_drill
        self._set_current_prompt(0, drill=choose_language_drill)
        command = ProcessSMSMessage(self.phone_number, "es")
        batch = self._process_command(command)

        self._assert_event_types(
            batch,
            DialogEventType.COMPLETED_PROMPT,
            DialogEventType.DRILL_COMPLETED,
        )
        self.assertEqual(batch.events[0].user_profile_updates, {"language": "es"})
        self.assertEqual(batch.user_profile.language, "es")

    @patch("stopcovid.drills.drills.Prompt.should_advance_with_answer", return_value=False)
    def test_conclude_with_too_many_wrong_answers(self, *args):
        self.dialog_state.user_profile.validated = True
        self._set_current_prompt(3)
        self.dialog_state.current_prompt_state.failures = 1

        command = ProcessSMSMessage(self.phone_number, "completely wrong answer")
        batch = self._process_command(command)
        self._assert_event_types(
            batch,
            DialogEventType.FAILED_PROMPT,
            DialogEventType.ADVANCED_TO_NEXT_PROMPT,
            DialogEventType.DRILL_COMPLETED,
        )

        failed_event: FailedPrompt = batch.events[0]  # type: ignore
        self.assertEqual(failed_event.prompt, self.drill.prompts[3])
        self.assertTrue(failed_event.abandoned)
        self.assertEqual(failed_event.response, "completely wrong answer")
        self.assertEqual(failed_event.drill_instance_id, self.drill_instance_id)
        self.assertEqual(batch.events[0].user_profile_updates, None)

        advanced_event: AdvancedToNextPrompt = batch.events[1]  # type: ignore
        self.assertEqual(self.drill.prompts[4], advanced_event.prompt)
        self.assertEqual(advanced_event.drill_instance_id, self.drill_instance_id)

        drill_completed_event: DrillCompleted = batch.events[2]  # type: ignore
        self.assertEqual(drill_completed_event.drill_instance_id, self.drill_instance_id)
        self.assertEqual(self.dialog_state.drill_instance_id, None)

    @patch("stopcovid.drills.drills.Prompt.should_advance_with_answer", return_value=False)
    def test_fail_prompt_with_empty_response_stores_response_as_null(self, *args):
        self.dialog_state.user_profile.validated = True
        self._set_current_prompt(3)
        self.dialog_state.current_prompt_state.failures = 0

        command = ProcessSMSMessage(self.phone_number, "")
        batch = self._process_command(command)
        self._assert_event_types(
            batch,
            DialogEventType.FAILED_PROMPT,
        )

        failed_event: FailedPrompt = batch.events[0]  # type: ignore
        self.assertEqual(failed_event.response, None)

    def test_opt_out(self):
        self.dialog_state.user_profile.validated = True
        self._set_current_prompt(0)
        command = ProcessSMSMessage(self.phone_number, "stop")
        batch = self._process_command(command)
        self._assert_event_types(batch, DialogEventType.OPTED_OUT)

    def test_message_during_opt_out(self):
        self.dialog_state.user_profile.validated = True
        self.dialog_state.user_profile.opted_out = True
        command = ProcessSMSMessage(self.phone_number, "it's not a bacteria")
        batch = self._process_command(command)
        self.assertEqual(0, len(batch.events))

    def test_opt_back_in(self):
        self.dialog_state.user_profile.validated = True
        self.dialog_state.user_profile.account_info = AccountInfo(employer_id=1)
        self.dialog_state.user_profile.opted_out = True
        command = ProcessSMSMessage(self.phone_number, "start")
        batch = self._process_command(command)
        self._assert_event_types(batch, DialogEventType.NEXT_DRILL_REQUESTED)

    def test_ask_for_help(self):
        command = ProcessSMSMessage(self.phone_number, "help")
        batch = self._process_command(command)
        self.assertEqual(0, len(batch.events))  # response handled by twilio

    def test_ask_for_help_validated(self):
        self.dialog_state.user_profile.validated = True
        self.dialog_state.user_profile.account_info = AccountInfo(employer_id=1)
        command = ProcessSMSMessage(self.phone_number, "help")
        batch = self._process_command(command)
        self.assertEqual(0, len(batch.events))  # response handled by twilio

    def test_ask_for_more(self):
        self.dialog_state.user_profile.validated = True
        self.dialog_state.user_profile.account_info = AccountInfo(employer_id=1)
        command = ProcessSMSMessage(self.phone_number, "more")
        batch = self._process_command(command)
        self._assert_event_types(batch, DialogEventType.NEXT_DRILL_REQUESTED)

    def test_ask_for_mas(self):
        self.dialog_state.user_profile.validated = True
        self.dialog_state.user_profile.account_info = AccountInfo(employer_id=1)
        command = ProcessSMSMessage(self.phone_number, "mas")
        batch = self._process_command(command)
        self._assert_event_types(batch, DialogEventType.NEXT_DRILL_REQUESTED)

        command = ProcessSMSMessage(self.phone_number, "más")
        batch = self._process_command(command)
        self._assert_event_types(batch, DialogEventType.NEXT_DRILL_REQUESTED)

    def test_ask_for_drill(self):
        self.dialog_state.user_profile.validated = True
        self.dialog_state.user_profile.account_info = AccountInfo(employer_id=1)
        self.dialog_state.current_drill = None
        command = ProcessSMSMessage(self.phone_number, "go")
        batch = self._process_command(command)
        self._assert_event_types(batch, DialogEventType.DRILL_REQUESTED)

        command = ProcessSMSMessage(self.phone_number, "vamos")
        batch = self._process_command(command)
        self._assert_event_types(batch, DialogEventType.DRILL_REQUESTED)

        self.dialog_state.current_drill = self.drill
        command = ProcessSMSMessage(self.phone_number, "go")
        batch = self._process_command(command)
        self._assert_event_types(batch, DialogEventType.UNHANDLED_MESSAGE_RECEIVED)

    def test_ask_for_drill_on_stale_drill(self):
        self.dialog_state.user_profile.validated = True
        self.dialog_state.user_profile.account_info = AccountInfo(employer_id=1)
        self.dialog_state.current_drill = self.drill

        # texting go while you have an old drill emits a DRILL_REQUESTED event
        self.dialog_state.current_prompt_state = PromptState(
            slug=self.drill.prompts[0].slug, start_time=self.now - timedelta(hours=40)
        )
        command = ProcessSMSMessage(self.phone_number, "go")
        batch = self._process_command(command)
        self._assert_event_types(batch, DialogEventType.DRILL_REQUESTED)

        # but if you have a drill you recently interacted with it will
        self.dialog_state.current_prompt_state = PromptState(
            slug=self.drill.prompts[0].slug, start_time=self.now - timedelta(minutes=1)
        )
        command = ProcessSMSMessage(self.phone_number, "go")
        batch = self._process_command(command)
        self._assert_event_types(
            batch, DialogEventType.COMPLETED_PROMPT, DialogEventType.ADVANCED_TO_NEXT_PROMPT
        )

    def test_send_ad_hoc_message(self):
        self.dialog_state.user_profile.validated = True
        self.dialog_state.user_profile.account_info = AccountInfo(employer_id=1)
        message = "An ad hoc message to a user"
        media_url = "https://gph.is/1w6mM6h"
        command = SendAdHocMessage(
            phone_number=self.phone_number, message=message, media_url=media_url
        )
        batch = self._process_command(command)
        self._assert_event_types(batch, DialogEventType.AD_HOC_MESSAGE_SENT)

        event = batch.events[0]
        self.assertEqual(event.sms.body, message)  # type:ignore
        self.assertEqual(event.sms.media_url, media_url)  # type:ignore

    def test_ask_for_scheduling_drill(self):
        messages = ["schedule", "calendario"]
        for message in messages:
            self.dialog_state.user_profile.validated = True
            self.dialog_state.user_profile.account_info = AccountInfo(employer_id=1)
            self.dialog_state.drill_instance_id = "11111111-1111-1111-1111-111111111111"
            self.dialog_state.current_prompt_state = "blabla"
            command = ProcessSMSMessage(self.phone_number, message)
            batch = self._process_command(command)
            self._assert_event_types(batch, DialogEventType.SCHEDULING_DRILL_REQUESTED)
            self.assertIsNone(self.dialog_state.current_drill)
            self.assertIsNone(self.dialog_state.drill_instance_id)
            self.assertIsNone(self.dialog_state.current_prompt_state)
            self.assertEqual(
                batch.events[0].abandoned_drill_instance_id,
                uuid.UUID("11111111-1111-1111-1111-111111111111"),
            )

    def test_change_name_drill_requested(self):
        for message in ["name", "nombre"]:
            self.dialog_state.user_profile.validated = True
            self.dialog_state.user_profile.account_info = AccountInfo(employer_id=1)
            self.dialog_state.drill_instance_id = "11111111-1111-1111-1111-111111111111"
            self.dialog_state.current_prompt_state = "blabla"
            command = ProcessSMSMessage(self.phone_number, message)
            batch = self._process_command(command)
            self._assert_event_types(batch, DialogEventType.NAME_CHANGE_DRILL_REQUESTED)
            self.assertIsNone(self.dialog_state.current_drill)
            self.assertIsNone(self.dialog_state.drill_instance_id)
            self.assertIsNone(self.dialog_state.current_prompt_state)
            self.assertEqual(
                batch.events[0].abandoned_drill_instance_id,
                uuid.UUID("11111111-1111-1111-1111-111111111111"),
            )

    def test_change_language_drill_requested(self):
        for message in ["lang", "language", "idioma"]:
            self.dialog_state.user_profile.validated = True
            self.dialog_state.user_profile.account_info = AccountInfo(employer_id=1)
            self.dialog_state.drill_instance_id = "11111111-1111-1111-1111-111111111111"
            self.dialog_state.current_prompt_state = "blabla"
            command = ProcessSMSMessage(self.phone_number, message)
            batch = self._process_command(command)
            self._assert_event_types(batch, DialogEventType.LANGUAGE_CHANGE_DRILL_REQUESTED)
            self.assertIsNone(self.dialog_state.current_drill)
            self.assertIsNone(self.dialog_state.drill_instance_id)
            self.assertIsNone(self.dialog_state.current_prompt_state)
            self.assertEqual(
                batch.events[0].abandoned_drill_instance_id,
                uuid.UUID("11111111-1111-1111-1111-111111111111"),
            )

    def test_certain_keywords_ignored_while_during_lesson(self):
        for message in ["lang", "schedule", "horario", "more", "mas", "name"]:
            self.dialog_state.user_profile.validated = True
            self.dialog_state.user_profile.account_info = AccountInfo(employer_id=1)
            self.dialog_state.drill_instance_id = "11111111-1111-1111-1111-111111111111"
            self._set_current_prompt(1)
            self.dialog_state.current_drill = self.drill
            command = ProcessSMSMessage(self.phone_number, message)
            batch = self._process_command(command)
            self._assert_event_types(
                batch, DialogEventType.COMPLETED_PROMPT, DialogEventType.ADVANCED_TO_NEXT_PROMPT
            )

    def test_dashboard_requested(self):
        for message in ["dashboard", "tablero"]:
            self.dialog_state.user_profile.validated = True
            self.dialog_state.user_profile.account_info = AccountInfo(employer_id=1)
            self.dialog_state.current_drill = "balbla"
            self.dialog_state.drill_instance_id = "11111111-1111-1111-1111-111111111111"
            self.dialog_state.current_prompt_state = "blabla"
            command = ProcessSMSMessage(self.phone_number, message)
            batch = self._process_command(command)
            self._assert_event_types(batch, DialogEventType.DASHBOARD_REQUESTED)
            self.assertIsNone(
                batch.events[0].abandoned_drill_instance_id,
            )

    def test_support_requested(self):
        for message in [
            "support",
            "ayuda",
        ]:
            self.dialog_state.user_profile.validated = True
            self.dialog_state.user_profile.account_info = AccountInfo(employer_id=1)
            self.dialog_state.current_drill = "balbla"
            self.dialog_state.drill_instance_id = "11111111-1111-1111-1111-111111111111"
            self.dialog_state.current_prompt_state = "blabla"
            command = ProcessSMSMessage(self.phone_number, message)
            batch = self._process_command(command)
            self._assert_event_types(batch, DialogEventType.SUPPORT_REQUESTED)
            self.assertIsNone(self.dialog_state.current_drill)
            self.assertIsNone(self.dialog_state.drill_instance_id)
            self.assertIsNone(self.dialog_state.current_prompt_state)
            self.assertEqual(
                batch.events[0].abandoned_drill_instance_id,
                uuid.UUID("11111111-1111-1111-1111-111111111111"),
            )

    def test_menu_requested(self):
        for message in ["menu", "menú"]:
            self.dialog_state.user_profile.validated = True
            self.dialog_state.user_profile.account_info = AccountInfo(employer_id=1)
            self.dialog_state.current_drill = "balbla"
            self.dialog_state.drill_instance_id = "11111111-1111-1111-1111-111111111111"
            self.dialog_state.current_prompt_state = "blabla"
            command = ProcessSMSMessage(self.phone_number, message)
            batch = self._process_command(command)
            self._assert_event_types(batch, DialogEventType.MENU_REQUESTED)

    def test_unhandled_message_received(self):
        self.dialog_state.user_profile.validated = True
        self.dialog_state.user_profile.account_info = AccountInfo(employer_id=1)
        command = ProcessSMSMessage(self.phone_number, "BLABLABLA")
        batch = self._process_command(command)
        self._assert_event_types(batch, DialogEventType.UNHANDLED_MESSAGE_RECEIVED)
        self.assertEqual(batch.events[0].message, "BLABLABLA")

    def test_thank_you_received(self):
        self.dialog_state.user_profile.validated = True
        self.dialog_state.user_profile.account_info = AccountInfo(employer_id=1)
        command = ProcessSMSMessage(self.phone_number, "Thanks!!")
        batch = self._process_command(command)
        self._assert_event_types(batch, DialogEventType.THANK_YOU_RECEIVED)

    def test_demo_requested(self):
        command = ProcessSMSMessage(self.phone_number, "OPUS")
        batch = self._process_command(command)
        self._assert_event_types(batch, DialogEventType.DEMO_REQUESTED)

    def test_update_user(self):
        name = "foo"
        unit_id = 123
        employer_id = 456
        user_profile_data = {
            "name": name,
            "account_info": {"unit_id": unit_id, "employer_id": employer_id},
        }
        command = UpdateUser(self.phone_number, user_profile_data)

        batch = self._process_command(command)

        self._assert_event_types(batch, DialogEventType.USER_UPDATED)
        self.assertEqual(self.dialog_state.user_profile.name, name)
        self.assertEqual(self.dialog_state.user_profile.account_info.unit_id, unit_id)
        self.assertEqual(self.dialog_state.user_profile.account_info.employer_id, employer_id)
