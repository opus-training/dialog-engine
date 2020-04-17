import argparse
import sys
import uuid
from typing import Iterator
import json

import boto3
from sqlalchemy import create_engine

from stopcovid.dialog.models.events import batch_from_dict, DialogEventBatch
from stopcovid.drill_progress.drill_progress import DrillProgressRepository
from stopcovid.utils import dynamodb as dynamodb_utils
from stopcovid.utils.logging import configure_logging
from stopcovid.sms.message_log.types import LogMessageCommandSchema
from stopcovid.sms.message_log.message_log import log_messages

configure_logging()


def get_env(stage: str):
    filename = {"dev": ".env.development", "prod": ".env.production"}[stage]
    with open(filename) as file:
        return {
            line_part[0].strip(): line_part[1].strip()
            for line_part in (line.split("=") for line in file.readlines())
        }


def handle_redrive_sqs(args):
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


def _get_dialog_events(phone_number: str, stage: str) -> Iterator[DialogEventBatch]:
    dynamodb = boto3.client("dynamodb")
    table_name = f"dialog-event-batches-{stage}"
    args = {}
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


def db_engine_factory(stage: str):
    environment = get_env(stage)

    def engine_factory():
        return create_engine(
            "postgresql+auroradataapi://:@/postgres",
            connect_args=dict(
                aurora_cluster_arn=environment["DB_CLUSTER_ARN"],
                secret_arn=environment["DB_SECRET_ARN"],
            ),
        )

    return engine_factory


def get_drill_progress_repo(stage: str) -> DrillProgressRepository:
    return DrillProgressRepository(db_engine_factory(stage))


def rebuild_drill_progress(args):
    drill_progress_repo = get_drill_progress_repo(args.stage)
    user_id = drill_progress_repo.delete_user_info(args.phone_number)
    for batch in _get_dialog_events(args.phone_number, args.stage):
        print(f"{batch.batch_id}: {batch.seq}")
        drill_progress_repo.update_user(batch, ensure_user_id=user_id)
    print("Done")


def show_drill_progress(args):
    drill_progress_repo = get_drill_progress_repo(args.stage)
    user = drill_progress_repo.get_user_for_phone_number(args.phone_number)
    if not user:
        print("User not found")
    progress = drill_progress_repo.get_progress_for_user(args.phone_number)
    print(f"{args.phone_number}:")
    print(f"\tid={user.user_id}")
    print(f"\tseq={user.seq}")
    print(f"\tprofile={user.profile}")
    print(f"\tlast_interacted_time={user.last_interacted_time.isoformat()}")
    print(f"\tfirst_unstarted_drill_slug={progress.first_unstarted_drill_slug}")
    print(f"\tfirst_incomplete_drill_slug={progress.first_incomplete_drill_slug}")


def get_all_users(args):
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


def replay_message_stream(args):
    kinesis = boto3.client("kinesis")
    stream_name = f"message-log-{args.stage}"
    shards = kinesis.list_shards(StreamName=stream_name)["Shards"]
    engine_factory = db_engine_factory(args.stage)
    for shard in shards:
        shard_id = shard["ShardId"]
        shard_iterator = kinesis.get_shard_iterator(
            StreamName=stream_name, ShardId=shard_id, ShardIteratorType="TRIM_HORIZON"
        )
        next_shard_iterator = shard_iterator["ShardIterator"]
        milliseconds_from_tip = 24 * 60 * 60 * 1000
        while milliseconds_from_tip > 0:
            response = kinesis.get_records(ShardIterator=next_shard_iterator)
            next_shard_iterator = response["NextShardIterator"]
            milliseconds_from_tip = response["MillisBehindLatest"]
            raw_commands = [json.loads(record["Data"]) for record in response["Records"]]
            commands = [
                LogMessageCommandSchema().load(
                    {"command_type": command["type"], "payload": command["payload"]}
                )
                for command in raw_commands
            ]
            print(
                f"{milliseconds_from_tip} from tip of shard {shard_id}. Handling {len(commands)} commands"
            )
            if commands:
                log_messages(commands, engine_factory=engine_factory)


def show_command(args):
    kinesis = boto3.client("kinesis")
    stream_name = f"command-stream-{args.stage}"
    shard_iterator = kinesis.get_shard_iterator(
        StreamName=stream_name,
        ShardId=args.shard_id,
        ShardIteratorType="AT_SEQUENCE_NUMBER",
        StartingSequenceNumber=args.seq,
    )
    response = kinesis.get_records(ShardIterator=shard_iterator["ShardIterator"], Limit=1)
    for record in response["Records"]:
        print(json.loads(record["Data"]))


def main():
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

    rebuild_progress_parser = subparsers.add_parser(
        "rebuild-drill-progress",
        description="rebuild drill progress information for the user in aurora",
    )
    rebuild_progress_parser.add_argument("phone_number")
    rebuild_progress_parser.set_defaults(func=rebuild_drill_progress)

    show_progress_parser = subparsers.add_parser(
        "show-drill-progress", description="print information on a user's drill progress"
    )
    show_progress_parser.add_argument("phone_number")
    show_progress_parser.set_defaults(func=show_drill_progress)

    get_all_users_parser = subparsers.add_parser(
        "get-all-users", description="print out every user's phone number"
    )
    get_all_users_parser.set_defaults(func=get_all_users)

    replay_message_stream_parser = subparsers.add_parser(
        "replay-message-stream", description="Replay all messages in the message-log stream"
    )
    replay_message_stream_parser.set_defaults(func=replay_message_stream)

    show_command_parser = subparsers.add_parser(
        "show-command",
        description="Show the command at a particular sequence in the command stream",
    )
    show_command_parser.add_argument("--shard_id")
    show_command_parser.add_argument("--seq")
    show_command_parser.set_defaults(func=show_command)

    args = parser.parse_args(sys.argv if len(sys.argv) == 1 else None)
    args.func(args)


if __name__ == "__main__":
    main()
