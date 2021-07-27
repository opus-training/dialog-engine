import boto3
import os
from typing import List

import rollbar

from stopcovid.dialog.models.events import batch_from_dict, DialogEventBatch
from stopcovid.utils import dynamodb as dynamodb_utils
from stopcovid.utils.logging import configure_logging
from stopcovid.utils.rollbar import configure_rollbar
from stopcovid.utils.verify_deploy_stage import verify_deploy_stage

configure_logging()
configure_rollbar()


@rollbar.lambda_function  # type: ignore
def handler(event: dict, context: dict) -> dict:
    verify_deploy_stage()
    event_batches = [
        batch_from_dict(dynamodb_utils.deserialize(record["dynamodb"]["NewImage"]))
        for record in event["Records"]
        if record["dynamodb"].get("NewImage")
    ]

    _publish_event_batches_to_kinesis(event_batches)

    return {"statusCode": 200}


def _publish_event_batches_to_kinesis(event_batches: List[DialogEventBatch]) -> None:
    kinesis = boto3.client("kinesis", endpoint_url=f'http://{os.environ.get("LOCALSTACK_HOSTNAME")}:4566')
    stage = os.environ.get("STAGE")
    stream_name = f"dialog-event-batches-{stage}"
    records = [
        {
            "PartitionKey": event_batch.phone_number,
            "Data": event_batch.json(),
        }
        for event_batch in event_batches
    ]
    response = kinesis.put_records(StreamName=stream_name, Records=records)
    if response.get("FailedRecordCount"):
        rollbar.report_exc_info(extra_data=response)
