# -*- coding: utf-8 -*-
import json
import sys
from time import sleep
from typing import List, Dict, Optional
import uuid

from stopcovid.dialog.persistence import DialogRepository
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
    DialogEventBatch,
)
from stopcovid.dialog.engine import process_command, StartDrill, ProcessSMSMessage
from stopcovid.dialog.registration import RegistrationValidator, CodeValidationPayload, AccountInfo
from stopcovid.dialog.models.state import DialogState, UserProfile
from stopcovid.drills.content_loader import SourceRepoDrillLoader, translate, SupportedTranslation

SEQ = 1
PHONE_NUMBER = "123456789"
DRILLS = SourceRepoDrillLoader().get_drills()


STARTED_DRILLS: Dict[uuid.UUID, str] = {}


def fake_sms(
    phone_number: str,
    user_profile: UserProfile,
    messages: List[str],
    with_initial_pause: bool = False,
) -> None:
    first = True
    for message in messages:
        if with_initial_pause or not first:
            sleep(1)
        print(f"  -> {phone_number}: {message}")
        first = False


class InMemoryRepository(DialogRepository):
    def __init__(self, lang: str) -> None:
        self.repo: dict = {}
        self.lang = lang

    def fetch_dialog_state(self, phone_number: str) -> DialogState:
        if phone_number in self.repo:
            state = DialogState(**json.loads(self.repo[phone_number]))
            return state
        else:
            return DialogState(
                phone_number=phone_number,
                seq="0",
                user_profile=UserProfile(validated=False, language=self.lang),
            )

    def get_next_unstarted_drill(self) -> Optional[str]:
        state = self.fetch_dialog_state(PHONE_NUMBER)
        assert state.user_profile
        language = state.user_profile.language
        assert language
        unstarted_drills = [
            code
            for code in DRILLS.keys()
            if DRILLS[code].slug not in STARTED_DRILLS.values()
            and DRILLS[code].slug.endswith(language)
        ]
        if unstarted_drills:
            return unstarted_drills[0]
        return None

    def persist_dialog_state(  # noqa: C901
        self, event_batch: DialogEventBatch, dialog_state: DialogState
    ) -> None:
        self.repo[dialog_state.phone_number] = dialog_state.json()
        assert dialog_state.user_profile.language
        drill_to_start = None
        print(event_batch.user_profile)
        for event in event_batch.events:
            if isinstance(event, AdvancedToNextPrompt):
                fake_sms(
                    event.phone_number,
                    dialog_state.user_profile,
                    [message.text for message in event.prompt.messages if message.text is not None],
                    with_initial_pause=True,
                )
            elif isinstance(event, FailedPrompt):
                if not event.abandoned:
                    fake_sms(
                        event.phone_number,
                        dialog_state.user_profile,
                        [
                            translate(
                                dialog_state.user_profile.language,
                                SupportedTranslation.INCORRECT_ANSWER,
                            )
                        ],
                    )
                else:
                    fake_sms(
                        event.phone_number,
                        dialog_state.user_profile,
                        [
                            translate(
                                dialog_state.user_profile.language,
                                SupportedTranslation.CORRECTED_ANSWER,
                                correct_answer=event.prompt.correct_response,
                            )
                        ],
                    )
            elif isinstance(event, CompletedPrompt):
                if event.prompt.correct_response is not None:
                    fake_sms(
                        event.phone_number,
                        dialog_state.user_profile,
                        [
                            translate(
                                dialog_state.user_profile.language,
                                SupportedTranslation.MATCH_CORRECT_ANSWER,
                            )
                        ],
                    )
            elif isinstance(event, UserValidated):
                assert dialog_state.user_profile.account_info
                drill_to_start = dialog_state.user_profile.account_info.employer_name
            elif isinstance(event, OptedOut):
                print("(You've been opted out.)")
                if event.drill_instance_id:
                    del STARTED_DRILLS[event.drill_instance_id]
            elif isinstance(event, NextDrillRequested):
                drill_to_start = self.get_next_unstarted_drill()
                if not drill_to_start:
                    print("(You're all out of drills.)")
            elif isinstance(event, UserValidationFailed):
                print(f"(try {', '.join(DRILLS.keys())})")
            elif isinstance(event, DrillStarted):
                assert dialog_state.current_drill
                STARTED_DRILLS[event.drill_instance_id] = dialog_state.current_drill.slug
                fake_sms(
                    event.phone_number,
                    dialog_state.user_profile,
                    [
                        message.text
                        for message in event.first_prompt.messages
                        if message.text is not None
                    ],
                )
            elif isinstance(event, DrillCompleted):
                print("(The drill is complete. Type 'more' for another drill or crtl-D to exit.)")
            elif isinstance(event, SchedulingDrillRequested):
                print("Scheduling drill requested")
        if drill_to_start:
            global SEQ
            SEQ += 1
            drill = DRILLS[drill_to_start]
            process_command(
                StartDrill(PHONE_NUMBER, drill.slug, drill.dict(), uuid.uuid4()),
                str(SEQ),
                repo=self,
            )


class FakeRegistrationValidator(RegistrationValidator):
    def validate_code(self, code: str) -> CodeValidationPayload:
        if code in DRILLS.keys():
            return CodeValidationPayload(
                valid=True,
                account_info=AccountInfo(
                    employer_id=1,
                    employer_name=code,
                    unit_id=1,
                    unit_name="unit_name",
                ),
            )
        return CodeValidationPayload(valid=False)


def main() -> None:
    global SEQ
    if len(sys.argv) > 1:
        lang = sys.argv[1]
    else:
        lang = "en"
    repo = InMemoryRepository(lang)
    validator = FakeRegistrationValidator()

    # kick off the language choice drill
    process_command(
        ProcessSMSMessage(PHONE_NUMBER, "00-language", registration_validator=validator),
        "1",
        repo=repo,
    )
    try:
        while True:
            message = input("> ")
            SEQ += 1
            process_command(
                ProcessSMSMessage(PHONE_NUMBER, message, registration_validator=validator),
                str(SEQ),
                repo=repo,
            )
    except EOFError:
        pass
    dialog_state = repo.fetch_dialog_state(PHONE_NUMBER)
    print(f"{dialog_state.user_profile}")


if __name__ == "__main__":
    main()
