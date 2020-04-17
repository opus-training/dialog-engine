from stopcovid.sms.types import SMSBatchSchema
from stopcovid.sms.send_sms import send_sms_batches
from stopcovid.utils.logging import configure_logging
from stopcovid.utils.verify_deploy_stage import verify_deploy_stage

configure_logging()


def handler(event, context):
    verify_deploy_stage()
    batches = [SMSBatchSchema().loads(record["body"]) for record in event["Records"]]
    send_sms_batches(batches)
    return {"statusCode": 200}
