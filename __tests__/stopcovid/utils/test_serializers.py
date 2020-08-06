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
        a_datetime = datetime.now(UTC)
        a_date = date.today()
        a_uuid = uuid.uuid4()
        a_dict = {
            "datetime": a_datetime,
            "date": a_date,
            "float": 1.234,
            "uuid": a_uuid,
            "enum": TestEnum.Key,
            "string": "abcdefg",
            "int": 432,
            "none": None,
            "list": [1, 2, 3, 3],
            "dict": {"a": "b"},
        }
        expected = {
            "datetime": {"S": a_datetime.isoformat()},
            "date": {"S": a_date.isoformat()},
            "float": {"N": "1.234"},
            "uuid": {"S": str(a_uuid)},
            "enum": {"S": "Val"},
            "string": {"S": "abcdefg"},
            "int": {"N": "432"},
            "none": {"NULL": True},
            "list": {"L": [{"N": "1"}, {"N": "2"}, {"N": "3"}, {"N": "3"}]},
            "dict": {"M": {"a": {"S": "b"}}},
        }
        self.assertEqual(serialize(a_dict), expected)
