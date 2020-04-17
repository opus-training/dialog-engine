import datetime
import logging
import uuid
from dataclasses import dataclass, field
from typing import Dict, Any, Optional, Iterator, Union, List

from marshmallow import fields, post_load, Schema
from sqlalchemy import (
    Table,
    MetaData,
    Column,
    String,
    ForeignKey,
    Boolean,
    DateTime,
    select,
    Integer,
    func,
    UniqueConstraint,
    Index,
    and_,
    exists,
    or_,
    insert,
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.exc import DatabaseError

from stopcovid import db
from ..dialog.models.events import (
    DrillStarted,
    ReminderTriggered,
    UserValidated,
    UserValidationFailed,
    CompletedPrompt,
    FailedPrompt,
    AdvancedToNextPrompt,
    DrillCompleted,
    OptedOut,
    NextDrillRequested,
    DialogEvent,
    DialogEventBatch,
)
from ..drills.drills import get_all_drill_slugs

metadata = MetaData()
users = Table(
    "users",
    metadata,
    Column("user_id", UUID, primary_key=True),
    Column("seq", String, nullable=False),
    Column("profile", JSONB, nullable=False),
    Column("last_interacted_time", DateTime(timezone=True), index=True),
)

phone_numbers = Table(
    "phone_numbers",
    metadata,
    Column("id", UUID, primary_key=True),
    Column("phone_number", String, nullable=False, unique=True),
    Column("user_id", UUID, ForeignKey("users.user_id"), nullable=False),
    Column("is_primary", Boolean, nullable=False),
)

drill_statuses = Table(
    "drill_statuses",
    metadata,
    Column("id", UUID, primary_key=True),
    Column("user_id", UUID, ForeignKey("users.user_id"), nullable=False),
    Column("drill_instance_id", UUID, nullable=True, index=True),
    Column("drill_slug", String, nullable=False),
    Column("place_in_sequence", Integer, nullable=False),
    Column("started_time", DateTime(timezone=True)),
    Column("completed_time", DateTime(timezone=True)),
    UniqueConstraint("user_id", "place_in_sequence"),
    UniqueConstraint("user_id", "drill_slug"),
    Index("user_id_started", "user_id", "started_time"),
    Index("user_id_completed", "user_id", "completed_time"),
)

drill_instances = Table(
    "drill_instances",
    metadata,
    Column("drill_instance_id", UUID, primary_key=True),
    Column("user_id", UUID, ForeignKey("users.user_id"), nullable=False),
    Column("phone_number", String, nullable=False),
    Column("drill_slug", String, nullable=False),
    Column("current_prompt_slug", String, nullable=True),
    Column("current_prompt_start_time", DateTime(timezone=True), nullable=True),
    Column("current_prompt_last_response_time", DateTime(timezone=True), nullable=True),
    Column("completion_time", DateTime(timezone=True), nullable=True),
    Column("is_valid", Boolean, nullable=False, default=True),
)


class DrillProgressSchema(Schema):
    phone_number = fields.String(required=True)
    user_id = fields.UUID(required=True)
    first_unstarted_drill_slug = fields.String(allow_none=True)
    first_incomplete_drill_slug = fields.String(allow_none=True)

    @post_load
    def make_drill_progress(self, data, **kwargs):
        return DrillProgress(**data)


@dataclass
class DrillProgress:
    phone_number: str
    user_id: uuid.UUID
    first_unstarted_drill_slug: Optional[str] = None
    first_incomplete_drill_slug: Optional[str] = None

    def next_drill_slug_to_trigger(self) -> Optional[str]:
        if self.first_unstarted_drill_slug:
            return self.first_unstarted_drill_slug
        return self.first_incomplete_drill_slug

    def to_dict(self):
        return DrillProgressSchema().dump(self)


@dataclass
class User:
    seq: str
    user_id: UUID = field(default_factory=uuid.uuid4)
    profile: Dict[str, Any] = field(default_factory=dict)
    last_interacted_time: Optional[datetime.datetime] = None


@dataclass
class PhoneNumber:
    phone_number: str
    user_id: UUID
    is_primary: bool = True
    id: UUID = field(default_factory=uuid.uuid4)


@dataclass
class DrillStatus:
    id: uuid.UUID
    user_id: uuid.UUID
    # Why are drill instance IDs nullable? We add a drill status row for each known drill before
    # any of them have started. At that time, the drill instance IDs haven't yet been created.
    drill_instance_id: Optional[uuid.UUID]
    drill_slug: str
    place_in_sequence: int
    started_time: datetime.datetime
    completed_time: datetime.datetime


@dataclass
class DrillInstance:
    drill_instance_id: uuid.UUID
    user_id: uuid.UUID
    phone_number: str
    drill_slug: str
    current_prompt_slug: Optional[str] = None
    current_prompt_start_time: Optional[datetime.datetime] = None
    current_prompt_last_response_time: Optional[datetime.datetime] = None
    completion_time: Optional[datetime.datetime] = None
    is_valid: bool = True


class DrillProgressRepository:
    def __init__(self, engine_factory=db.get_sqlalchemy_engine):
        self.engine_factory = engine_factory
        self.engine = engine_factory()

    def get_user(self, user_id: uuid.UUID) -> Optional[User]:
        result = self.engine.execute(
            select([users]).where(users.c.user_id == func.uuid(str(user_id)))
        )
        row = result.fetchone()
        if row is None:
            return None
        return User(
            user_id=uuid.UUID(row["user_id"]),
            profile=row["profile"],
            last_interacted_time=row["last_interacted_time"],
            seq=row["seq"],
        )

    def get_drill_status(self, user_id: uuid.UUID, drill_slug: str) -> Optional[DrillStatus]:
        result = self.engine.execute(
            select([drill_statuses]).where(
                and_(
                    drill_statuses.c.user_id == func.uuid(str(user_id)),
                    drill_statuses.c.drill_slug == drill_slug,
                )
            )
        )
        row = result.fetchone()
        if row is None:
            return None
        drill_instance_id = (
            uuid.UUID(row["drill_instance_id"]) if row["drill_instance_id"] else None
        )
        return DrillStatus(
            id=uuid.UUID(row["id"]),
            user_id=uuid.UUID(row["user_id"]),
            drill_instance_id=drill_instance_id,
            drill_slug=row["drill_slug"],
            place_in_sequence=row["place_in_sequence"],
            started_time=row["started_time"],
            completed_time=row["completed_time"],
        )

    def update_user(  # noqa: C901
        self, batch: DialogEventBatch, ensure_user_id: Optional[uuid.UUID] = None
    ) -> uuid.UUID:
        logging.info(f"Updating {batch.phone_number} at seq {batch.seq}")
        with self.engine.connect() as connection:
            with connection.begin():
                user = self.get_user_for_phone_number(batch.phone_number, connection)
                if user is not None and int(user.seq) >= int(batch.seq):
                    logging.info(
                        f"Ignoring batch at {batch.seq} because a more recent user exists "
                        f"(seq {user.seq})"
                    )
                    return user.user_id

                # also updates sequence number for the user, which won't be committed unless the
                # transaction succeeds
                user_id = self._create_or_update_user(batch, ensure_user_id, connection)

                for event in batch.events:
                    self._mark_interacted_time(user_id, event, connection)
                    if isinstance(event, UserValidated):
                        self._reset_drill_statuses(user_id, connection)
                        self._invalidate_prior_drills(user_id, connection)
                    elif isinstance(event, DrillStarted):
                        self._mark_drill_started(user_id, event, connection)
                        self._record_new_drill_instance(user_id, event, connection)
                    elif isinstance(event, DrillCompleted):
                        self._mark_drill_completed(event, connection)
                        self._mark_drill_instance_complete(event, connection)
                    elif isinstance(event, OptedOut):
                        if event.drill_instance_id is not None:
                            self._unmark_drill_started(event, connection)
                            self._invalidate_drill_instance(event.drill_instance_id, connection)
                    elif isinstance(event, CompletedPrompt):
                        self._update_current_prompt_response_time(event, connection)
                    elif isinstance(event, FailedPrompt):
                        self._update_current_prompt_response_time(event, connection)
                    elif isinstance(event, AdvancedToNextPrompt):
                        self._update_current_prompt(event, connection)
                    elif (
                        isinstance(event, ReminderTriggered)
                        or isinstance(event, UserValidationFailed)
                        or isinstance(event, NextDrillRequested)
                    ):
                        logging.info(f"Ignoring event of type {event.event_type}")
                    else:
                        raise ValueError(f"Unknown event type {event.event_type}")

                return user_id

    def get_progress_for_users_who_need_drills(self, inactivity_minutes) -> Iterator[DrillProgress]:
        ds1 = drill_statuses.alias()
        ds2 = drill_statuses.alias()
        time_threshold = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(
            minutes=inactivity_minutes
        )
        stmt = (
            select([drill_statuses, phone_numbers.c.phone_number])
            .select_from(
                drill_statuses.join(users, users.c.user_id == drill_statuses.c.user_id).join(
                    phone_numbers, phone_numbers.c.user_id == drill_statuses.c.user_id
                )
            )
            .where(
                and_(
                    phone_numbers.c.is_primary.is_(True),
                    # haven't interacted recently
                    or_(
                        users.c.last_interacted_time.is_(None),
                        users.c.last_interacted_time <= time_threshold,
                    ),
                    # there's at least one started drill
                    exists().where(
                        and_(ds2.c.user_id == users.c.user_id, ds2.c.started_time.isnot(None))
                    ),
                    # and at least one incomplete drill
                    exists().where(
                        and_(ds1.c.user_id == users.c.user_id, ds1.c.completed_time.is_(None))
                    ),
                )
            )
            .order_by(drill_statuses.c.user_id, drill_statuses.c.place_in_sequence)
        )
        cur_drill_progress = None
        for row in self.engine.execute(stmt):
            user_id = uuid.UUID(row["user_id"])
            if cur_drill_progress is None or cur_drill_progress.user_id != user_id:
                if cur_drill_progress is not None:
                    yield cur_drill_progress
                cur_drill_progress = DrillProgress(
                    phone_number=row["phone_number"], user_id=user_id
                )
            if (
                cur_drill_progress.first_incomplete_drill_slug is None
                and row["completed_time"] is None
            ):
                cur_drill_progress.first_incomplete_drill_slug = row["drill_slug"]
            if (
                cur_drill_progress.first_unstarted_drill_slug is None
                and row["started_time"] is None
            ):
                cur_drill_progress.first_unstarted_drill_slug = row["drill_slug"]

        if cur_drill_progress is not None:
            yield cur_drill_progress

    def get_progress_for_user(self, phone_number: str) -> DrillProgress:
        user = self.get_user_for_phone_number(phone_number)
        user_id = user.user_id
        result = self.engine.execute(
            select([drill_statuses])
            .where(drill_statuses.c.user_id == func.uuid((str(user_id))))
            .order_by(drill_statuses.c.place_in_sequence)
        )
        progress = DrillProgress(phone_number=phone_number, user_id=user_id)
        for row in result:
            if progress.first_incomplete_drill_slug is None and row["completed_time"] is None:
                progress.first_incomplete_drill_slug = row["drill_slug"]
            if progress.first_unstarted_drill_slug is None and row["started_time"] is None:
                progress.first_unstarted_drill_slug = row["drill_slug"]
        return progress

    def delete_user_info(self, phone_number: str) -> Optional[uuid.UUID]:
        # useful for backfills and rebuilding users. Shouldn't be called regularly.
        with self.engine.connect() as connection:
            with connection.begin():
                user = self.get_user_for_phone_number(phone_number, connection)
                if user is None:
                    logging.info(f"No user exists for {phone_number}")
                    return None
                connection.execute(
                    phone_numbers.delete().where(
                        phone_numbers.c.user_id == func.uuid(str(user.user_id))
                    )
                )
                connection.execute(
                    drill_statuses.delete().where(
                        drill_statuses.c.user_id == func.uuid(str(user.user_id))
                    )
                )
                connection.execute(
                    drill_instances.delete().where(
                        drill_instances.c.user_id == func.uuid(str(user.user_id))
                    )
                )
                connection.execute(
                    users.delete().where(users.c.user_id == func.uuid(str(user.user_id)))
                )
                return user.user_id

    def get_user_for_phone_number(self, phone_number: str, connection=None) -> Optional[User]:
        if connection is None:
            connection = self.engine
        result = connection.execute(
            select([users])
            .select_from(users.join(phone_numbers, users.c.user_id == phone_numbers.c.user_id))
            .where(phone_numbers.c.phone_number == phone_number)
        )
        row = result.fetchone()
        if row is None:
            return None
        return User(
            user_id=uuid.UUID(row["user_id"]),
            profile=row["profile"],
            last_interacted_time=row["last_interacted_time"],
            seq=row["seq"],
        )

    def _create_or_update_user(
        self, batch: DialogEventBatch, ensure_user_id: Optional[uuid.UUID], connection
    ) -> uuid.UUID:
        event = batch.events[-1]
        phone_number = event.phone_number
        profile = event.user_profile.to_dict()
        result = connection.execute(
            select([phone_numbers]).where(phone_numbers.c.phone_number == phone_number)
        )
        row = result.fetchone()
        if row is None:
            logging.info(f"No record of {phone_number}. Creating a new entry.")
            user_record = User(profile=profile, seq=batch.seq)
            if ensure_user_id:
                user_record.user_id = ensure_user_id
            phone_number_record = PhoneNumber(
                phone_number=phone_number, user_id=user_record.user_id
            )
            connection.execute(
                users.insert().values(
                    user_id=str(user_record.user_id), profile=user_record.profile, seq=batch.seq
                )
            )
            connection.execute(
                phone_numbers.insert().values(
                    id=str(phone_number_record.id),
                    user_id=str(phone_number_record.user_id),
                    is_primary=phone_number_record.is_primary,
                    phone_number=phone_number_record.phone_number,
                )
            )
            for i, slug in enumerate(get_all_drill_slugs()):
                connection.execute(
                    drill_statuses.insert().values(
                        id=str(uuid.uuid4()),
                        user_id=str(user_record.user_id),
                        drill_slug=slug,
                        place_in_sequence=i,
                    )
                )
            logging.info(f"New user ID for {phone_number} is {user_record.user_id}")
            return user_record.user_id

        phone_number_record = PhoneNumber(**row)
        user_record = self.get_user(phone_number_record.user_id)
        if int(user_record.seq) >= int(batch.seq):
            logging.info(
                f"Ignoring batch at {batch.seq} because a more recent user exists "
                f"(seq {user_record.seq}"
            )
            return phone_number_record.user_id

        connection.execute(
            users.update()
            .where(users.c.user_id == func.uuid(str(phone_number_record.user_id)))
            .values(profile=profile, seq=batch.seq)
        )
        return phone_number_record.user_id

    @staticmethod
    def _reset_drill_statuses(user_id: uuid.UUID, connection):
        connection.execute(
            drill_statuses.update()
            .where(drill_statuses.c.user_id == func.uuid(str(user_id)))
            .values(started_time=None, completed_time=None, drill_instance_id=None)
        )

    @staticmethod
    def _mark_drill_started(user_id: uuid.UUID, event: DrillStarted, connection):
        connection.execute(
            drill_statuses.update()
            .where(
                and_(
                    drill_statuses.c.user_id == func.uuid(str(user_id)),
                    drill_statuses.c.drill_slug == event.drill.slug,
                )
            )
            .values(started_time=event.created_time, drill_instance_id=str(event.drill_instance_id))
        )

    @staticmethod
    def _unmark_drill_started(event: OptedOut, connection):
        connection.execute(
            drill_statuses.update()
            .where(drill_statuses.c.drill_instance_id == func.uuid(str(event.drill_instance_id)))
            .values(started_time=None)
        )

    @staticmethod
    def _mark_drill_completed(event: DrillCompleted, connection):
        connection.execute(
            drill_statuses.update()
            .where((drill_statuses.c.drill_instance_id == func.uuid(str(event.drill_instance_id))))
            .values(completed_time=event.created_time)
        )

    @staticmethod
    def _mark_interacted_time(user_id, event: DialogEvent, connection):
        connection.execute(
            users.update()
            .where(users.c.user_id == func.uuid(str(user_id)))
            .values(last_interacted_time=event.created_time)
        )

    @staticmethod
    def _invalidate_prior_drills(user_id: uuid.UUID, connection):
        connection.execute(
            drill_instances.update()
            .where(
                and_(
                    drill_instances.c.user_id == func.uuid(str(user_id)),
                    drill_instances.c.is_valid.is_(True),
                )
            )
            .values(is_valid=False)
        )

    @staticmethod
    def _invalidate_drill_instance(drill_instance_id: Optional[uuid.UUID], connection):
        if drill_instance_id is None:
            return
        connection.execute(
            drill_instances.update()
            .where(drill_instances.c.drill_instance_id == func.uuid(str(drill_instance_id)))
            .values(is_valid=False)
        )

    def _record_new_drill_instance(self, user_id: uuid.UUID, event: DrillStarted, connection):
        drill_instance = DrillInstance(
            drill_instance_id=event.drill_instance_id,
            user_id=user_id,
            phone_number=event.phone_number,
            drill_slug=event.drill.slug,
            current_prompt_slug=event.first_prompt.slug,
            current_prompt_start_time=event.created_time,
        )
        self._save_drill_instance(drill_instance, connection)

    @staticmethod
    def _mark_drill_instance_complete(event: DrillCompleted, connection):
        connection.execute(
            drill_instances.update()
            .where(drill_instances.c.drill_instance_id == func.uuid(str(event.drill_instance_id)))
            .values(
                completion_time=event.created_time,
                current_prompt_slug=None,
                current_prompt_start_time=None,
                current_prompt_last_response_time=None,
            )
        )

    @staticmethod
    def _update_current_prompt_response_time(
        event: Union[FailedPrompt, CompletedPrompt], connection
    ):
        connection.execute(
            drill_instances.update()
            .where(drill_instances.c.drill_instance_id == func.uuid(str(event.drill_instance_id)))
            .values(current_prompt_last_response_time=event.created_time)
        )

    @staticmethod
    def _update_current_prompt(event: AdvancedToNextPrompt, connection):
        connection.execute(
            drill_instances.update()
            .where(drill_instances.c.drill_instance_id == func.uuid(str(event.drill_instance_id)))
            .values(
                current_prompt_last_response_time=None,
                current_prompt_start_time=event.created_time,
                current_prompt_slug=event.prompt.slug,
            )
        )

    @staticmethod
    def _deserialize(row):
        return DrillInstance(
            drill_instance_id=uuid.UUID(row["drill_instance_id"]),
            user_id=uuid.UUID(row["user_id"]),
            phone_number=row["phone_number"],
            drill_slug=row["drill_slug"],
            current_prompt_slug=row["current_prompt_slug"],
            current_prompt_start_time=row["current_prompt_start_time"],
            current_prompt_last_response_time=row["current_prompt_last_response_time"],
            completion_time=row["completion_time"],
            is_valid=row["is_valid"],
        )

    def get_drill_instance(
        self, drill_instance_id: uuid.UUID, connection=None
    ) -> Optional[DrillInstance]:
        if connection is None:
            connection = self.engine
        result = connection.execute(
            select([drill_instances]).where(
                drill_instances.c.drill_instance_id == func.uuid(str(drill_instance_id))
            )
        )
        row = result.fetchone()
        if row is None:
            return None
        return self._deserialize(row)

    def _save_drill_instance(self, drill_instance: DrillInstance, connection=None):
        if connection is None:
            connection = self.engine
        stmt = insert(drill_instances).values(
            drill_instance_id=str(drill_instance.drill_instance_id),
            user_id=str(drill_instance.user_id),
            phone_number=drill_instance.phone_number,
            drill_slug=str(drill_instance.drill_slug),
            current_prompt_slug=str(drill_instance.current_prompt_slug),
            current_prompt_start_time=drill_instance.current_prompt_start_time,
            current_prompt_last_response_time=drill_instance.current_prompt_last_response_time,
            completion_time=drill_instance.completion_time,
            is_valid=drill_instance.is_valid,
        )
        connection.execute(stmt)

    def get_incomplete_drills(
        self, inactive_for_minutes_floor=None, inactive_for_minutes_ceil=None
    ) -> List[DrillInstance]:
        stmt = select([drill_instances]).where(
            and_(drill_instances.c.completion_time.is_(None), drill_instances.c.is_valid.is_(True))
        )  # noqa:  E711
        if inactive_for_minutes_floor is not None:
            stmt = stmt.where(
                drill_instances.c.current_prompt_start_time
                <= datetime.datetime.now(datetime.timezone.utc)
                - datetime.timedelta(minutes=inactive_for_minutes_floor)
            )
        if inactive_for_minutes_ceil is not None:
            stmt = stmt.where(
                drill_instances.c.current_prompt_start_time
                >= datetime.datetime.now(datetime.timezone.utc)
                - datetime.timedelta(minutes=inactive_for_minutes_ceil)
            )
        return [self._deserialize(row) for row in self.engine.execute(stmt)]

    def drop_and_recreate_tables_testing_only(self):
        if self.engine_factory == db.get_sqlalchemy_engine:
            raise ValueError("This function should not be called against databases in RDS")
        try:
            drill_statuses.drop(bind=self.engine)
        except DatabaseError:
            pass
        try:
            phone_numbers.drop(bind=self.engine)
        except DatabaseError:
            pass
        try:
            drill_instances.drop(bind=self.engine)
        except DatabaseError:
            pass
        try:
            users.drop(bind=self.engine)
        except DatabaseError:
            pass
        metadata.create_all(bind=self.engine)
