import unittest

from stopcovid.drills import localize


class TestLocalize(unittest.TestCase):
    def test_localization(self):
        self.assertEqual(
            "🤖 Sorry, not correct. 🤔\n\n*Try again one more time!*",
            localize.localize("{{incorrect_answer}}", None),
        )
        self.assertEqual(
            "🤖 Sorry, not correct. 🤔\n\n*Try again one more time!*",
            localize.localize("{{incorrect_answer}}", "en"),
        )
        self.assertEqual(
            "🤖 Lo siento, no es correcto.🤔\n\n*¡Intenta una vez más!*",
            localize.localize("{{incorrect_answer}}", "es"),
        )
        self.assertEqual(
            "🤖 Lo siento, no es correcto.🤔\n\n*¡Intenta una vez más!*",
            localize.localize("{{incorrect_answer}}", "Es"),
        )
        self.assertEqual(
            "🤖 Sorry, not correct. 🤔\n\n*Try again one more time!*",
            localize.localize("{{incorrect_answer}}", "xx"),
        )
