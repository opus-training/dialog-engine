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
from stopcovid.dialog.models.state import UserProfile
from stopcovid.drills.drills import get_drill
from stopcovid.drill_progress.status import (
    initiates_first_drill,
    initiates_subsequent_drill,
)


class TestStatus(unittest.TestCase):
    def setUp(self) -> None:
        logging.disable(logging.CRITICAL)
        self.phone_number = "123456789"
        self.first_drill = get_drill("01-sample-drill")
        self.intake_drill = get_drill("00-intake")

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
        self.assertTrue(initiates_subsequent_drill(batch1))
        self.assertFalse(initiates_subsequent_drill(batch2))

    def test_autocontinue_next_drill(self):
        batch1 = DialogEventBatch(
            phone_number="123456789",
            seq="0",
            events=[
                DrillCompleted(
                    drill_instance_id=uuid4(),
                    phone_number="123456789",
                    user_profile=UserProfile(True),
                    auto_continue=True,
                )
            ],
        )
        batch2 = DialogEventBatch(
            phone_number="987654321",
            seq="0",
            events=[
                DrillCompleted(
                    drill_instance_id=uuid4(),
                    phone_number="987654321",
                    user_profile=UserProfile(True),
                    auto_continue=False,
                )
            ],
        )
        batch3 = DialogEventBatch(
            phone_number="987654321",
            seq="1",
            events=[
                DrillStarted(
                    phone_number="987654321",
                    user_profile=UserProfile(True),
                    drill=self.intake_drill,
                    first_prompt=self.intake_drill.prompts[0],
                )
            ],
        )
        self.assertTrue(initiates_subsequent_drill(batch1))
        self.assertFalse(initiates_subsequent_drill(batch2))
        self.assertFalse(initiates_subsequent_drill(batch3))
