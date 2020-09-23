import json
from base64 import b64decode
from typing import List, cast


def get_payload_from_kinesis_record(record: dict) -> dict:
    payload_bytes = b64decode(record["kinesis"]["data"])
    return cast(dict, json.loads(payload_bytes.decode("UTF-8")))


def get_payloads_from_kinesis_event(kinesis_payload: dict) -> List[dict]:
    records = kinesis_payload["Records"]
    return [get_payload_from_kinesis_record(record) for record in records]
