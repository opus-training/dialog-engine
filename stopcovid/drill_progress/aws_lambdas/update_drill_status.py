import boto3
import os
from typing import List
import json

from stopcovid.dialog.models.events import batch_from_dict, DialogEventBatch
from stopcovid.utils import dynamodb as dynamodb_utils
from stopcovid.drill_progress import status
from stopcovid.utils.logging import configure_logging
from stopcovid.utils.verify_deploy_stage import verify_deploy_stage

configure_logging()


def handler(event, context):
    verify_deploy_stage()
    event_batches = [
        batch_from_dict(dynamodb_utils.deserialize(record["dynamodb"]["NewImage"]))
        for record in event["Records"]
        if record["dynamodb"].get("NewImage")
    ]

    status.handle_dialog_event_batches(event_batches)
    _publish_event_batches_to_kinesis(event_batches)

    return {"statusCode": 200}


def _publish_event_batches_to_kinesis(event_batches: List[DialogEventBatch]):
    kinesis = boto3.client("kinesis")
    stage = os.environ.get("stage")
    stream_name = f"dialog-event-batches-{stage}"
    records = [
        {"PartitionKey": event_batch.phone_number, "Data": json.dumps(event_batch.to_dict())}
        for event_batch in event_batches
    ]
    kinesis.put_records(StreamName=stream_name, Records=records)
