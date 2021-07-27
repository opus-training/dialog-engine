from typing import cast

import boto3
import os
import json

from stopcovid.sms.types import OutboundPayload


def publish_outbound_sms(payload: OutboundPayload) -> dict:
    kinesis = boto3.client("kinesis", endpoint_url=f'http://{os.environ.get("LOCALSTACK_HOSTNAME")}:4566')
    stage = os.environ.get("STAGE")
    records = [
        {
            "Data": json.dumps(
                {
                    "type": "OUTBOUND_SMS",
                    "payload": payload.dict(),
                }
            ),
            "PartitionKey": payload.To,
        }
    ]

    return cast(dict, kinesis.put_records(Records=records, StreamName=f"message-log-{stage}"))
