import unittest

from stopcovid.drills.response_check import is_correct_response

SAMPLES = [
    ["a) si", "b) no", False],
    ["La a", "a) test", True],
    ["La b", "a) test", False],
    ["a", "a) test", True],
    ["b", "a) test", False],
    ["b", "a) sí", False],
    ["test", "a) test", True],
    ["else", "a) test", False],
    ["I need a lid", "a) I need a lid", True],
    ["Safety pin", "a) I need a lid", False],
    ["uses mandolin", "d) uses / mandolin", True],
    ["She uses a mandolin", "d) uses / mandolin", True],
    ["She uses a knife", "d) uses / mandolin", False],
    ["2-3 pumps", "b) 2-3 pumps", True],
    ["1 pump", "b) 2-3 pumps", False],
    ["a water proof bandage", "a. first aid kit", False],
]


class TestResponseCheck(unittest.TestCase):
    def test_all_samples(self):
        for user_supplied, correct, expected in SAMPLES:
            self.assertEqual(
                expected,
                is_correct_response(user_supplied, correct),
                f"User-supplied: {user_supplied}, Correct: {correct}," f" Expected: {expected}",
            )

    def test_empty(self):
        self.assertFalse(is_correct_response("", "b) 2-3 pumps"))
        self.assertFalse(is_correct_response(" ", "b) 2-3 pumps"))
