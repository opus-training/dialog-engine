from datetime import datetime
import enum
import uuid
from abc import abstractmethod
from typing import Optional, Dict, Type, Any, List

import pydantic
from pytz import UTC

from stopcovid.dialog.registration import CodeValidationPayload, AccountInfo
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
    DRILL_REQUESTED = "DRILL_REQUESTED"
    ENGLISH_LESSON_DRILL_REQUESTED = "ENGLISH_LESSON_DRILL_REQUESTED"
    NEXT_DRILL_REQUESTED = "NEXT_DRILL_REQUESTED"
    OPTED_OUT = "OPTED_OUT"
    SCHEDULING_DRILL_REQUESTED = "SCHEDULING_DRILL_REQUESTED"
    NAME_CHANGE_DRILL_REQUESTED = "NAME_CHANGE_DRILL_REQUESTED"
    LANGUAGE_CHANGE_DRILL_REQUESTED = "LANGUAGE_CHANGE_DRILL_REQUESTED"
    MENU_REQUESTED = "MENU_REQUESTED"
    AD_HOC_MESSAGE_SENT = "AD_HOC_MESSAGE_SENT"
    UNHANDLED_MESSAGE_RECEIVED = "UNHANDLED_MESSAGE_RECEIVED"
    SUPPORT_REQUESTED = "SUPPORT_REQUESTED"
    DASHBOARD_REQUESTED = "DASHBOARD_REQUESTED"
    USER_UPDATED = "USER_UPDATED"
    THANK_YOU_RECEIVED = "THANK_YOU_RECEIVED"
    DEMO_REQUESTED = "DEMO_REQUESTED"


class DialogEvent(pydantic.BaseModel):
    phone_number: str
    event_type: DialogEventType
    user_profile: UserProfile
    created_time: datetime = pydantic.Field(default_factory=lambda: datetime.now(UTC))
    event_id: uuid.UUID = pydantic.Field(default_factory=uuid.uuid4)
    schema_version: int = SCHEMA_VERSION
    user_profile_updates: Optional[Dict[str, str]] = None

    @abstractmethod
    def apply_to(self, dialog_state: DialogState) -> None:
        pass


class DrillStarted(DialogEvent):
    event_type: DialogEventType = DialogEventType.DRILL_STARTED
    drill: drills.Drill
    first_prompt: drills.Prompt
    drill_instance_id: uuid.UUID

    def apply_to(self, dialog_state: DialogState) -> None:
        dialog_state.current_drill = self.drill
        dialog_state.drill_instance_id = self.drill_instance_id
        dialog_state.current_prompt_state = PromptState(
            slug=self.first_prompt.slug, start_time=self.created_time
        )


class AdHocMessageSent(DialogEvent):
    event_type: DialogEventType = DialogEventType.AD_HOC_MESSAGE_SENT
    sms: SMS

    def apply_to(self, dialog_state: DialogState) -> None:
        pass


class UserValidated(DialogEvent):
    event_type: DialogEventType = DialogEventType.USER_VALIDATED
    code_validation_payload: CodeValidationPayload

    def apply_to(self, dialog_state: DialogState) -> None:
        dialog_state.drill_instance_id = None
        dialog_state.current_prompt_state = None
        dialog_state.current_drill = None
        dialog_state.user_profile.validated = True
        dialog_state.user_profile.is_demo = self.code_validation_payload.is_demo
        dialog_state.user_profile.account_info = self.code_validation_payload.account_info


class UserValidationFailed(DialogEvent):
    event_type: DialogEventType = DialogEventType.USER_VALIDATION_FAILED

    def apply_to(self, dialog_state: DialogState) -> None:
        pass


class CompletedPrompt(DialogEvent):
    event_type: DialogEventType = DialogEventType.COMPLETED_PROMPT
    prompt: drills.Prompt
    response: str
    drill_instance_id: uuid.UUID

    def apply_to(self, dialog_state: DialogState) -> None:
        dialog_state.current_prompt_state = None
        if self.prompt.response_user_profile_key:
            setattr(
                dialog_state.user_profile,
                self.prompt.response_user_profile_key,
                self.response,
            )


