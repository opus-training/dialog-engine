import json
import os
import uuid
from abc import ABC, abstractmethod
from typing import Any

import boto3

from stopcovid.utils import dynamodb as dynamodb_utils
from .models.state import DialogState
from .models.events import DialogEventBatch, batch_from_dict


class DialogRepository(ABC):
    @abstractmethod
    def fetch_dialog_state(self, phone_number: str) -> DialogState:
        pass

    @abstractmethod
    def persist_dialog_state(
        self, event_batch: DialogEventBatch, dialog_state: DialogState
    ) -> None:
        pass


class DynamoDBDialogRepository(DialogRepository):
    def __init__(self, table_name_suffix: str = None, **kwargs: Any) -> None:
        self.dynamodb = boto3.client("dynamodb", **kwargs)
        if table_name_suffix is None:
            table_name_suffix = os.getenv("DIALOG_TABLE_NAME_SUFFIX", "")
        self.table_name_suffix = table_name_suffix

    def event_batch_table_name(self) -> str:
        return (
            f"dialog-event-batches-{self.table_name_suffix}"
            if self.table_name_suffix
            else "dialog-event-batches"
        )

    def state_table_name(self) -> str:
        return (
            f"dialog-state-{self.table_name_suffix}" if self.table_name_suffix else "dialog-state"
        )

    def fetch_dialog_state(self, phone_number: str) -> DialogState:
        response = self.dynamodb.get_item(
            TableName=self.state_table_name(),
            Key={"phone_number": {"S": phone_number}},
            ConsistentRead=True,
        )
        if "Item" not in response:
            return DialogState(phone_number=phone_number, seq="0")
        dialog_dict = dynamodb_utils.deserialize(response["Item"])
        return DialogState(**dialog_dict)

    def fetch_dialog_event_batch(self, phone_number: str, batch_id: uuid.UUID) -> DialogEventBatch:
        response = self.dynamodb.get_item(
            TableName=self.event_batch_table_name(),
            Key={"phone_number": {"S": phone_number}, "batch_id": {"S": str(batch_id)}},
            ConsistentRead=True,
        )
        dialog_dict = dynamodb_utils.deserialize(response["Item"])

        return batch_from_dict(dialog_dict)

    def persist_dialog_state(
        self, event_batch: DialogEventBatch, dialog_state: DialogState
    ) -> None:
        if event_batch.events:
            write_items = [
                {
                    "Put": {
                        "TableName": self.event_batch_table_name(),
                        "Item": dynamodb_utils.serialize(json.loads(event_batch.json())),
                    }
                },
                {
                    "Put": {
                        "TableName": self.state_table_name(),
                        "Item": dynamodb_utils.serialize(json.loads(dialog_state.json())),
                    }
                },
            ]
            self.dynamodb.transact_write_items(TransactItems=write_items)

    def ensure_tables_exist(self) -> None:
        # useful for testing but will likely be duplicated elsewhere

        # noinspection PyBroadException
        try:
            self.dynamodb.create_table(
                TableName=self.event_batch_table_name(),
                KeySchema=[
                    {"AttributeName": "phone_number", "KeyType": "HASH"},
                    {"AttributeName": "batch_id", "KeyType": "RANGE"},
                ],
                AttributeDefinitions=[
                    {"AttributeName": "phone_number", "AttributeType": "S"},
                    {"AttributeName": "batch_id", "AttributeType": "S"},
                    {"AttributeName": "created_time", "AttributeType": "S"},
                ],
                LocalSecondaryIndexes=[
                    {
                        "IndexName": "by_created_time",
                        "KeySchema": [
                            {"AttributeName": "phone_number", "KeyType": "HASH"},
                            {"AttributeName": "created_time", "KeyType": "RANGE"},
                        ],
                        "Projection": {"ProjectionType": "ALL"},
                    }
                ],
                BillingMode="PAY_PER_REQUEST",
            )

            self.dynamodb.create_table(
                TableName=self.state_table_name(),
                KeySchema=[{"AttributeName": "phone_number", "KeyType": "HASH"}],
                AttributeDefinitions=[{"AttributeName": "phone_number", "AttributeType": "S"}],
                BillingMode="PAY_PER_REQUEST",
            )
        except Exception:
            # table already exists, most likely
            pass
