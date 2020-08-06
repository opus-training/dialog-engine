from datetime import datetime
import enum
import uuid
from abc import abstractmethod
from typing import Optional, Dict, Type, Any, List

import pydantic
from pytz import UTC

from stopcovid.dialog.registration import (
    CodeValidationPayload,
)
from stopcovid.dialog.models.state import (
    DialogState,
    UserProfile,
    PromptState,
)
from stopcovid.dialog.models import SCHEMA_VERSION
from stopcovid.drills import drills
from stopcovid.sms.types import SMS


class DialogEventType(enum.Enum):
    DRILL_STARTED = "DRILL_STARTED"
    USER_VALIDATED = "USER_VALIDATED"
    USER_VALIDATION_FAILED = "USER_VALIDATION_FAILED"
    COMPLETED_PROMPT = "COMPLETED_PROMPT"
    FAILED_PROMPT = "FAILED_PROMPT"
    ADVANCED_TO_NEXT_PROMPT = "ADVANCED_TO_NEXT_PROMPT"
    DRILL_COMPLETED = "DRILL_COMPLETED"
    NEXT_DRILL_REQUESTED = "NEXT_DRILL_REQUESTED"
    OPTED_OUT = "OPTED_OUT"
    SCHEDULING_DRILL_REQUESTED = "SCHEDULING_DRILL_REQUESTED"
    NAME_CHANGE_DRILL_REQUESTED = "NAME_CHANGE_DRILL_REQUESTED"
    LANGUAGE_CHANGE_DRILL_REQUESTED = "LANGUAGE_CHANGE_DRILL_REQUESTED"
    MENU_REQUESTED = "MENU_REQUESTED"
    AD_HOC_MESSAGE_SENT = "AD_HOC_MESSAGE_SENT"
    UNHANDLED_MESSAGE_RECEIVED = "UNHANDLED_MESSAGE_RECEIVED"
    SUPPORT_REQUESTED = "SUPPORT_REQUESTED"


class DialogEvent(pydantic.BaseModel):
    phone_number: str
    event_type: DialogEventType
    user_profile: UserProfile
    created_time: datetime = pydantic.Field(default_factory=lambda: datetime.now(UTC))
    event_id: uuid.UUID = pydantic.Field(default_factory=uuid.uuid4)
    schema_version: int = SCHEMA_VERSION

    @abstractmethod
    def apply_to(self, dialog_state: DialogState):
        pass


class DrillStarted(DialogEvent):
    event_type = DialogEventType.DRILL_STARTED
    drill: drills.Drill
    first_prompt: drills.Prompt
    drill_instance_id: uuid.UUID = pydantic.Field(default_factory=uuid.uuid4)

    def apply_to(self, dialog_state: DialogState):
        dialog_state.current_drill = self.drill
        dialog_state.drill_instance_id = self.drill_instance_id
        dialog_state.current_prompt_state = PromptState(
            slug=self.first_prompt.slug, start_time=self.created_time
        )


class AdHocMessageSent(DialogEvent):
    event_type = DialogEventType.AD_HOC_MESSAGE_SENT
    sms: SMS

    def apply_to(self, dialog_state: DialogState):
        pass


class UserValidated(DialogEvent):
    event_type = DialogEventType.USER_VALIDATED
    code_validation_payload: CodeValidationPayload

    def apply_to(self, dialog_state: DialogState):
        dialog_state.drill_instance_id = None
        dialog_state.current_prompt_state = None
        dialog_state.current_drill = None
        dialog_state.user_profile.validated = True
        dialog_state.user_profile.is_demo = self.code_validation_payload.is_demo
        dialog_state.user_profile.account_info = self.code_validation_payload.account_info.dict()


class UserValidationFailed(DialogEvent):
    event_type = DialogEventType.USER_VALIDATION_FAILED

    def apply_to(self, dialog_state: DialogState):
        pass


class CompletedPrompt(DialogEvent):
    event_type = DialogEventType.COMPLETED_PROMPT
    prompt: drills.Prompt
    response: str
    drill_instance_id: uuid.UUID

    def apply_to(self, dialog_state: DialogState):
        dialog_state.current_prompt_state = None
        if self.prompt.response_user_profile_key:
            setattr(
                dialog_state.user_profile, self.prompt.response_user_profile_key, self.response,
            )


class FailedPrompt(DialogEvent):
    event_type = DialogEventType.FAILED_PROMPT
    prompt: drills.Prompt
    abandoned: bool
    response: Optional[str]
    drill_instance_id: uuid.UUID

    def apply_to(self, dialog_state: DialogState):
        if self.abandoned:
            dialog_state.current_prompt_state = None
        else:
            dialog_state.current_prompt_state.last_response_time = self.created_time
            dialog_state.current_prompt_state.failures += 1


class AdvancedToNextPrompt(DialogEvent):
    event_type = DialogEventType.ADVANCED_TO_NEXT_PROMPT
    prompt: drills.Prompt
    drill_instance_id: uuid.UUID

    def apply_to(self, dialog_state: DialogState):
        dialog_state.current_prompt_state = PromptState(
            slug=self.prompt.slug, start_time=self.created_time
        )


class DrillCompleted(DialogEvent):
    event_type = DialogEventType.DRILL_COMPLETED
    drill_instance_id: uuid.UUID
    auto_continue: bool = False

    def apply_to(self, dialog_state: DialogState):
        dialog_state.current_drill = None
        dialog_state.drill_instance_id = None
        dialog_state.current_prompt_state = None


