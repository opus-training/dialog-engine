import boto3
from time import sleep
import json
import os
import logging

from stopcovid.utils.logging import configure_logging

from twilio.rest import Client


class SystemTest:
    def __init__(self):
        sqs = boto3.resource("sqs")
        self.queue = sqs.get_queue_by_name(QueueName="system-test-dev")
        self.twilio_client = Client(
            os.environ["TWILIO_ACCOUNT_SID"], os.environ["TWILIO_AUTH_TOKEN"]
        )
        self.test_complete = False
        self.SYSTEM_TEST_PHONE_NUMBER = os.environ["SYSTEM_TEST_PHONE_NUMBER"]
        self.DEV_PHONE_NUMBER = os.environ["DEV_PHONE_NUMBER"]

    def respond(self, body):
        logging.info(f"Responding: {body}")
        self.twilio_client.messages.create(
            to=self.DEV_PHONE_NUMBER, from_=self.SYSTEM_TEST_PHONE_NUMBER, body=body
        )

    def _handle_response(self, text):
        lowered_text = text.lower()

        if "choose your language" in lowered_text:
            self.respond("en")

        if "text me the word go" in lowered_text:
            self.test_complete = True

    def execute(self):
        self.respond("stopcovid")
        idle_count = 0
        while not self.test_complete:
            if idle_count > 5:
                raise RuntimeError("System is not responding in time.")

            messages = self.queue.receive_messages(WaitTimeSeconds=1)
            if messages:
                idle_count = 0
                for message in messages:
                    sms = json.loads(message.body)
                    text = sms["Body"]
                    logging.info(f"Received: {text}")
                    self._handle_response(text)
                    message.delete()
            else:
                idle_count += 1

            sleep(1)
        logging.info("System test complete")


if __name__ == "__main__":
    configure_logging()
    SystemTest().execute()
