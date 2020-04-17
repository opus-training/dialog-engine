import uuid
from typing import List

from sqlalchemy import Table, MetaData, Column, String, select, insert, DateTime, func
from sqlalchemy.dialects.postgresql import UUID

from sqlalchemy.exc import DatabaseError

from stopcovid import db

metadata = MetaData()
messages = Table(
    "messages",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True),
    Column("created_at", DateTime(timezone=True), server_default=func.now()),
    Column("twilio_message_id", String, nullable=False, index=True, unique=True),
    Column("from_number", String, nullable=True, index=True),
    Column("to_number", String, nullable=False, index=True),
    Column("body", String, nullable=True, index=True),
    Column("status", String, nullable=False, index=True),
)


class MessageRepository:
    def __init__(self, engine_factory=db.get_sqlalchemy_engine):
        self.engine_factory = engine_factory
        self.engine = engine_factory()

    def upsert_messages(self, values: List[dict]):
        def _prep_insert(obj):
            obj["id"] = uuid.uuid4()
            return obj

        with self.engine.connect() as connection:
            with connection.begin():
                for value in values:
                    message_id = value["twilio_message_id"]
                    result = connection.execute(
                        select([messages]).where(messages.c.twilio_message_id == message_id)
                    )
                    row = result.fetchone()
                    if row is None:
                        connection.execute(insert(messages).values(**_prep_insert(value)))
                    else:
                        current_status = row["status"]
                        if self._is_more_recent(current_status, value["status"]):
                            value["status"] = current_status

                        connection.execute(
                            messages.update()
                            .where(messages.c.twilio_message_id == message_id)
                            .values(**value)
                        )

    def _is_more_recent(self, status1: str, status2: str) -> bool:
        status_ranks = {
            "accepted": 0,
            "queued": 1,
            "sent": 2,
            "delivered": 3,
            "undelivered": 3,
            "failed": 3,
            "received": 3,
        }
        return status_ranks[status1.lower()] > status_ranks[status2.lower()]

    def _get_messages(self):
        results = self.engine.execute(select([messages]))
        return [row for row in results]

    def drop_and_recreate_tables_testing_only(self):
        if self.engine_factory == db.get_sqlalchemy_engine:
            raise ValueError("This function should not be called against databases in RDS")
        try:
            messages.drop(bind=self.engine)
        except DatabaseError:
            pass

        metadata.create_all(bind=self.engine)
