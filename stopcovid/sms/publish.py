import boto3
import os
import json


def publish_outbound_sms(twilio_responses: list):
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

    return kinesis.put_records(Records=records, StreamName=f"message-log-{stage}")
