import logging
from abc import ABC, abstractmethod
from copy import deepcopy
from typing import List, Optional, Dict, Any

import stopcovid.dialog.models.events
from stopcovid.dialog.models.events import (
    DrillStarted,
    UserValidated,
    UserValidationFailed,
    CompletedPrompt,
    FailedPrompt,
    AdvancedToNextPrompt,
    DrillCompleted,
    OptedOut,
    NextDrillRequested,
    SchedulingDrillRequested,
    AdHocMessageSent,
    DialogEvent,
    DialogEventBatch,
    NameChangeDrillRequested,
    LanguageChangeDrillRequested,
    MenuRequested,
    UnhandledMessageReceived,
    SupportRequested,
)
from stopcovid.dialog.persistence import DialogRepository, DynamoDBDialogRepository
from stopcovid.dialog.registration import (
    RegistrationValidator,
    DefaultRegistrationValidator,
)
from stopcovid.dialog.models.state import DialogState
from stopcovid.drills.drills import Drill
from stopcovid.sms.types import SMS

DEFAULT_REGISTRATION_VALIDATOR = DefaultRegistrationValidator()


class Command(ABC):
    def __init__(self, phone_number: str):
        self.phone_number = phone_number

    @abstractmethod
    def execute(self, dialog_state: DialogState) -> List[DialogEvent]:
        pass


def process_command(command: Command, seq: str, repo: DialogRepository = None):
    if repo is None:
        repo = DynamoDBDialogRepository()
    dialog_state = repo.fetch_dialog_state(command.phone_number)
    command_seq = int(seq)
    state_seq = int(dialog_state.seq)
    if command_seq <= state_seq:
        logging.info(
            f"({command.phone_number}) Processing already processed command {seq}. Current "
            f"dialog state has sequence {dialog_state.seq}."
        )
        return

    logging.info(
        f"({command.phone_number}) Processing command {command}. " f"Current state: {dialog_state}."
    )

    events = command.execute(dialog_state)
    event_types = ", ".join(f"{event.event_type}" for event in events)
    logging.info(f"({command.phone_number}) Applying events: {event_types}")
    for event in events:
        # deep copying the event so that modifications to the dialog_state don't have
        # side effects on the events that we're persisting. The user_profile on the event
        # should reflect the user_profile *before* the event is applied to the dialog_state.
        deepcopy(event).apply_to(dialog_state)
    dialog_state.seq = seq
    repo.persist_dialog_state(
        DialogEventBatch(events=events, phone_number=command.phone_number, seq=seq), dialog_state,
    )


class StartDrill(Command):
    def __init__(self, phone_number: str, drill_slug: str, drill_body: dict):
        super().__init__(phone_number)
        self.drill_slug = drill_slug
        self.drill = Drill(**drill_body)

    def __str__(self):
        return f"Start Drill: {self.drill_slug}"

    def execute(
        self, dialog_state: DialogState
    ) -> List[stopcovid.dialog.models.events.DialogEvent]:
        if dialog_state.user_profile.opted_out or not dialog_state.user_profile.validated:
            logging.warning(
                f"Attempted to initiate a drill for {dialog_state.phone_number}, "
                f"who hasn't validated or has opted out."
            )
            return []
        return [
            DrillStarted(
                phone_number=self.phone_number,
                user_profile=dialog_state.user_profile,
                drill=self.drill,
                first_prompt=self.drill.first_prompt(),
            )
        ]


