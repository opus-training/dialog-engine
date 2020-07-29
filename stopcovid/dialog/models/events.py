import datetime
import enum
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional, Dict, Type, Any, List

from marshmallow import fields, post_load, utils, Schema

from stopcovid.dialog.registration import (
    CodeValidationPayloadSchema,
    CodeValidationPayload,
)
from stopcovid.dialog.models.state import (
    DialogState,
    UserProfileSchema,
    UserProfile,
    PromptState,
)
from stopcovid.dialog.models import SCHEMA_VERSION
from stopcovid.drills import drills
from stopcovid.sms.types import SMSSchema, SMS


class EventTypeField(fields.Field):
    """Field that serializes to a title case string and deserializes
    to a lower case string.
    """

    def _serialize(self, value, attr, obj, **kwargs):
        return value.name

    def _deserialize(self, value, attr, data, **kwargs):
        return DialogEventType[value]


class DialogEventSchema(Schema):
    phone_number = fields.String(required=True)
    created_time = fields.DateTime(required=True)
    event_id = fields.UUID(required=True)
    event_type = EventTypeField(required=True)
    user_profile = fields.Nested(UserProfileSchema, required=True)
    schema_version = fields.Integer(missing=1)


class DrillStartedSchema(DialogEventSchema):
    drill = fields.Nested(drills.DrillSchema, required=True)
    drill_instance_id = fields.UUID(required=True)
    first_prompt = fields.Nested(drills.PromptSchema, required=True)

    @post_load
    def make_drill_started(self, data, **kwargs):
        return DrillStarted(**{k: v for k, v in data.items() if k != "event_type"})


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


class DialogEvent(ABC):
    def __init__(
        self,
        schema: Schema,
        event_type: DialogEventType,
        phone_number: str,
        user_profile: UserProfile,
        **kwargs,
    ):
        self.schema = schema
        self.phone_number = phone_number

        # relying on created time to determine ordering. We should be fine and it's simpler than
        # sequence numbers. Events are processed in order by phone number and are relatively
        # infrequent. And the lambda environment has some clock guarantees.
        self.created_time = kwargs.get("created_time", datetime.datetime.now(datetime.timezone.utc))
        self.event_id = kwargs.get("event_id", uuid.uuid4())
        self.event_type = event_type
        self.user_profile = user_profile
        self.schema_version = SCHEMA_VERSION

    @abstractmethod
    def apply_to(self, dialog_state: DialogState):
        pass

    def to_dict(self) -> Dict:
        return self.schema.dump(self)


class DrillStarted(DialogEvent):
    def __init__(
        self,
        phone_number: str,
        user_profile: UserProfile,
        drill: drills.Drill,
        first_prompt: drills.Prompt,
        **kwargs,
    ):
        super().__init__(
            DrillStartedSchema(),
            DialogEventType.DRILL_STARTED,
            phone_number,
            user_profile,
            **kwargs,
        )
        self.drill = drill
        self.first_prompt = first_prompt
        self.drill_instance_id = kwargs.get("drill_instance_id", uuid.uuid4())

    def apply_to(self, dialog_state: DialogState):
        dialog_state.current_drill = self.drill
        dialog_state.drill_instance_id = self.drill_instance_id
        dialog_state.current_prompt_state = PromptState(
            self.first_prompt.slug, start_time=self.created_time
        )


class AdHocMessageSentSchema(DialogEventSchema):
    sms = fields.Nested(SMSSchema, required=True)

    @post_load
    def make_ad_hoc_message_sent(self, data, **kwargs):
        return AdHocMessageSent(**{k: v for k, v in data.items() if k != "event_type"})


class AdHocMessageSent(DialogEvent):
    def __init__(self, phone_number: str, user_profile: UserProfile, sms: SMS, **kwargs):
        super().__init__(
            AdHocMessageSentSchema(),
            DialogEventType.AD_HOC_MESSAGE_SENT,
            phone_number,
            user_profile,
            **kwargs,
        )
        self.sms = sms

    def apply_to(self, dialog_state: DialogState):
        pass


class UserValidatedSchema(DialogEventSchema):
    code_validation_payload = fields.Nested(CodeValidationPayloadSchema, required=True)

    @post_load
    def make_user_created(self, data, **kwargs):
        return UserValidated(**{k: v for k, v in data.items() if k != "event_type"})


