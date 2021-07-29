from typing import cast

import os
import json

from stopcovid.sms.types import OutboundPayload
from stopcovid.utils.boto3 import get_boto3_client


def publish_outbound_sms(payload: OutboundPayload) -> dict:
    kinesis = get_boto3_client("kinesis")
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
