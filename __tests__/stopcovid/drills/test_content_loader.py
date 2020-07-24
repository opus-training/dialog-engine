import unittest

from stopcovid.drills.content_loader import translate, SupportedTranslation


class TestTranslate(unittest.TestCase):
    def test_english(self):
        self.assertEqual(
            translate("en", SupportedTranslation.INCORRECT_ANSWER),
            "🤖 Sorry, not correct. Try again one more time.",
        )
        self.assertEqual(
            translate(
                "en", SupportedTranslation.CORRECTED_ANSWER, correct_answer="a) Philadelphia"
            ),
            "🤖 The correct answer is *a) Philadelphia*.\n\nLets move to the next one.",
        )
        self.assertEqual(translate("en", SupportedTranslation.MATCH_CORRECT_ANSWER), "🤖 Correct!")

    def test_non_supported_lang_falls_back_to_english(self):
        self.assertEqual(
            translate("zh", SupportedTranslation.INCORRECT_ANSWER),
            "🤖 Sorry, not correct. Try again one more time.",
        )
        self.assertEqual(
            translate(
                "zh", SupportedTranslation.CORRECTED_ANSWER, correct_answer="a) Philadelphia"
            ),
            "🤖 The correct answer is *a) Philadelphia*.\n\nLets move to the next one.",
        )
        self.assertEqual(translate("zh", SupportedTranslation.MATCH_CORRECT_ANSWER), "🤖 Correct!")

    def test_spanish(self):
        self.assertEqual(
            translate("es", SupportedTranslation.INCORRECT_ANSWER),
            "🤖 Lo siento, no es correcto. ¡Inténtalo de nuevo!",
        )
        self.assertEqual(
            translate(
                "es", SupportedTranslation.CORRECTED_ANSWER, correct_answer="a) Philadelphia"
            ),
            "🤖 La respuesta correcta es *a) Philadelphia*.\n\nAvancemos a la siguiente.",
        )
        self.assertEqual(translate("es", SupportedTranslation.MATCH_CORRECT_ANSWER), "🤖 ¡Correcto!")

    def test_french(self):
        self.assertEqual(
            translate("fr", SupportedTranslation.INCORRECT_ANSWER),
            "🤖 Désolé, ce n'est pas correct. Essayez à nouveau!",
        )
        self.assertEqual(
            translate(
                "fr", SupportedTranslation.CORRECTED_ANSWER, correct_answer="a) Philadelphia"
            ),
            "🤖 La bonne réponse est *a) Philadelphia*.\n\nPassons à la suite.",
        )
        self.assertEqual(
            translate("fr", SupportedTranslation.MATCH_CORRECT_ANSWER), "🤖 C'est Correct!"
        )
