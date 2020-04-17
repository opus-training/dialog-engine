import logging
from stopcovid.utils import dynamodb as dynamodb_utils

from stopcovid.drill_progress.initiation import DrillInitiator
from stopcovid.drill_progress.drill_progress import DrillProgressSchema

from stopcovid.utils.logging import configure_logging
from stopcovid.utils.verify_deploy_stage import verify_deploy_stage

configure_logging()


def handler(event, context):
    verify_deploy_stage()
    drill_progresses_to_schedule = {}
    for record in event["Records"]:
        if record["eventName"] == "REMOVE":
            item = dynamodb_utils.deserialize(record["dynamodb"]["OldImage"])
            drill_progresses_to_schedule[item["idempotency_key"]] = DrillProgressSchema().load(
                item["drill_progress"]
            )
    initiator = DrillInitiator()

    for idempotency_key, drill_progress in drill_progresses_to_schedule.items():
        slug = drill_progress.next_drill_slug_to_trigger()
        if slug is None:
            logging.warning(
                f"Got a request to trigger drill_slug=None "
                f"for {drill_progress.phone_number}. Ignoring."
            )
            continue
        initiator.trigger_drill_if_not_stale(drill_progress.phone_number, slug, idempotency_key)

    return {"statusCode": 200}
