import unittest
from decimal import Decimal
import os

import requests_mock

from stopcovid.dialog.registration import DefaultRegistrationValidator, CodeValidationPayload


class TestRegistration(unittest.TestCase):
    def setUp(self) -> None:
        self.url = "https://foo"
        self.key = "access-key"

        os.environ["REGISTRATION_VALIDATION_URL"] = "www.foo.com"

    def test_invalid_code(self):
        with requests_mock.Mocker() as m:
            m.post(
                self.url, json={"valid": False, "is_demo": False, "account_info": None},
            )
            payload = DefaultRegistrationValidator().validate_code(
                "foo", url=self.url, key=self.key
            )

        self.assertFalse(payload.valid)

    def test_demo_code(self):
        with requests_mock.Mocker() as m:
            m.post(
                self.url,
                json={
                    "valid": "True",
                    "is_demo": "True",
                    "account_info": {
                        "employer_id": 165,
                        "employer_name": "Kai's Crab Shack",
                        "unit_id": 429,
                        "unit_name": "Kitchen",
                    },
                },
            )
            payload = DefaultRegistrationValidator().validate_code(
                "foo", url=self.url, key=self.key
            )

        self.assertTrue(payload.valid)
        self.assertTrue(payload.is_demo)

    def test_valid_non_demo_code(self):
        with requests_mock.Mocker() as m:
            m.post(
                self.url,
                json={
                    "valid": "True",
                    "is_demo": "False",
                    "account_info": {
                        "employer_id": 165,
                        "employer_name": "Kai's Crab Shack",
                        "unit_id": 429,
                        "unit_name": "Kitchen",
                    },
                },
            )
            payload = DefaultRegistrationValidator().validate_code(
                "foo", url=self.url, key=self.key
            )

        self.assertTrue(payload.valid)
        self.assertFalse(payload.is_demo)
        self.assertEqual(
            {
                "employer_id": 165,
                "employer_name": "Kai's Crab Shack",
                "unit_id": 429,
                "unit_name": "Kitchen",
            },
            payload.account_info,
        )

    def test_cache_results(self):
        with requests_mock.Mocker() as m:
            m.post(
                self.url,
                json={
                    "valid": "True",
                    "is_demo": "False",
                    "account_info": {"employer_id": 165, "unit_id": 429},
                },
            )
            validator = DefaultRegistrationValidator()
            validator.validate_code("foo", url=self.url, key=self.key)
            validator.validate_code("foo", url=self.url, key=self.key)
            self.assertEqual(1, m.call_count)

    def test_code_validation_payload_json_serializable(self):
        payload = CodeValidationPayload(
            valid="True",
            is_demo="False",
            account_info={"employer_id": Decimal(12), "unit_id": Decimal(1)},
        )
        self.assertEqual(
            payload.dict(),
            {"valid": True, "is_demo": False, "account_info": {"employer_id": 12, "unit_id": 1},},
        )

        # json serialization doesnt blow up
        payload.json()
