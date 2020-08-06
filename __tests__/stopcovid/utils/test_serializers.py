import unittest
import uuid
from datetime import date, datetime
from enum import Enum

from pytz import UTC

from stopcovid.utils.dynamodb import serialize


class TestEnum(Enum):
    Key = "Val"


class SerializerTest(unittest.TestCase):
    def test_serializer(self):
        a_dict = {
            "datetime": datetime.now(UTC),
            "date": date.today(),
            "float": 1.234,
            "uuid": uuid.uuid4(),
            "enum": TestEnum.Key,
            "string": "abcdefg",
            "int": 432,
            "none": None,
            "list": [1, 2, 3, 3],
            "dict": {"a": "b"},
        }
        expected = {
            "datetime": {"S": "2020-08-06T21:11:00.004223+00:00"},
            "date": {"S": "2020-08-06"},
            "float": {"N": "1.234"},
            "uuid": {"S": "7fb67b15-5faf-488c-9e4a-c16978b9ce9d"},
            "enum": {"S": "Val"},
            "string": {"S": "abcdefg"},
            "int": {"N": "432"},
            "none": {"NULL": True},
            "list": {"L": [{"N": "1"}, {"N": "2"}, {"N": "3"}, {"N": "3"}]},
            "dict": {"M": {"a": {"S": "b"}}},
        }
        self.assertEqual(serialize(a_dict), expected)
