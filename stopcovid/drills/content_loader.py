import json
import os
import enum
import random
from typing import Dict, Any, List, Optional
from jinja2 import Template


from .drills import Drill

__location__ = os.path.realpath(os.path.join(os.getcwd(), os.path.dirname(__file__)))


class SupportedTranslation(enum.Enum):
    INCORRECT_ANSWER = "INCORRECT_ANSWER"
    CORRECTED_ANSWER = "CORRECTED_ANSWER"
    MATCH_CORRECT_ANSWER = "MATCH_CORRECT_ANSWER"


TRANSLATIONS = {
    "en": {
        SupportedTranslation.INCORRECT_ANSWER: "🤖 Sorry, not correct. Try again one more time.",
        SupportedTranslation.CORRECTED_ANSWER: "🤖 The correct answer is *{{correct_answer}}*.\n\nLets move to the next one.",
        SupportedTranslation.MATCH_CORRECT_ANSWER: "Correct!",
    },
    "es": {
        SupportedTranslation.INCORRECT_ANSWER: "🤖 Lo siento, no es correcto. ¡Inténtalo de nuevo!",
        SupportedTranslation.CORRECTED_ANSWER: "🤖 La respuesta correcta es *{{correct_answer}}*.\n\nAvancemos a la siguiente.",
        SupportedTranslation.MATCH_CORRECT_ANSWER: "¡Correcto!",
    },
    "fr": {
        SupportedTranslation.INCORRECT_ANSWER: "🤖 Désolé, ce n'est pas correct. Essayez à nouveau!",
        SupportedTranslation.CORRECTED_ANSWER: "🤖 La bonne réponse est *{{correct_answer}}*.\n\nPassons à la suite.",
        SupportedTranslation.MATCH_CORRECT_ANSWER: "C'est Correct!",
    },
    "km": {
        SupportedTranslation.INCORRECT_ANSWER: "🤖សូមអភ័យទោសមិនត្រឹមត្រូវ។ ព្យាយាមម្តងទៀត។",
        SupportedTranslation.CORRECTED_ANSWER: "🤖ចម្លើយដែលត្រឹមត្រូវគឺ * {{correct_answer}} * ។\n\nអាចទៅកន្លែងបន្ទាប់។",
        SupportedTranslation.MATCH_CORRECT_ANSWER: "ត្រឹមត្រូវ!",
    },
}


def correct_answer_response(language: Optional[str]) -> str:
    return f"{random.choice(CORRECT_ANSWER_EMOJI)} {translate(language, SupportedTranslation.MATCH_CORRECT_ANSWER)}"


def template_additional_args(message: str, **kwargs: Any) -> str:
    template = Template(message)
    result = template.render({**kwargs})

    if kwargs:
        template = Template(result)
        result = template.render(**kwargs)
    return result


def translate(language: Optional[str], template: SupportedTranslation, **kwargs: Any) -> str:
    value = TRANSLATIONS.get(language or "en", TRANSLATIONS["en"])[template]
    if kwargs:
        value = template_additional_args(value, **kwargs)
    return value


class SourceRepoDrillLoader:
    def __init__(self) -> None:
        self.drills_dict: Dict[str, Drill] = {}
        self.all_drill_slugs: List[str] = []
        self._populate_content()

    def _populate_drills(self, drill_content: str) -> None:
        self.drills_dict = {}
        self.all_drill_slugs = []
        raw_drills = json.loads(drill_content)
        for drill_slug, raw_drill in raw_drills.items():
            self.drills_dict[drill_slug] = Drill(**raw_drill)
            self.all_drill_slugs.append(drill_slug)

        self.all_drill_slugs.sort()

    def _populate_content(self) -> None:
        with open(os.path.join(__location__, "drill_content/drills.json")) as f:
            self._populate_drills(f.read())

    def get_drills(self) -> Dict[str, Drill]:
        return self.drills_dict


CORRECT_ANSWER_EMOJI = [
    "⚡",
    "🏄",
    "🚀",
    "📈",
    "🏎",
    "😇",
    "😸",
    "🙌",
    "👌",
    "🐶",
    "🐞",
    "🦋",
    "🦄",
    "🦖",
    "🦕",
    "🐬",
    "🐟",
    "🐎",
    "🍀",
    "🌱",
    "�",
    "�",
    "🌸",
    "🌞",
    "🌻",
    "🌼",
    "🌝",
    "💫",
    "🌟",
    "🌈",
    "🔥",
    "✨",
    "🌊",
    "🥂",
    "🍬",
    "🍭",
    "⛳",
    "️",
    "🪁",
    "🏆",
    "🎗",
    "🎯",
    "🚁",
    "🏝",
    "🎊",
    "🎏",
    "🎉",
    "🥇",
    "🎖",
]
