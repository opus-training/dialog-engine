from typing import Dict, Optional

from jinja2 import Template


SUPPORTED_LANGUAGES = {"en", "es", "fr", "pt", "zh"}


def localize(message: str, lang: Optional[str], **kwargs) -> str:
    lang = lang or "en"
    lang = lang.lower()
    if lang not in SUPPORTED_LANGUAGES:
        lang = "en"

    template = Template(message)
    result = template.render({**kwargs, **localizations_for(lang)})

    if kwargs:
        template = Template(result)
        result = template.render(**kwargs)
    return result


def localizations_for(lang: str) -> Dict[str, str]:
    from .content_loader import get_translation_loader

    return get_translation_loader().get_translations()[lang]