class UserValidated(DialogEvent):
    def __init__(
        self,
        phone_number: str,
        user_profile: UserProfile,
        code_validation_payload: CodeValidationPayload,
        **kwargs,
    ):
        super().__init__(
            UserValidatedSchema(),
            DialogEventType.USER_VALIDATED,
            phone_number,
            user_profile,
            **kwargs,
        )
        self.code_validation_payload = code_validation_payload

    def apply_to(self, dialog_state: DialogState):
        dialog_state.drill_instance_id = None
        dialog_state.current_prompt_state = None
        dialog_state.current_drill = None
        dialog_state.user_profile.validated = True
        dialog_state.user_profile.is_demo = self.code_validation_payload.is_demo
        dialog_state.user_profile.account_info = self.code_validation_payload.account_info


class UserValidationFailedSchema(DialogEventSchema):
    @post_load
    def make_user_creation_failed(self, data, **kwargs):
        return UserValidationFailed(**{k: v for k, v in data.items() if k != "event_type"})


class UserValidationFailed(DialogEvent):
    def __init__(self, phone_number: str, user_profile: UserProfile, **kwargs):
        super().__init__(
            UserValidationFailedSchema(),
            DialogEventType.USER_VALIDATION_FAILED,
            phone_number,
            user_profile,
            **kwargs,
        )

    def apply_to(self, dialog_state: DialogState):
        pass


class CompletedPromptSchema(DialogEventSchema):
    prompt = fields.Nested(drills.PromptSchema, required=True)
    response = fields.String(required=True)
    drill_instance_id = fields.UUID(required=True)

    @post_load
    def make_completed_prompt(self, data, **kwargs):
        return CompletedPrompt(**{k: v for k, v in data.items() if k != "event_type"})


class CompletedPrompt(DialogEvent):
    def __init__(
        self,
        phone_number: str,
        user_profile: UserProfile,
        prompt: drills.Prompt,
        drill_instance_id: uuid.UUID,
        response: str,
        **kwargs,
    ):
        super().__init__(
            CompletedPromptSchema(),
            DialogEventType.COMPLETED_PROMPT,
            phone_number,
            user_profile,
            **kwargs,
        )
        self.prompt = prompt
        self.response = response
        self.drill_instance_id = drill_instance_id

    def apply_to(self, dialog_state: DialogState):
        dialog_state.current_prompt_state = None
        if self.prompt.response_user_profile_key:
            setattr(
                dialog_state.user_profile, self.prompt.response_user_profile_key, self.response,
            )


class FailedPromptSchema(DialogEventSchema):
    prompt = fields.Nested(drills.PromptSchema, required=True)
    abandoned = fields.Boolean(required=True)
    response = fields.String(required=True, allow_none=True)
    drill_instance_id = fields.UUID(required=True)

    @post_load
    def make_failed_prompt(self, data, **kwargs):
        return FailedPrompt(**{k: v for k, v in data.items() if k != "event_type"})


class FailedPrompt(DialogEvent):
    def __init__(
        self,
        phone_number: str,
        user_profile: UserProfile,
        prompt: drills.Prompt,
        drill_instance_id: uuid.UUID,
        response: Optional[str],
        abandoned: bool,
        **kwargs,
    ):
        super().__init__(
            FailedPromptSchema(),
            DialogEventType.FAILED_PROMPT,
            phone_number,
            user_profile,
            **kwargs,
        )
        self.prompt = prompt
        self.abandoned = abandoned
        self.response = response
        self.drill_instance_id = drill_instance_id

    def apply_to(self, dialog_state: DialogState):
        if self.abandoned:
            dialog_state.current_prompt_state = None
        else:
            dialog_state.current_prompt_state.last_response_time = self.created_time
            dialog_state.current_prompt_state.failures += 1


class AdvancedToNextPromptSchema(DialogEventSchema):
    prompt = fields.Nested(drills.PromptSchema, required=True)
    drill_instance_id = fields.UUID(required=True)

    @post_load
    def make_advanced_to_next_prompt(self, data, **kwargs):
        return AdvancedToNextPrompt(**{k: v for k, v in data.items() if k != "event_type"})


