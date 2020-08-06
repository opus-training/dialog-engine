import unittest

from stopcovid.drills import drills


class TestPrompt(unittest.TestCase):
    def test_should_advance_ignore(self):
        prompt = drills.Prompt(slug="test-prompt", messages=[drills.PromptMessage(text="{{msg1}}")])
        self.assertTrue(prompt.should_advance_with_answer("any answer"))

    def test_should_advance_store(self):
        prompt = drills.Prompt(
            slug="test-prompt",
            messages=[drills.PromptMessage(text="{{msg1}}")],
            response_user_profile_key="self_rating_7",
        )
        self.assertTrue(prompt.should_advance_with_answer("any answer"))

    def test_should_advance_graded(self):
        prompt = drills.Prompt(
            slug="test-prompt",
            messages=[drills.PromptMessage(text="{{msg1}}")],
            correct_response="my response",
        )

        self.assertFalse(prompt.should_advance_with_answer("something completely different"))
        self.assertTrue(prompt.should_advance_with_answer("my response"))
