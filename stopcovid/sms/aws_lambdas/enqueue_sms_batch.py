import logging
from typing import List

import rollbar

from stopcovid.dialog.models.events import batch_from_dict, DialogEventBatch, DialogEvent
from stopcovid.utils import dynamodb as dynamodb_utils


from stopcovid.sms.enqueue_outbound_sms import enqueue_outbound_sms_commands
from stopcovid.utils.logging import configure_logging
from stopcovid.utils.rollbar import configure_rollbar
from stopcovid.utils.verify_deploy_stage import verify_deploy_stage

configure_logging()
configure_rollbar()


@rollbar.lambda_function
def handler(event: dict, context: dict) -> dict:
    verify_deploy_stage()
    event_batches: List[DialogEventBatch] = [
        batch_from_dict(dynamodb_utils.deserialize(record["dynamodb"]["NewImage"]))
        for record in event["Records"]
        if record["dynamodb"].get("NewImage")
    ]

    dialog_events: List[DialogEvent] = []
    for batch in event_batches:
        for dialog_event in batch.events:
            dialog_events.append(dialog_event)

    enqueue_outbound_sms_commands(dialog_events)
    for batch in event_batches:
        logging.info(f"Enqueue SMS commands for {batch.phone_number} at seq {batch.seq}")

    return {"statusCode": 200}
