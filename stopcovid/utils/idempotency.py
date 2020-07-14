import datetime
import os

import boto3

from stopcovid.utils import dynamodb as dynamodb_utils


class IdempotencyChecker:
    # a best effort idempotency checker
    # double processing of an item is still possible if the underlying operation
    # succeeds and record_as_processed() fails

    def __init__(self, **kwargs):
        self.dynamodb = boto3.client("dynamodb", **kwargs)
        self.stage = os.environ.get("STAGE")

    def record_as_processed(
        self, idempotency_key: str, realm: str, expiration_minutes: int
    ):
        self.dynamodb.put_item(
            TableName=self._table_name(),
            Item=dynamodb_utils.serialize(
                {
                    "idempotency_key": idempotency_key,
                    "realm": realm,
                    "expiration_ts": int(
                        (
                            self._now() + datetime.timedelta(minutes=expiration_minutes)
                        ).timestamp()
                    ),
                }
            ),
        )

    def already_processed(self, idempotency_key: str, realm: str) -> bool:
        response = self.dynamodb.get_item(
            TableName=self._table_name(),
            Key={"idempotency_key": {"S": idempotency_key}, "realm": {"S": realm}},
            ConsistentRead=True,
        )
        return "Item" in response

    def _table_name(self):
        return f"idempotency-checks-{self.stage}"

    @staticmethod
    def _now() -> datetime.datetime:
        return datetime.datetime.now(tz=datetime.timezone.utc)

    def drop_and_recreate_table(self):
        if self.stage != "test":
            raise RuntimeError("Method unsafe to run in non test environment")
        try:
            self.dynamodb.delete_table(TableName=self._table_name())
        except Exception:
            # Table already does not exist
            pass

        self.dynamodb.create_table(
            TableName=self._table_name(),
            KeySchema=[
                {"AttributeName": "idempotency_key", "KeyType": "HASH"},
                {"AttributeName": "realm", "KeyType": "RANGE"},
            ],
            AttributeDefinitions=[
                {"AttributeName": "idempotency_key", "AttributeType": "S"},
                {"AttributeName": "realm", "AttributeType": "S"},
            ],
            BillingMode="PAY_PER_REQUEST",
        )
        self.dynamodb.update_time_to_live(
            TableName=self._table_name(),
            TimeToLiveSpecification={"AttributeName": "expiration_ts", "Enabled": True},
        )