class OptedOut(DialogEvent):
    event_type = DialogEventType.OPTED_OUT
    drill_instance_id: Optional[uuid.UUID]

    def apply_to(self, dialog_state: DialogState):
        dialog_state.drill_instance_id = None
        dialog_state.user_profile.opted_out = True
        dialog_state.current_drill = None
        dialog_state.current_prompt_state = None


class NextDrillRequested(DialogEvent):
    event_type = DialogEventType.NEXT_DRILL_REQUESTED

    def apply_to(self, dialog_state: DialogState):
        dialog_state.user_profile.opted_out = False


class SchedulingDrillRequested(DialogEvent):
    event_type = DialogEventType.SCHEDULING_DRILL_REQUESTED
    abandoned_drill_instance_id: Optional[uuid.UUID] = None

    def apply_to(self, dialog_state: DialogState):
        dialog_state.current_drill = None
        dialog_state.drill_instance_id = None
        dialog_state.current_prompt_state = None
        dialog_state.user_profile.opted_out = False


class NameChangeDrillRequested(DialogEvent):
    event_type = DialogEventType.NAME_CHANGE_DRILL_REQUESTED
    abandoned_drill_instance_id: Optional[uuid.UUID] = None

    def apply_to(self, dialog_state: DialogState):
        dialog_state.current_drill = None
        dialog_state.drill_instance_id = None
        dialog_state.current_prompt_state = None
        dialog_state.user_profile.opted_out = False


class LanguageChangeDrillRequested(DialogEvent):
    event_type = DialogEventType.LANGUAGE_CHANGE_DRILL_REQUESTED
    abandoned_drill_instance_id: Optional[uuid.UUID] = None

    def apply_to(self, dialog_state: DialogState):
        dialog_state.current_drill = None
        dialog_state.drill_instance_id = None
        dialog_state.current_prompt_state = None
        dialog_state.user_profile.opted_out = False


class SupportRequested(DialogEvent):
    event_type = DialogEventType.SUPPORT_REQUESTED
    abandoned_drill_instance_id: Optional[uuid.UUID] = None

    def apply_to(self, dialog_state: DialogState):
        dialog_state.current_drill = None
        dialog_state.drill_instance_id = None
        dialog_state.current_prompt_state = None
        dialog_state.user_profile.opted_out = False


class UnhandledMessageReceived(DialogEvent):
    event_type = DialogEventType.UNHANDLED_MESSAGE_RECEIVED
    message: str = "None"

    def apply_to(self, dialog_state: DialogState):
        pass


class MenuRequested(DialogEvent):
    event_type = DialogEventType.MENU_REQUESTED
    abandoned_drill_instance_id: Optional[uuid.UUID] = None

    def apply_to(self, dialog_state: DialogState):
        dialog_state.current_drill = None
        dialog_state.drill_instance_id = None
        dialog_state.current_prompt_state = None
        dialog_state.user_profile.opted_out = False


TYPE_TO_SCHEMA: Dict[DialogEventType, Type[DialogEvent]] = {
    DialogEventType.ADVANCED_TO_NEXT_PROMPT: AdvancedToNextPrompt,
    DialogEventType.DRILL_COMPLETED: DrillCompleted,
    DialogEventType.USER_VALIDATION_FAILED: UserValidationFailed,
    DialogEventType.DRILL_STARTED: DrillStarted,
    DialogEventType.USER_VALIDATED: UserValidated,
    DialogEventType.COMPLETED_PROMPT: CompletedPrompt,
    DialogEventType.FAILED_PROMPT: FailedPrompt,
    DialogEventType.OPTED_OUT: OptedOut,
    DialogEventType.NEXT_DRILL_REQUESTED: NextDrillRequested,
    DialogEventType.SCHEDULING_DRILL_REQUESTED: SchedulingDrillRequested,
    DialogEventType.AD_HOC_MESSAGE_SENT: AdHocMessageSent,
    DialogEventType.NAME_CHANGE_DRILL_REQUESTED: NameChangeDrillRequested,
    DialogEventType.LANGUAGE_CHANGE_DRILL_REQUESTED: LanguageChangeDrillRequested,
    DialogEventType.MENU_REQUESTED: MenuRequested,
    DialogEventType.UNHANDLED_MESSAGE_RECEIVED: UnhandledMessageReceived,
    DialogEventType.SUPPORT_REQUESTED: SupportRequested,
}


def event_from_dict(event_dict: Dict[str, Any]) -> DialogEvent:
    event_type = DialogEventType[event_dict["event_type"]]
    return TYPE_TO_SCHEMA[event_type](**event_dict)


class DialogEventBatch(pydantic.BaseModel):
    events: List[DialogEvent]
    phone_number: str
    seq: str
    batch_id: uuid.UUID = pydantic.Field(default_factory=uuid.uuid4)
    created_time: datetime = pydantic.Field(default_factory=lambda: datetime.now(UTC))

    def to_dict(self):
        return {
            "batch_id": str(self.batch_id),
            "seq": self.seq,
            "phone_number": self.phone_number,
            "created_time": self.created_time.isoformat(),
            "events": [event.dict() for event in self.events],
        }


def batch_from_dict(batch_dict: Dict[str, Any]) -> DialogEventBatch:
    events = batch_dict.pop("events") if "events" in batch_dict else []
    return DialogEventBatch(
        events=[event_from_dict(event_dict) for event_dict in events], **batch_dict
    )
