from decimal import Decimal
from enum import Enum
from datetime import datetime, date
from uuid import UUID

from boto3.dynamodb.types import TypeSerializer, TypeDeserializer


def serialize(a_dict):
    for key, val in a_dict.items():
        if isinstance(val, float):
            a_dict[key] = Decimal(str(val))
        elif isinstance(val, Enum):
            a_dict[key] = val.value
        elif isinstance(val, (datetime, date)):
            a_dict[key] = val.isoformat()
        elif isinstance(val, UUID):
            a_dict[key] = str(val)

    serializer = TypeSerializer()
    return {k: serializer.serialize(v) for k, v in a_dict.items()}


def deserialize(a_dict):
    deserializer = TypeDeserializer()
    return {k: deserializer.deserialize(v) for k, v in a_dict.items()}