class AdvancedToNextPrompt(DialogEvent):
    def __init__(
        self,
        phone_number: str,
        user_profile: UserProfile,
        prompt: drills.Prompt,
        drill_instance_id: uuid.UUID,
        **kwargs,
    ):
        super().__init__(
            AdvancedToNextPromptSchema(),
            DialogEventType.ADVANCED_TO_NEXT_PROMPT,
            phone_number,
            user_profile,
            **kwargs,
        )
        self.prompt = prompt
        self.drill_instance_id = drill_instance_id

    def apply_to(self, dialog_state: DialogState):
        dialog_state.current_prompt_state = PromptState(
            self.prompt.slug, start_time=self.created_time
        )


class DrillCompletedSchema(DialogEventSchema):
    drill_instance_id = fields.UUID(required=True)
    auto_continue = fields.Boolean(missing=False)

    @post_load
    def make_drill_completed(self, data, **kwargs):
        return DrillCompleted(**{k: v for k, v in data.items() if k != "event_type"})


class DrillCompleted(DialogEvent):
    def __init__(
        self,
        phone_number: str,
        user_profile: UserProfile,
        drill_instance_id: uuid.UUID,
        auto_continue: Optional[bool] = False,
        **kwargs,
    ):
        super().__init__(
            DrillCompletedSchema(),
            DialogEventType.DRILL_COMPLETED,
            phone_number,
            user_profile,
            **kwargs,
        )
        self.drill_instance_id = drill_instance_id
        self.auto_continue = auto_continue

    def apply_to(self, dialog_state: DialogState):
        dialog_state.current_drill = None
        dialog_state.drill_instance_id = None
        dialog_state.current_prompt_state = None


class OptedOutSchema(DialogEventSchema):
    drill_instance_id = fields.UUID(allow_none=True)

    @post_load
    def make_opted_out(self, data, **kwargs):
        return OptedOut(**{k: v for k, v in data.items() if k != "event_type"})


class OptedOut(DialogEvent):
    def __init__(
        self,
        phone_number: str,
        user_profile: UserProfile,
        drill_instance_id: Optional[uuid.UUID],
        **kwargs,
    ):
        super().__init__(
            OptedOutSchema(), DialogEventType.OPTED_OUT, phone_number, user_profile, **kwargs,
        )
        self.drill_instance_id = drill_instance_id

    def apply_to(self, dialog_state: DialogState):
        dialog_state.drill_instance_id = None
        dialog_state.user_profile.opted_out = True
        dialog_state.current_drill = None
        dialog_state.current_prompt_state = None


class NextDrillRequestedSchema(DialogEventSchema):
    @post_load
    def make_next_drill_requested(self, data, **kwargs):
        return NextDrillRequested(**{k: v for k, v in data.items() if k != "event_type"})


class NextDrillRequested(DialogEvent):
    def __init__(self, phone_number: str, user_profile: UserProfile, **kwargs):
        super().__init__(
            NextDrillRequestedSchema(),
            DialogEventType.NEXT_DRILL_REQUESTED,
            phone_number,
            user_profile,
            **kwargs,
        )

    def apply_to(self, dialog_state: DialogState):
        dialog_state.user_profile.opted_out = False


class SchedulingDrillRequestedSchema(DialogEventSchema):
    @post_load
    def make_next_drill_requested(self, data, **kwargs):
        return SchedulingDrillRequested(**{k: v for k, v in data.items() if k != "event_type"})


class SchedulingDrillRequested(DialogEvent):
    def __init__(self, phone_number: str, user_profile: UserProfile, **kwargs):
        super().__init__(
            SchedulingDrillRequestedSchema(),
            DialogEventType.SCHEDULING_DRILL_REQUESTED,
            phone_number,
            user_profile,
            **kwargs,
        )

    def apply_to(self, dialog_state: DialogState):
        dialog_state.current_drill = None
        dialog_state.drill_instance_id = None
        dialog_state.current_prompt_state = None
        dialog_state.user_profile.opted_out = False


class NameChangeDrillRequestedSchema(DialogEventSchema):
    @post_load
    def make_next_drill_requested(self, data, **kwargs):
        return NameChangeDrillRequested(**{k: v for k, v in data.items() if k != "event_type"})


class NameChangeDrillRequested(DialogEvent):
    def __init__(self, phone_number: str, user_profile: UserProfile, **kwargs):
        super().__init__(
            NameChangeDrillRequestedSchema(),
            DialogEventType.NAME_CHANGE_DRILL_REQUESTED,
            phone_number,
            user_profile,
            **kwargs,
        )

    def apply_to(self, dialog_state: DialogState):
        dialog_state.current_drill = None
        dialog_state.drill_instance_id = None
        dialog_state.current_prompt_state = None
        dialog_state.user_profile.opted_out = False


