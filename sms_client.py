import argparse
from threading import Thread
import json
import os

from stopcovid.utils.boto3 import get_boto3_client
from stopcovid.dialog.command_stream.publish import CommandPublisher


GREEN = "\033[92m"
END_COLOR = "\033[0m"
QUEUE_URL_PATH = "/000000000000/outbound-sms-dlq-local.fifo"


parser = argparse.ArgumentParser(
    description="Simulate a text message client via localstack",
    epilog="Example use: `python sms_client.py http://localhost:4566 +15552345678`",
)
parser.add_argument("localstack", type=str, help="Host of running localstack instance")
parser.add_argument("phone", type=str, help="Phone number to send & receive messages from")


def read_messages(phone: str, localstack: str) -> None:
    sqs = get_boto3_client("sqs")
    queue_url = f"{localstack}{QUEUE_URL_PATH}"
    while True:
        res = sqs.receive_message(QueueUrl=queue_url)
        messages = res.get("Messages")
        if messages:
            for message in messages:
                body = json.loads(message["Body"])
                phone_number = body["phone_number"]
                if phone_number == phone:
                    print(GREEN)
                    print(f"Inbound to {phone_number}:")
                    for m in body["messages"]:
                        print(m["body"])
                        if m["media_url"]:
                            print(m["media_url"])
                    print(END_COLOR)
                    sqs.delete_message(QueueUrl=queue_url, ReceiptHandle=message["ReceiptHandle"])


def send_messages(phone: str) -> None:
    while True:
        message = input(f"Send a message as {phone}:\n")
        print(GREEN)
        print(f"Outbound from {phone}:")
        print(message)
        print(END_COLOR)
        CommandPublisher().publish_process_sms_command(phone, message, {})


def main() -> None:
    args = parser.parse_args()
    if os.environ.get("STAGE") != "local":
        print("Not local environment; exiting")
        return
    thread_1 = Thread(
        target=read_messages,
        args=(
            args.phone,
            args.localstack,
        ),
    )
    thread_2 = Thread(target=send_messages, args=(args.phone,))
    thread_1.start()
    thread_2.start()
    thread_2.join()


if __name__ == "__main__":
    main()
