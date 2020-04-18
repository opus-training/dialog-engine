import unittest

from stopcovid.dialog.models.state import UserProfile, UserProfileSchema


class TestUserProfileSerialization(unittest.TestCase):
    def test_serialize_and_deserialize_language(self):
        profile = UserProfile(validated=True, language="English")
        self.assertEqual("English", profile.language)
        serialized = UserProfileSchema().dumps(profile)
        deserialized = UserProfileSchema().loads(serialized)
        self.assertEqual("en", deserialized.language)

    def test_serialize_and_deserialize_no_language(self):
        profile = UserProfile(validated=True)
        self.assertIsNone(profile.language)
        serialized = UserProfileSchema().dumps(profile)
        deserialized = UserProfileSchema().loads(serialized)
        self.assertIsNone(deserialized.language)
