import functools
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict

import requests
from marshmallow import Schema, fields, post_load

from .models.state import AccountInfoField


class CodeValidationPayloadSchema(Schema):
    valid = fields.Boolean(required=True)
    is_demo = fields.Boolean()
    account_info = AccountInfoField(keys=fields.Str(), allow_none=True)

    @post_load
    def make_code_validation_payload(self, data, **kwargs):
        return CodeValidationPayload(**data)


@dataclass
class CodeValidationPayload:
    valid: bool
    is_demo: bool = False
    account_info: Dict[str, Any] = field(default_factory=lambda: {})


class RegistrationValidator(ABC):
    @abstractmethod
    def validate_code(self, code) -> CodeValidationPayload:
        pass


class DefaultRegistrationValidator(RegistrationValidator):
    @functools.lru_cache(maxsize=1024)
    def validate_code(self, code, **kwargs) -> CodeValidationPayload:
        url = kwargs.get("url", os.environ["REGISTRATION_VALIDATION_URL"])
        key = kwargs.get("key", os.getenv("REGISTRATION_VALIDATION_KEY"))
        response = requests.post(
            url=url,
            json={"code": code, "stage": os.getenv("STAGE")},
            headers={"authorization": f"Bearer {key}", "content-type": "application/json",},
        )
        return CodeValidationPayloadSchema().load(response.json())
