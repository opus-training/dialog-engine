import logging
import unittest
from uuid import uuid4

from stopcovid.dialog.models.events import (
    DrillStarted,
    UserValidated,
    NextDrillRequested,
    DialogEventBatch,
    DrillCompleted,
)
from stopcovid.dialog.registration import CodeValidationPayload
from stopcovid.dialog.models.state import UserProfile, DialogState
from stopcovid.dialog.persistence import DialogRepository
from stopcovid.drills.drills import get_drill
from stopcovid.drill_progress.status import (
    initiates_first_drill,
    initiates_subsequent_drill,
)

CONTINUE_PHONE = "123456789"
REGULAR_PHONE = "987654321"


class TestDialogRepository(DialogRepository):
    def persist_dialog_state(self, event_batch: DialogEventBatch, dialog_state: DialogState):
        pass

    def fetch_dialog_state(self, phone_number: str) -> DialogState:
        if phone_number == CONTINUE_PHONE:
            current_drill = get_drill("00-intake")
        else:
            current_drill = get_drill("01-sample-drill")

        return DialogState(current_drill=current_drill, phone_number=phone_number, seq="0")


class TestStatus(unittest.TestCase):
    def setUp(self) -> None:
        logging.disable(logging.CRITICAL)
        self.phone_number = "123456789"
        self.first_drill = get_drill("01-sample-drill")
        self.intake_drill = get_drill("00-intake")
        self.repo = TestDialogRepository()

    def test_initiates_first_drill(self):
        batch1 = DialogEventBatch(
            phone_number="123456789",
            seq="0",
            events=[
                UserValidated(
                    phone_number="123456789",
                    user_profile=UserProfile(True),
                    code_validation_payload=CodeValidationPayload(valid=True),
                ),
                DrillStarted(
                    phone_number="123456789",
                    user_profile=UserProfile(True),
                    drill=self.first_drill,
                    first_prompt=self.first_drill.prompts[0],
                ),
            ],
        )
        batch2 = DialogEventBatch(
            phone_number="123456789",
            seq="1",
            events=[
                DrillStarted(
                    phone_number="123456789",
                    user_profile=UserProfile(True),
                    drill=self.first_drill,
                    first_prompt=self.first_drill.prompts[0],
                )
            ],
        )
        self.assertTrue(initiates_first_drill(batch1))
        self.assertFalse(initiates_first_drill(batch2))

    def test_initiates_subsequent_drill(self):
        batch1 = DialogEventBatch(
            phone_number="123456789",
            seq="0",
            events=[
                NextDrillRequested(
                    phone_number="123456789",
                    user_profile=UserProfile(True),
                    code_validation_payload=CodeValidationPayload(valid=True),
                ),
                DrillStarted(
                    phone_number="123456789",
                    user_profile=UserProfile(True),
                    drill=self.first_drill,
                    first_prompt=self.first_drill.prompts[0],
                ),
            ],
        )
        batch2 = DialogEventBatch(
            phone_number="987654321",
            seq="1",
            events=[
                DrillStarted(
                    phone_number="987654321",
                    user_profile=UserProfile(True),
                    drill=self.first_drill,
                    first_prompt=self.first_drill.prompts[0],
                )
            ],
        )
        self.assertTrue(initiates_subsequent_drill(batch1, self.repo))
        self.assertFalse(initiates_subsequent_drill(batch2, self.repo))

    def test_autocontinue_next_drill(self):
        batch1 = DialogEventBatch(
            phone_number=CONTINUE_PHONE,
            seq="0",
            events=[
                DrillCompleted(
                    drill_instance_id=uuid4(),
                    phone_number=CONTINUE_PHONE,
                    user_profile=UserProfile(True),
                )
            ],
        )
        batch2 = DialogEventBatch(
            phone_number=REGULAR_PHONE,
            seq="0",
            events=[
                DrillCompleted(
                    drill_instance_id=uuid4(),
                    phone_number=REGULAR_PHONE,
                    user_profile=UserProfile(True),
                )
            ],
        )
        batch3 = DialogEventBatch(
            phone_number=REGULAR_PHONE,
            seq="1",
            events=[
                DrillStarted(
                    phone_number=REGULAR_PHONE,
                    user_profile=UserProfile(True),
                    drill=self.intake_drill,
                    first_prompt=self.intake_drill.prompts[0],
                )
            ],
        )
        self.assertTrue(initiates_subsequent_drill(batch1, self.repo))
        self.assertFalse(initiates_subsequent_drill(batch2, self.repo))
        self.assertFalse(initiates_subsequent_drill(batch3, self.repo))
