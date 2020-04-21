from typing import List

from .initiation import DrillInitiator
from ..drills.drills import Drill
from .drill_progress import DrillProgressRepository
from ..dialog.persistence import DynamoDBDialogRepository
from ..dialog.models.events import (
    UserValidated,
    NextDrillRequested,
    DialogEventBatch,
    DrillCompleted,
    DialogState,
)


def handle_dialog_event_batches(batches: List[DialogEventBatch]):
    # trigger initiation before updating status. The status updates could be slow because of
    # aurora cold start time.
    initiator = DrillInitiator()
    for batch in batches:
        if initiates_first_drill(batch):
            initiator.trigger_first_drill(batch.phone_number, str(batch.batch_id))

    user_repo = DrillProgressRepository()
    state_repo = DynamoDBDialogRepository()
    for batch in batches:
        user_repo.update_user(batch)
        dialog_state = state_repo.fetch_dialog_state(batch.phone_number)
        if initiates_subsequent_drill(batch, dialog_state):
            initiator.trigger_next_drill_for_user(batch.phone_number, str(batch.batch_id))


def initiates_first_drill(batch: DialogEventBatch):
    return any(event for event in batch.events if isinstance(event, UserValidated))


def initiates_subsequent_drill(batch: DialogEventBatch, dialog_state: DialogState):
    for event in batch.events:
        if isinstance(event, NextDrillRequested):
            return True
        elif isinstance(event, DrillCompleted):
            current_drill = dialog_state.current_drill
            if isinstance(current_drill, Drill) and current_drill.auto_continue:
                return True
