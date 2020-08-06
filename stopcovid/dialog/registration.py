import functools
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

import requests
import pydantic


class AccountInfo(pydantic.BaseModel):
    employer_id: int
    employer_name: str
    unit_id: int
    unit_name: str


@dataclass
class CodeValidationPayload:
    valid: bool
    is_demo: bool = False
    account_info: Optional[AccountInfo] = None


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
        return CodeValidationPayload(**response.json())
