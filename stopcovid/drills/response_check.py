import math
import re
from typing import List

from stopcovid.utils import levenshtein


def tokenize(text: str) -> List[str]:
    text = re.sub(r"[^\w]", " ", text).lower()
    text = re.sub(r"\b(he|she|the|an|i)\b", "", text)
    text = re.sub(r"[lL]a\s+(\w)", r"\1", text)
    return [w for w in text.split(" ") if w != ""]


def is_not_letter_answer(text: str) -> bool:
    return re.match(r"^[a-zA-Z]$", text) is None


def is_correct_response(user_response: str, correct_response: str) -> bool:
    clean_user_response = tokenize(user_response)
    if not clean_user_response:
        return False
    clean_correct_response = tokenize(correct_response)
    allowed_error = (
        math.floor(len("".join([w for w in clean_correct_response if is_not_letter_answer(w)])) / 4)
        or 1
    )

    # if user responds a single letter and it matches, user is correct
    if (
        len(clean_user_response) == 1
        and re.match(r"^[a-zA-Z]$", clean_user_response[0])
        and len(clean_correct_response[0]) == 1
    ):
        return clean_user_response[0] == clean_correct_response[0]

    # If answer includes "yes", accept "si" and vice versa
    if ("yes" in clean_user_response or "si" in clean_user_response) and (
        "yes" in clean_correct_response or "si" in clean_correct_response
    ):
        return True

    # If both answer and response include a no
    if "no" in clean_user_response and "no" in clean_correct_response:
        return True

    # If answer without single letters is close enough to response
    user_response_to_compare = "".join([w for w in clean_user_response if is_not_letter_answer(w)])
    correct_response_to_compare = "".join(
        [w for w in clean_correct_response if is_not_letter_answer(w)]
    )

    l_distance = levenshtein.distance(user_response_to_compare, correct_response_to_compare)

    if l_distance <= allowed_error:
        return True

    # If answer is contained entirely within user's response
    return " ".join([w for w in clean_correct_response if is_not_letter_answer(w)]) in " ".join(
        clean_user_response
    )
