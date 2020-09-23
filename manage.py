import argparse
import sys
import uuid
from typing import Dict, Iterator, List, Any
import json

import boto3

from stopcovid.dialog.models.events import batch_from_dict, DialogEventBatch
from stopcovid.utils import dynamodb as dynamodb_utils
from stopcovid.utils.logging import configure_logging

configure_logging()


def get_env(stage: str) -> Dict[str, str]:
    filename = {"dev": ".env.development", "prod": ".env.production"}[stage]
    with open(filename) as file:
        return {
            line_part[0].strip(): line_part[1].strip()
            for line_part in (line.split("=") for line in file.readlines())
        }


def handle_redrive_sqs(args: Any) -> None:
    sqs = boto3.resource("sqs")

    queue_configs = {
        "sms": {
            "queue": f"outbound-sms-{args.stage}.fifo",
            "dlq": f"outbound-sms-dlq-{args.stage}.fifo",
        },
        "drill-initiation": {
            "queue": f"drill-initiation-{args.stage}",
            "dlq": f"drill-initiation-dlq-{args.stage}",
        },
    }
    queue_config = queue_configs[args.queue]

    queue = sqs.get_queue_by_name(QueueName=queue_config["queue"])
    dlq = sqs.get_queue_by_name(QueueName=queue_config["dlq"])

    total_redriven = 0
    while True:
        messages = dlq.receive_messages(WaitTimeSeconds=1)
        if not messages:
            if args.dry_run:
                print(f"{total_redriven} total messages (dry run)")
            else:
                print(
                    f"Redrove {total_redriven} message{'s' if total_redriven != 1 else ''} "
                    f"from the dlq"
                )
            return
        if args.dry_run:
            for message in messages:
                print(message.body)
        else:
            entries = []
            for message in messages:
                entry = {
                    "MessageBody": message.body,
                    "MessageAttributes": message.message_attributes or {},
                    "Id": str(uuid.uuid4()),
                }
                if args.queue == "sms":
                    parsed_body = json.loads(message.body)
                    entry["MessageGroupId"] = parsed_body["phone_number"]
                    idempotency_key = parsed_body["idempotency_key"]
                    start_index = max(0, len(idempotency_key) - 128)
                    entry["MessageDeduplicationId"] = idempotency_key[start_index:]
                entries.append(entry)

            queue.send_messages(Entries=entries)
            for message in messages:
                message.delete()
        total_redriven += len(messages)


def handle_replay_sqs_failures(args: Any) -> None:
    sqs = boto3.resource("sqs")
    kinesis = boto3.client("kinesis")

    queue_name = f"{args.sqs_queue}-failures-{args.stage}"
    stream_name = f"{args.kinesis_stream}-{args.stage}"
    queue = sqs.get_queue_by_name(QueueName=queue_name)

    while True:
        print(f"Getting messages from {queue_name}...")
        messages = queue.receive_messages(WaitTimeSeconds=1)
        if not messages:
            print(f"Reached end of {queue_name}")
            return
        for message in messages:
            print(f"Message ID: {message.message_id}")
            print(json.dumps(json.loads(message.body), indent=4, sort_keys=True))
            if args.print_only:
                continue
            response = input(
                f"Re-publish message {message.message_id} to {stream_name}? (yes/no)\n"
            ).lower()
            if response in ["y", "yes"]:
                partition_key = input(f"What partition in {args.kinesis_stream}?\n").lower()
                records = [{"Data": message.body, "PartitionKey": partition_key}]
                print(
                    f"Re-publishing message {message.message_id} to {stream_name} at partition {partition_key}"
                )
                response = kinesis.put_records(StreamName=stream_name, Records=records)
                print(f"Deleting message {message.message_id}\n")
                message.delete()
            else:
                print(f"Skipping message {message.message_id}\n")


def _get_dialog_events(phone_number: str, stage: str) -> Iterator[DialogEventBatch]:
    dynamodb = boto3.client("dynamodb")
    table_name = f"dialog-event-batches-{stage}"
    args: Dict[str, str] = {}
    while True:
        result = dynamodb.query(
            TableName=table_name,
            IndexName="by_created_time",
            KeyConditionExpression="phone_number=:phone_number",
            ExpressionAttributeValues={":phone_number": {"S": phone_number}},
            **args,
        )
        for item in result["Items"]:
            yield batch_from_dict(dynamodb_utils.deserialize(item))
        if not result.get("LastEvaluatedKey"):
            break
        args["ExclusiveStartKey"] = result["LastEvaluatedKey"]


def get_all_users(args: Any) -> None:
    dynamodb = boto3.client("dynamodb")
    table_name = f"dialog-state-{args.stage}"
    args = {}
    while True:
        result = dynamodb.scan(TableName=table_name, **args)
        for item in result["Items"]:
            print(item["phone_number"]["S"])
        if not result.get("LastEvaluatedKey"):
            break
        args["ExclusiveStartKey"] = result["LastEvaluatedKey"]


def handle_show_stream_record(args: Any) -> None:
    kinesis = boto3.client("kinesis")
    stream_name = f"{args.kinesis_stream}-{args.stage}"
    shard_iterator = kinesis.get_shard_iterator(
        StreamName=stream_name,
        ShardId=args.shard_id,
        ShardIteratorType="AT_SEQUENCE_NUMBER",
        StartingSequenceNumber=args.seq,
    )
    response = kinesis.get_records(ShardIterator=shard_iterator["ShardIterator"], Limit=1)
    for record in response["Records"]:
        print(json.loads(record["Data"]))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--stage", choices=["dev", "prod"], required=True)
    subparsers = parser.add_subparsers(
        required=True, title="subcommands", description="valid subcommands"
    )
    sqs_parser = subparsers.add_parser(
        "redrive-sqs", description="Retry failures from an SQS queue"
    )
    sqs_parser.add_argument("queue", choices=["sms", "drill-initiation"])
    sqs_parser.add_argument("--dry_run", action="store_true")
    sqs_parser.set_defaults(func=handle_redrive_sqs)

    get_all_users_parser = subparsers.add_parser(
        "get-all-users", description="print out every user's phone number"
    )
    get_all_users_parser.set_defaults(func=get_all_users)

    show_stream_record_parser = subparsers.add_parser(
        "show-stream-record",
        description="Show the record at a particular sequence in a kinesis stream",
    )
    show_stream_record_parser.add_argument("--kinesis_stream")
    show_stream_record_parser.add_argument("--shard_id")
    show_stream_record_parser.add_argument("--seq")
    show_stream_record_parser.set_defaults(func=handle_show_stream_record)

    replay_sqs_failures_parser = subparsers.add_parser(
        "replay-sqs-failures",
        description="Interactively replay to a kinesis stream (or just view) messages from an SQS failure queue",
    )
    replay_sqs_failures_parser.set_defaults(func=handle_replay_sqs_failures)
    replay_sqs_failures_parser.add_argument("--sqs_queue")
    replay_sqs_failures_parser.add_argument("--kinesis_stream")
    replay_sqs_failures_parser.add_argument("--print_only", action="store_true")

    args = parser.parse_args(sys.argv if len(sys.argv) == 1 else None)
    args.func(args)


if __name__ == "__main__":
    main()