class ProcessSMSMessage(Command):
    def __init__(
        self,
        phone_number: str,
        content: str,
        registration_validator: Optional[RegistrationValidator] = None,
    ):
        super().__init__(phone_number)
        self.content = content.strip()
        self.content_lower = self.content.lower()
        if registration_validator is None:
            registration_validator = DEFAULT_REGISTRATION_VALIDATOR
        self.registration_validator = registration_validator

    def __str__(self):
        return f"Process SMS: '{self.content}'"

    def execute(
        self, dialog_state: DialogState
    ) -> List[stopcovid.dialog.models.events.DialogEvent]:
        base_args = {
            "phone_number": self.phone_number,
            "user_profile": dialog_state.user_profile,
        }

        # a chain of responsibility. Each handler can handle the current command and return an
        # event list. A handler can also NOT handle an event and return None, thereby leaving it
        # for the next handler.
        for handler in [
            self._respond_to_help,
            self._menu_requested,
            self._support_requested,
            self._name_change_drill_requested,
            self._language_change_drill_requested,
            self._update_schedule_requested,
            self._handle_opt_out,
            self._handle_opt_back_in,
            self._validate_registration,
            self._check_response,
            self._advance_to_next_drill,
            self._unhandled_message,
        ]:
            result = handler(dialog_state, base_args)
            if result is not None:
                return result
        return []

    def _respond_to_help(
        self, dialog_state: DialogState, base_args: Dict[str, Any]
    ) -> Optional[List[stopcovid.dialog.models.events.DialogEvent]]:
        if self.content_lower == "help":
            # Twilio will respond with help text
            return []
        return None

    def _handle_opt_out(
        self, dialog_state: DialogState, base_args: Dict[str, Any]
    ) -> Optional[List[stopcovid.dialog.models.events.DialogEvent]]:
        if self.content_lower == "stop":
            return [OptedOut(drill_instance_id=dialog_state.drill_instance_id, **base_args)]
        return None

    def _handle_opt_back_in(
        self, dialog_state: DialogState, base_args: Dict[str, Any]
    ) -> Optional[List[stopcovid.dialog.models.events.DialogEvent]]:
        if dialog_state.user_profile.opted_out:
            if self.content_lower in ["start", "unstop", "go"]:
                return [NextDrillRequested(**base_args)]
            return []
        return None

    def _validate_registration(
        self, dialog_state: DialogState, base_args: Dict[str, Any]
    ) -> Optional[List[stopcovid.dialog.models.events.DialogEvent]]:

        if dialog_state.user_profile.is_demo or not dialog_state.user_profile.validated:
            validation_payload = self.registration_validator.validate_code(self.content_lower)
            if validation_payload.valid:
                return [UserValidated(code_validation_payload=validation_payload, **base_args)]
            if not dialog_state.user_profile.validated:
                return [UserValidationFailed(**base_args)]
        return None

    def _get_drill_completed_event(
        self, dialog_state: DialogState, base_args: Dict[str, Any]
    ) -> DrillCompleted:
        auto_continue = None
        if isinstance(dialog_state.current_drill, Drill):
            auto_continue = dialog_state.current_drill.auto_continue

        return DrillCompleted(
            drill_instance_id=dialog_state.drill_instance_id,
            auto_continue=auto_continue,
            **base_args,
        )

    def _check_response(
        self, dialog_state: DialogState, base_args: Dict[str, Any]
    ) -> Optional[List[stopcovid.dialog.models.events.DialogEvent]]:
        prompt = dialog_state.get_prompt()
        if prompt is None:
            return None
        events: List[DialogEvent] = []
        if prompt.should_advance_with_answer(self.content_lower):
            events.append(
                CompletedPrompt(
                    prompt=prompt,
                    drill_instance_id=dialog_state.drill_instance_id,
                    response=self.content,
                    **base_args,
                )
            )
            should_advance = True
        else:
            should_advance = dialog_state.current_prompt_state.failures >= prompt.max_failures
            events.append(
                FailedPrompt(
                    prompt=prompt,
                    response=self.content or None,
                    drill_instance_id=dialog_state.drill_instance_id,
                    abandoned=should_advance,
                    **base_args,
                )
            )

        if should_advance:
            next_prompt = dialog_state.get_next_prompt()
            if next_prompt is not None:
                events.append(
                    AdvancedToNextPrompt(
                        prompt=next_prompt,
                        drill_instance_id=dialog_state.drill_instance_id,
                        **base_args,
                    )
                )
                if dialog_state.is_next_prompt_last():
                    # assume the last prompt doesn't wait for an answer
                    events.append(self._get_drill_completed_event(dialog_state, base_args))

            elif len(dialog_state.current_drill.prompts) == 1:
                events.append(self._get_drill_completed_event(dialog_state, base_args))

        return events

    def _advance_to_next_drill(
        self, dialog_state: DialogState, base_args: Dict[str, Any]
    ) -> Optional[List[stopcovid.dialog.models.events.DialogEvent]]:
        prompt = dialog_state.get_prompt()
        if prompt is None:
            if self.content_lower in ["more", "mas", "más"]:
                return [NextDrillRequested(**base_args)]
        return None

    def _update_schedule_requested(
        self, dialog_state: DialogState, base_args: Dict[str, Any]
    ) -> Optional[List[stopcovid.dialog.models.events.DialogEvent]]:
        if self.content_lower in ["schedule", "calendario", "horario"]:
            return [
                SchedulingDrillRequested(
                    **base_args, abandoned_drill_instance_id=dialog_state.drill_instance_id
                )
            ]
        return None

    def _name_change_drill_requested(self, dialog_state: DialogState, base_args: Dict[str, Any]):
        if self.content_lower in ["name", "nombre"]:
            return [
                NameChangeDrillRequested(
                    **base_args, abandoned_drill_instance_id=dialog_state.drill_instance_id
                )
            ]
        return None

    def _support_requested(self, dialog_state: DialogState, base_args: Dict[str, Any]):
        if self.content_lower in ["support", "ayuda"]:
            return [
                SupportRequested(
                    **base_args, abandoned_drill_instance_id=dialog_state.drill_instance_id
                )
            ]
        return None

    def _language_change_drill_requested(
        self, dialog_state: DialogState, base_args: Dict[str, Any]
    ):
        if self.content_lower in ["lang", "language", "idioma"]:
            return [
                LanguageChangeDrillRequested(
                    **base_args, abandoned_drill_instance_id=dialog_state.drill_instance_id
                )
            ]
        return None

    def _menu_requested(self, dialog_state: DialogState, base_args: Dict[str, Any]):
        if self.content_lower in ["menu", "menú"]:
            return [
                MenuRequested(
                    **base_args, abandoned_drill_instance_id=dialog_state.drill_instance_id
                )
            ]
        return None

    def _unhandled_message(self, dialog_state: DialogState, base_args: Dict[str, Any]):
        return [UnhandledMessageReceived(**base_args, message=self.content)]


class SendAdHocMessage(Command):
    def __init__(self, phone_number: str, message: str, media_url: Optional[str] = None):
        super().__init__(phone_number)
        self.sms = SMS(body=message, media_url=media_url)

    def execute(
        self, dialog_state: DialogState
    ) -> List[stopcovid.dialog.models.events.DialogEvent]:
        return [AdHocMessageSent(
            phone_number=self.phone_number,
            user_profile=dialog_state.user_profile,
            sms=self.sms)
        ]
