import functools
import os
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional

import pydantic
import requests


class CodeValidationPayload(pydantic.BaseModel):
    valid: bool
    is_demo: bool = False
    account_info: Optional[Dict[str, Any]] = None


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
