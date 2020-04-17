from stopcovid.dialog.models.events import batch_from_dict
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

    return {"statusCode": 200}
