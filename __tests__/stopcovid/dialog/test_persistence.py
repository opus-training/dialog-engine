import unittest
import uuid

from stopcovid.dialog.models.events import (
    CompletedPrompt,
    AdvancedToNextPrompt,
    DialogEventBatch,
)
from stopcovid.dialog.persistence import DynamoDBDialogRepository
from stopcovid.dialog.models.state import DialogState, UserProfile
from stopcovid.drills.drills import Prompt, PromptMessage


class TestPersistence(unittest.TestCase):
    """
    requires local dynamoDB to be running: docker-compose up in the dynamodb_local directory
    """

    def setUp(self):
        self.repo = DynamoDBDialogRepository(
            region_name="us-west-2",
            endpoint_url="http://localhost:9000",
            aws_access_key_id="fake-key",
            aws_secret_access_key="fake-secret",
        )
        self.repo.ensure_tables_exist()
        self.phone_number = "123456789"

    def test_save_and_fetch(self):
        dialog_state = self.repo.fetch_dialog_state(self.phone_number)
        self.assertEqual(self.phone_number, dialog_state.phone_number)

        event1 = CompletedPrompt(
            phone_number=self.phone_number,
            user_profile=UserProfile(True),
            prompt=Prompt(
                slug="one", messages=[PromptMessage(text="one"), PromptMessage(text="two")],
            ),
            response="hi",
            drill_instance_id=uuid.uuid4(),
        )
        event2 = AdvancedToNextPrompt(
            phone_number=self.phone_number,
            user_profile=UserProfile(True),
            prompt=Prompt(
                slug="two", messages=[PromptMessage(text="three"), PromptMessage(text="four")],
            ),
            drill_instance_id=event1.drill_instance_id,
        )
        dialog_state = DialogState(
            phone_number=self.phone_number,
            seq="0",
            user_profile=UserProfile(validated=True, language="de"),
            drill_instance_id=event1.drill_instance_id,
        )
        batch = DialogEventBatch(phone_number=self.phone_number, events=[event1, event2], seq="216")

        self.repo.persist_dialog_state(batch, dialog_state)
        dialog_state2 = self.repo.fetch_dialog_state(self.phone_number)
        self.assertEqual(dialog_state.phone_number, dialog_state2.phone_number)
        self.assertEqual(dialog_state.user_profile.validated, dialog_state2.user_profile.validated)
        self.assertEqual(dialog_state.user_profile.language, dialog_state2.user_profile.language)

        batch_retrieved = self.repo.fetch_dialog_event_batch(self.phone_number, batch.batch_id)

        event1_retrieved = batch_retrieved.events[0]
        self.assertEqual(event1.response, event1_retrieved.response)  # type: ignore

        event2_retrieved = batch_retrieved.events[1]
        self.assertEqual(event2.prompt.slug, event2_retrieved.prompt.slug)  # type: ignore