class FailedPrompt(DialogEvent):
    event_type: DialogEventType = DialogEventType.FAILED_PROMPT
    prompt: drills.Prompt
    abandoned: bool
    response: Optional[str]
    drill_instance_id: uuid.UUID

    def apply_to(self, dialog_state: DialogState) -> None:
        if self.abandoned:
            dialog_state.current_prompt_state = None
        else:
            assert dialog_state.current_prompt_state
            dialog_state.current_prompt_state.last_response_time = self.created_time
            dialog_state.current_prompt_state.failures += 1


class AdvancedToNextPrompt(DialogEvent):
    event_type: DialogEventType = DialogEventType.ADVANCED_TO_NEXT_PROMPT
    prompt: drills.Prompt
    drill_instance_id: uuid.UUID

    def apply_to(self, dialog_state: DialogState) -> None:
        dialog_state.current_prompt_state = PromptState(
            slug=self.prompt.slug, start_time=self.created_time
        )


class DrillCompleted(DialogEvent):
    event_type: DialogEventType = DialogEventType.DRILL_COMPLETED
    drill_instance_id: uuid.UUID
    last_prompt_response: Optional[str]

    def apply_to(self, dialog_state: DialogState) -> None:
        dialog_state.current_drill = None
        dialog_state.drill_instance_id = None
        dialog_state.current_prompt_state = None


class OptedOut(DialogEvent):
    event_type: DialogEventType = DialogEventType.OPTED_OUT
    drill_instance_id: Optional[uuid.UUID]

    def apply_to(self, dialog_state: DialogState) -> None:
        dialog_state.drill_instance_id = None
        dialog_state.user_profile.opted_out = True
        dialog_state.current_drill = None
        dialog_state.current_prompt_state = None


class DrillRequested(DialogEvent):
    event_type: DialogEventType = DialogEventType.DRILL_REQUESTED

    def apply_to(self, dialog_state: DialogState) -> None:
        pass


class EnglishLessonDrillRequested(DialogEvent):
    event_type: DialogEventType = DialogEventType.ENGLISH_LESSON_DRILL_REQUESTED

    def apply_to(self, dialog_state: DialogState) -> None:
        pass


class NextDrillRequested(DialogEvent):
    event_type: DialogEventType = DialogEventType.NEXT_DRILL_REQUESTED

    def apply_to(self, dialog_state: DialogState) -> None:
        dialog_state.user_profile.opted_out = False


class SchedulingDrillRequested(DialogEvent):
    event_type: DialogEventType = DialogEventType.SCHEDULING_DRILL_REQUESTED
    abandoned_drill_instance_id: Optional[uuid.UUID] = None

    def apply_to(self, dialog_state: DialogState) -> None:
        dialog_state.current_drill = None
        dialog_state.drill_instance_id = None
        dialog_state.current_prompt_state = None
        dialog_state.user_profile.opted_out = False


class NameChangeDrillRequested(DialogEvent):
    event_type: DialogEventType = DialogEventType.NAME_CHANGE_DRILL_REQUESTED
    abandoned_drill_instance_id: Optional[uuid.UUID] = None

    def apply_to(self, dialog_state: DialogState) -> None:
        dialog_state.current_drill = None
        dialog_state.drill_instance_id = None
        dialog_state.current_prompt_state = None
        dialog_state.user_profile.opted_out = False


class LanguageChangeDrillRequested(DialogEvent):
    event_type: DialogEventType = DialogEventType.LANGUAGE_CHANGE_DRILL_REQUESTED
    abandoned_drill_instance_id: Optional[uuid.UUID] = None

    def apply_to(self, dialog_state: DialogState) -> None:
        dialog_state.current_drill = None
        dialog_state.drill_instance_id = None
        dialog_state.current_prompt_state = None
        dialog_state.user_profile.opted_out = False


class SupportRequested(DialogEvent):
    event_type: DialogEventType = DialogEventType.SUPPORT_REQUESTED

    def apply_to(self, dialog_state: DialogState) -> None:
        pass


