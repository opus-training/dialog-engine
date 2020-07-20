import uuid
import datetime
from dataclasses import dataclass, field
from typing import Optional, Dict, Any

from marshmallow import Schema, fields, post_load

from stopcovid.dialog.models import SCHEMA_VERSION
from stopcovid.drills import drills


class AccountInfoField(fields.Mapping):
    def _serialize(self, value, attr, obj, **kwargs):
        if "employer_id" in value:
            value["employer_id"] = int(value["employer_id"])

        if "unit_id" in value:
            value["unit_id"] = int(value["unit_id"])
        return value

    def _deserialize(self, value, attr, data, **kwargs):
        return value


class UserProfileSchema(Schema):
    validated = fields.Boolean(required=True)
    opted_out = fields.Boolean(missing=False)
    language = fields.Str(allow_none=True)
    name = fields.Str(allow_none=True)
    account_info = AccountInfoField(keys=fields.Str(), allow_none=True)
    is_demo = fields.Boolean()
    self_rating_1 = fields.Str(allow_none=True)
    self_rating_2 = fields.Str(allow_none=True)
    self_rating_3 = fields.Str(allow_none=True)
    self_rating_4 = fields.Str(allow_none=True)
    self_rating_5 = fields.Str(allow_none=True)
    self_rating_6 = fields.Str(allow_none=True)
    self_rating_7 = fields.Str(allow_none=True)
    self_rating_8 = fields.Str(allow_none=True)
    job = fields.Str(allow_none=True)
    schedule_days = fields.Str(allow_none=True)
    schedule_time = fields.Str(allow_none=True)

    @post_load
    def make_user_profile(self, data, **kwargs):
        return UserProfile(**data)


@dataclass
class UserProfile:
    validated: bool
    opted_out: bool = False
    is_demo: bool = False
    name: Optional[str] = None
    language: Optional[str] = None
    account_info: Dict[str, Any] = field(default_factory=lambda: {})
    self_rating_1: Optional[str] = None
    self_rating_2: Optional[str] = None
    self_rating_3: Optional[str] = None
    self_rating_4: Optional[str] = None
    self_rating_5: Optional[str] = None
    self_rating_6: Optional[str] = None
    self_rating_7: Optional[str] = None
    self_rating_8: Optional[str] = None
    job: Optional[str] = None
    schedule_days: Optional[str] = None
    schedule_time: Optional[str] = None

    def __str__(self):
        return f"lang={self.language}, validated={self.validated}, " f"name={self.name}"

    def __setattr__(self, key, value):
        if key == "language" and value is not None:
            super().__setattr__(key, value.lower()[:2])
        else:
            super().__setattr__(key, value)

    def to_dict(self):
        return UserProfileSchema().dump(self)


class PromptStateSchema(Schema):
    slug = fields.Str(required=True)
    start_time = fields.DateTime(required=True)
    failures = fields.Int(allow_none=True)
    reminder_triggered = fields.Boolean(allow_none=True, required=False)

    @post_load
    def make_prompt_state(self, data, **kwargs):
        return PromptState(**data)


@dataclass
class PromptState:
    slug: str
    start_time: datetime.datetime
    last_response_time: Optional[datetime.datetime] = None
    reminder_triggered: bool = False
    failures: int = 0


class DialogStateSchema(Schema):
    phone_number = fields.Str(required=True)
    # store sequence number as a string to int conversion imprecision
    seq = fields.Str(required=True)
    user_profile = fields.Nested(UserProfileSchema, allow_none=True)
    # persist the entire drill so that modifications to drills don"t affect
    # drills that are in flight
    current_drill = fields.Nested(drills.DrillSchema, allow_none=True)
    drill_instance_id = fields.UUID(allow_none=True)
    current_prompt_state = fields.Nested(PromptStateSchema, allow_none=True)
    schema_version = fields.Integer(missing=1)

    @post_load
    def make_dialog_state(self, data, **kwargs):
        return DialogState(**data)


@dataclass
class DialogState:
    phone_number: str
    seq: str
    schema_version: int = SCHEMA_VERSION
    user_profile: UserProfile = field(default_factory=lambda: UserProfile(validated=False))
    current_drill: Optional[drills.Drill] = None
    drill_instance_id: Optional[uuid.UUID] = None
    current_prompt_state: Optional[PromptState] = None

    def get_prompt(self) -> Optional[drills.Prompt]:
        if self.current_drill is None or self.current_prompt_state is None:
            return None
        return self.current_drill.get_prompt(self.current_prompt_state.slug)

    def get_next_prompt(self) -> Optional[drills.Prompt]:
        return self.current_drill.get_next_prompt(self.current_prompt_state.slug)

    def is_next_prompt_last(self) -> bool:
        return self.current_drill.prompts[-1].slug == self.get_next_prompt().slug

    def to_dict(self) -> Dict:
        return DialogStateSchema().dump(self)
