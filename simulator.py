# -*- coding: utf-8 -*-
import sys
from time import sleep
from typing import List

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
    DialogEventBatch,
)
from stopcovid.dialog.engine import process_command, StartDrill, ProcessSMSMessage
from stopcovid.dialog.registration import RegistrationValidator, CodeValidationPayload
from stopcovid.dialog.models.state import DialogStateSchema, DialogState, UserProfile
from stopcovid.drills.drills import get_drill, get_all_drill_slugs
from stopcovid.drills.localize import localize

SEQ = 1
TRY_AGAIN = "{{incorrect_answer}}"
PHONE_NUMBER = "123456789"
DRILLS = {slug: get_drill(slug) for slug in get_all_drill_slugs()}


STARTED_DRILLS = {}


def fake_sms(
    phone_number: str,
    user_profile: UserProfile,
    messages: List[str],
    with_initial_pause=False,
    **kwargs,
):
    additional_args = {
        "company": user_profile.account_info.get("company", "your company"),
        "name": "",
    }
    if user_profile.name is not None:
        additional_args["name"] = user_profile.name.split(" ")[0]
    additional_args.update(kwargs)

    first = True
    for message in messages:
        if with_initial_pause or not first:
            sleep(1)
        print(f"  -> {phone_number}: {localize(message, user_profile.language, **additional_args)}")
        first = False


class InMemoryRepository(DialogRepository):
    def __init__(self, lang):
        self.repo = {}
        self.lang = lang

    def fetch_dialog_state(self, phone_number: str) -> DialogState:
        if phone_number in self.repo:
            state = DialogStateSchema().loads(self.repo[phone_number])
            return state
        else:
            return DialogState(
                phone_number=phone_number,
                seq="0",
                user_profile=UserProfile(False, language=self.lang),
            )

    def persist_dialog_state(  # noqa: C901
        self, event_batch: DialogEventBatch, dialog_state: DialogState
    ):
        self.repo[dialog_state.phone_number] = DialogStateSchema().dumps(dialog_state)

        drill_to_start = None
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
                    fake_sms(event.phone_number, dialog_state.user_profile, [TRY_AGAIN])
                else:
                    fake_sms(
                        event.phone_number,
                        dialog_state.user_profile,
                        ["{{corrected_answer}}"],
                        correct_answer=localize(
                            event.prompt.correct_response,  # type: ignore
                            dialog_state.user_profile.language,
                        ),
                    )
            elif isinstance(event, CompletedPrompt):
                if event.prompt.correct_response is not None:
                    fake_sms(
                        event.phone_number, dialog_state.user_profile, ["{{match_correct_answer}}"]
                    )
            elif isinstance(event, UserValidated):
                drill_to_start = dialog_state.user_profile.account_info["code"]
            elif isinstance(event, OptedOut):
                print("(You've been opted out.)")
                if event.drill_instance_id:
                    del STARTED_DRILLS[event.drill_instance_id]
            elif isinstance(event, NextDrillRequested):
                unstarted_drills = [
                    code
                    for code in DRILLS.keys()
                    if DRILLS[code].slug not in STARTED_DRILLS.values()
                ]
                if unstarted_drills:
                    drill_to_start = unstarted_drills[0]
                else:
                    print("(You're all out of drills.)")
            elif isinstance(event, UserValidationFailed):
                print(f"(try {', '.join(DRILLS.keys())})")
            elif isinstance(event, DrillStarted):
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
        if drill_to_start:
            global SEQ
            SEQ += 1
            process_command(
                StartDrill(PHONE_NUMBER, DRILLS[drill_to_start].slug), str(SEQ), repo=self
            )


class FakeRegistrationValidator(RegistrationValidator):
    def validate_code(self, code) -> CodeValidationPayload:
        if code in DRILLS.keys():
            return CodeValidationPayload(valid=True, account_info={"code": code})
        return CodeValidationPayload(valid=False)


def main():
    global SEQ
    if len(sys.argv) > 1:
        lang = sys.argv[1]
    else:
        lang = "en"
    repo = InMemoryRepository(lang)
    validator = FakeRegistrationValidator()
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
