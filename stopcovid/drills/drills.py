from typing import Optional, List

import pydantic

from .response_check import is_correct_response


class PromptMessage(pydantic.BaseModel):
    text: Optional[str]
    media_url: Optional[str] = None


class Prompt(pydantic.BaseModel):
    slug: str
    messages: List[PromptMessage]
    response_user_profile_key: Optional[str] = None
    correct_response: Optional[str] = None
    max_failures: Optional[int] = 1

    def should_advance_with_answer(self, answer: str) -> bool:
        if self.correct_response is None:
            return True
        return is_correct_response(answer, self.correct_response)


class Drill(pydantic.BaseModel):
    slug: str
    name: str
    prompts: List[Prompt]
    auto_continue: Optional[bool] = False

    def first_prompt(self) -> Prompt:
        return self.prompts[0]

    def get_prompt(self, slug: str) -> Optional[Prompt]:
        for p in self.prompts:
            if p.slug == slug:
                return p
        raise ValueError(f"unknown prompt {slug}")

    def get_next_prompt(self, slug: str) -> Optional[Prompt]:
        return_next = False
        for p in self.prompts:
            if return_next:
                return p
            if p.slug == slug:
                return_next = True
        return None
