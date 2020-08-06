import unittest

from stopcovid.dialog.models.state import UserProfile
from stopcovid.dialog.registration import AccountInfo


class TestUserProfile(unittest.TestCase):
    def test_json_serialize_user_profile_handles_decimals_and_uuids(self):
        profile = UserProfile(
            validated=True,
            is_demo=True,
            name="Devin Booker",
            language="en",
            account_info=AccountInfo(
                employer_id=1, unit_id=1, employer_name="employer_name", unit_name="unit_name",
            ),
        )
        expected = {
            "validated": True,
            "is_demo": True,
            "name": "Devin Booker",
            "language": "en",
            "account_info": {
                "employer_id": 1,
                "unit_id": 1,
                "employer_name": "employer_name",
                "unit_name": "unit_name",
            },
            "opted_out": False,
        }

        self.assertDictContainsSubset(expected, profile.dict())
