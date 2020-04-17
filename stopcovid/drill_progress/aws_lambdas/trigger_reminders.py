from stopcovid.drill_progress.trigger_reminders import ReminderTriggerer

from stopcovid.utils.logging import configure_logging
from stopcovid.utils.verify_deploy_stage import verify_deploy_stage

configure_logging()


def handler(event, context):
    verify_deploy_stage()
    ReminderTriggerer().trigger_reminders()

    return {"statusCode": 200}
