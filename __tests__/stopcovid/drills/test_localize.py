import unittest

from stopcovid.drills import localize


class TestLocalize(unittest.TestCase):
    def test_localization(self):
        self.assertEqual(
            "You're almost done! Answer the question above.  ",
            localize.localize("{{drill_reminder}}", None),
        )
        self.assertEqual(
            "You're almost done! Answer the question above.  ",
            localize.localize("{{drill_reminder}}", "en"),
        )
        self.assertEqual(
            "¡Ya casi terminas! Responde la pregunta anterior.",
            localize.localize("{{drill_reminder}}", "es"),
        )
        self.assertEqual(
            "¡Ya casi terminas! Responde la pregunta anterior.",
            localize.localize("{{drill_reminder}}", "Es"),
        )
        self.assertEqual(
            "You're almost done! Answer the question above.  ",
            localize.localize("{{drill_reminder}}", "xx"),
        )
