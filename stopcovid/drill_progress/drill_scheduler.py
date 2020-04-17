import datetime
import os
from dataclasses import dataclass
import random
from typing import Iterable, Optional

import boto3
from stopcovid.utils import dynamodb as dynamodb_utils

from stopcovid.drill_progress.drill_progress import DrillProgress, DrillProgressSchema


@dataclass
class ScheduledDrill:
    idempotency_key: str
    drill_progress: DrillProgress
    trigger_ts: int


class DrillScheduler:
    def __init__(self, **kwargs):
        self.dynamodb = boto3.client("dynamodb", **kwargs)
        self.stage = os.environ.get("STAGE")

    def schedule_drills_to_trigger(
        self, drill_progresses: Iterable[DrillProgress], distribute_over_minutes: int
    ):
        now = self._now()
        for drill_progress in drill_progresses:
            delay_seconds = random.randint(1, distribute_over_minutes * 60)
            trigger_time = now + datetime.timedelta(seconds=delay_seconds)
            idempotency_key = self._idempotency_key(drill_progress)
            self.dynamodb.put_item(
                TableName=self._table_name(),
                Item=dynamodb_utils.serialize(
                    {
                        "phone_number": drill_progress.phone_number,
                        "idempotency_key": idempotency_key,
                        "trigger_ts": int(trigger_time.timestamp()),
                        "drill_progress": drill_progress.to_dict(),
                    }
                ),
            )

    def get_scheduled_drill(self, drill_progress: DrillProgress) -> Optional[ScheduledDrill]:
        response = self.dynamodb.get_item(
            TableName=self._table_name(),
            Key={
                "phone_number": {"S": drill_progress.phone_number},
                "idempotency_key": {"S": self._idempotency_key(drill_progress)},
            },
            ConsistentRead=True,
        )
        if "Item" not in response:
            return None
        dialog_dict = dynamodb_utils.deserialize(response["Item"])
        return ScheduledDrill(
            idempotency_key=dialog_dict["idempotency_key"],
            trigger_ts=int(dialog_dict["trigger_ts"]),
            drill_progress=DrillProgressSchema().load(dialog_dict["drill_progress"]),
        )

    def _table_name(self) -> str:
        return f"drill-trigger-schedule-{self.stage}"

    @staticmethod
    def _now() -> datetime.datetime:
        return datetime.datetime.now(tz=datetime.timezone.utc)

    @staticmethod
    def _idempotency_key(drill_progress: DrillProgress) -> str:
        return f"scheduled-{drill_progress.next_drill_slug_to_trigger()}"

    def ensure_tables_exist(self):
        try:
            self.dynamodb.create_table(
                TableName=self._table_name(),
                KeySchema=[
                    {"AttributeName": "phone_number", "KeyType": "HASH"},
                    {"AttributeName": "idempotency_key", "KeyType": "RANGE"},
                ],
                AttributeDefinitions=[
                    {"AttributeName": "phone_number", "AttributeType": "S"},
                    {"AttributeName": "idempotency_key", "AttributeType": "S"},
                ],
                BillingMode="PAY_PER_REQUEST",
            )
            self.dynamodb.update_time_to_live(
                TableName=self._table_name(),
                TimeToLiveSpecification={"AttributeName": "trigger_ts", "Enabled": True},
            )
        except Exception:
            # table already exists, most likely
            pass
