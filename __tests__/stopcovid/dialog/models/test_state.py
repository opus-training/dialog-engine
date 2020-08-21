import json
import unittest

from stopcovid.dialog.models.state import UserProfile


class TestUserProfileSerialization(unittest.TestCase):
    def test_serialize_and_deserialize_language(self):
        profile = UserProfile(validated=True, language="English")
        self.assertEqual("en", profile.language)
        serialized = profile.json()
        deserialized = UserProfile(**json.loads(serialized))
        self.assertEqual("en", deserialized.language)

    def test_serialize_and_deserialize_no_language(self):
        profile = UserProfile(validated=True)
        self.assertIsNone(profile.language)
        serialized = profile.json()
        deserialized = UserProfile(**json.loads(serialized))
        self.assertIsNone(deserialized.language)

    def test_user_profile_ignores_additional_fields(self):
        profile = UserProfile(validated=True, language="en", foo="bar", joel="embiid")
        self.assertEqual("en", profile.language)
        serialized = profile.json()
        deserialized = UserProfile(**json.loads(serialized))
        self.assertEqual("en", deserialized.language)