class LanguageChangeDrillRequestedSchema(DialogEventSchema):
    @post_load
    def make_next_drill_requested(self, data, **kwargs):
        return LanguageChangeDrillRequested(**{k: v for k, v in data.items() if k != "event_type"})


class LanguageChangeDrillRequested(DialogEvent):
    def __init__(self, phone_number: str, user_profile: UserProfile, **kwargs):
        super().__init__(
            LanguageChangeDrillRequestedSchema(),
            DialogEventType.LANGUAGE_CHANGE_DRILL_REQUESTED,
            phone_number,
            user_profile,
            **kwargs,
        )

    def apply_to(self, dialog_state: DialogState):
        dialog_state.current_drill = None
        dialog_state.drill_instance_id = None
        dialog_state.current_prompt_state = None
        dialog_state.user_profile.opted_out = False


class MenuRequestedSchema(DialogEventSchema):
    @post_load
    def make_next_drill_requested(self, data, **kwargs):
        return MenuRequested(**{k: v for k, v in data.items() if k != "event_type"})


class MenuRequested(DialogEvent):
    def __init__(self, phone_number: str, user_profile: UserProfile, **kwargs):
        super().__init__(
            MenuRequestedSchema(),
            DialogEventType.MENU_REQUESTED,
            phone_number,
            user_profile,
            **kwargs,
        )

    def apply_to(self, dialog_state: DialogState):
        dialog_state.current_drill = None
        dialog_state.drill_instance_id = None
        dialog_state.current_prompt_state = None
        dialog_state.user_profile.opted_out = False


TYPE_TO_SCHEMA: Dict[DialogEventType, Type[DialogEventSchema]] = {
    DialogEventType.ADVANCED_TO_NEXT_PROMPT: AdvancedToNextPromptSchema,
    DialogEventType.DRILL_COMPLETED: DrillCompletedSchema,
    DialogEventType.USER_VALIDATION_FAILED: UserValidationFailedSchema,
    DialogEventType.DRILL_STARTED: DrillStartedSchema,
    DialogEventType.USER_VALIDATED: UserValidatedSchema,
    DialogEventType.COMPLETED_PROMPT: CompletedPromptSchema,
    DialogEventType.FAILED_PROMPT: FailedPromptSchema,
    DialogEventType.OPTED_OUT: OptedOutSchema,
    DialogEventType.NEXT_DRILL_REQUESTED: NextDrillRequestedSchema,
    DialogEventType.SCHEDULING_DRILL_REQUESTED: SchedulingDrillRequestedSchema,
    DialogEventType.AD_HOC_MESSAGE_SENT: AdHocMessageSentSchema,
    DialogEventType.NAME_CHANGE_DRILL_REQUESTED: NameChangeDrillRequestedSchema,
    DialogEventType.LANGUAGE_CHANGE_DRILL_REQUESTED: LanguageChangeDrillRequestedSchema,
    DialogEventType.MENU_REQUESTED: MenuRequestedSchema,
}


def event_from_dict(event_dict: Dict[str, Any]) -> DialogEvent:
    event_type = DialogEventType[event_dict["event_type"]]
    return TYPE_TO_SCHEMA[event_type]().load(event_dict)


@dataclass
class DialogEventBatch:
    events: List[DialogEvent]
    phone_number: str
    seq: str
    batch_id: uuid.UUID = field(default_factory=uuid.uuid4)
    created_time: datetime.datetime = field(
        default_factory=lambda: datetime.datetime.now(datetime.timezone.utc)
    )

    def to_dict(self):
        return {
            "batch_id": str(self.batch_id),
            "seq": self.seq,
            "phone_number": self.phone_number,
            "created_time": utils.isoformat(self.created_time),
            "events": [event.to_dict() for event in self.events],
        }


def batch_from_dict(batch_dict: Dict[str, Any]) -> DialogEventBatch:
    return DialogEventBatch(
        batch_id=uuid.UUID(batch_dict["batch_id"]),
        phone_number=batch_dict["phone_number"],
        seq=batch_dict["seq"],
        created_time=utils.from_iso_datetime(batch_dict["created_time"]),
        events=[event_from_dict(event_dict) for event_dict in batch_dict["events"]],
    )
