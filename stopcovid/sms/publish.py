from typing import cast

import boto3
import os
import json


def publish_outbound_sms(twilio_responses: list) -> dict:
    kinesis = boto3.client("kinesis")
    stage = os.environ.get("STAGE")
    records = [
        {
            "Data": json.dumps(
                {
                    "type": "OUTBOUND_SMS",
                    "payload": {
                        "MessageSid": response.sid,
                        "To": response.to,
                        "Body": response.body,
                        "MessageStatus": response.status,
                    },
                }
            ),
            "PartitionKey": response.to,
        }
        for response in twilio_responses
    ]

    return cast(dict, kinesis.put_records(Records=records, StreamName=f"message-log-{stage}"))
