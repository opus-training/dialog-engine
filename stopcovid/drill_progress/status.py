from typing import List

from .initiation import DrillInitiator
from .drill_progress import DrillProgressRepository
from ..dialog.models.events import UserValidated, NextDrillRequested, DialogEventBatch


def handle_dialog_event_batches(batches: List[DialogEventBatch]):
    # trigger initiation before updating status. The status updates could be slow because of
    # aurora cold start time.
    initiator = DrillInitiator()
    for batch in batches:
        if initiates_first_drill(batch):
            initiator.trigger_first_drill(batch.phone_number, str(batch.batch_id))

    user_repo = DrillProgressRepository()
    for batch in batches:
        user_repo.update_user(batch)
        if initiates_subsequent_drill(batch):
            initiator.trigger_next_drill_for_user(batch.phone_number, str(batch.batch_id))


def initiates_first_drill(batch: DialogEventBatch):
    return any(event for event in batch.events if isinstance(event, UserValidated))


def initiates_subsequent_drill(batch: DialogEventBatch):
    return any(event for event in batch.events if isinstance(event, NextDrillRequested))