class DashboardRequested(DialogEvent):
    event_type: DialogEventType = DialogEventType.DASHBOARD_REQUESTED
    abandoned_drill_instance_id: Optional[uuid.UUID] = None

    def apply_to(self, dialog_state: DialogState) -> None:
        dialog_state.user_profile.opted_out = False


class UnhandledMessageReceived(DialogEvent):
    event_type: DialogEventType = DialogEventType.UNHANDLED_MESSAGE_RECEIVED
    message: str = "None"

    def apply_to(self, dialog_state: DialogState) -> None:
        pass


class DemoRequested(DialogEvent):
    event_type: DialogEventType = DialogEventType.DEMO_REQUESTED

    def apply_to(self, dialog_state: DialogState) -> None:
        pass


class ThankYouReceived(DialogEvent):
    event_type: DialogEventType = DialogEventType.THANK_YOU_RECEIVED

    def apply_to(self, dialog_state: DialogState) -> None:
        pass


class MenuRequested(DialogEvent):
    event_type: DialogEventType = DialogEventType.MENU_REQUESTED
    abandoned_drill_instance_id: Optional[uuid.UUID] = None

    def apply_to(self, dialog_state: DialogState) -> None:
        dialog_state.user_profile.opted_out = False


class UserUpdated(DialogEvent):
    event_type: DialogEventType = DialogEventType.USER_UPDATED
    user_profile_data: dict
    purge_drill_state: bool = False

    def apply_to(self, dialog_state: DialogState) -> None:
        # TODO: revisit this (pretty unfortunate) updating logic. Maybe we should always just
        # overwrite the dialog engine user profile data from scadmin, rather than having two
        # sources of truth?
        account_info = dialog_state.user_profile.account_info
        if "account_info" in self.user_profile_data:
            account_info = (
                account_info.copy(update=self.user_profile_data["account_info"])
                if account_info
                else AccountInfo(**self.user_profile_data["account_info"])
            )
        dialog_state.user_profile = dialog_state.user_profile.copy(update=self.user_profile_data)
        dialog_state.user_profile.account_info = account_info
        if self.purge_drill_state:
            dialog_state.current_drill = None
            dialog_state.drill_instance_id = None
            dialog_state.current_prompt_state = None


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
    DialogEventType.DRILL_REQUESTED: DrillRequested,
    DialogEventType.ENGLISH_LESSON_DRILL_REQUESTED: EnglishLessonDrillRequested,
    DialogEventType.SCHEDULING_DRILL_REQUESTED: SchedulingDrillRequested,
    DialogEventType.AD_HOC_MESSAGE_SENT: AdHocMessageSent,
    DialogEventType.NAME_CHANGE_DRILL_REQUESTED: NameChangeDrillRequested,
    DialogEventType.LANGUAGE_CHANGE_DRILL_REQUESTED: LanguageChangeDrillRequested,
    DialogEventType.MENU_REQUESTED: MenuRequested,
    DialogEventType.UNHANDLED_MESSAGE_RECEIVED: UnhandledMessageReceived,
    DialogEventType.SUPPORT_REQUESTED: SupportRequested,
    DialogEventType.DASHBOARD_REQUESTED: DashboardRequested,
    DialogEventType.USER_UPDATED: UserUpdated,
    DialogEventType.THANK_YOU_RECEIVED: ThankYouReceived,
    DialogEventType.DEMO_REQUESTED: DemoRequested,
}


def event_from_dict(event_dict: Dict[str, Any]) -> DialogEvent:
    event_type: DialogEventType = DialogEventType(event_dict["event_type"])
    return TYPE_TO_SCHEMA[event_type](**event_dict)


class DialogEventBatch(pydantic.BaseModel):
    events: List[DialogEvent]
    phone_number: str
    seq: str
    batch_id: uuid.UUID = pydantic.Field(default_factory=uuid.uuid4)
    created_time: datetime = pydantic.Field(default_factory=lambda: datetime.now(UTC))
    user_profile: Optional[UserProfile] = None


def batch_from_dict(batch_dict: Dict[str, Any]) -> DialogEventBatch:
    events = batch_dict.pop("events") if "events" in batch_dict else []
    return DialogEventBatch(
        events=[event_from_dict(event_dict) for event_dict in events], **batch_dict
    )
