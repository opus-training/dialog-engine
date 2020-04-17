import logging
from typing import Optional

from .drill_progress import DrillProgressRepository
from ..dialog.command_stream.publish import CommandPublisher
from ..drills.drills import get_first_drill_slug
from ..utils.idempotency import IdempotencyChecker

IDEMPOTENCY_REALM = "drill-initiation"
IDEMPOTENCY_EXPIRATION_MINUTES = 600


class DrillInitiator:
    def __init__(self):
        self.drill_progress_repository = DrillProgressRepository()
        self.command_publisher = CommandPublisher()
        self.idempotency_checker = IdempotencyChecker()

    def trigger_first_drill(self, phone_number: str, idempotency_key: str):
        self.trigger_drill(phone_number, get_first_drill_slug(), idempotency_key)

    def trigger_next_drill_for_user(self, phone_number: str, idempotency_key: str):
        drill_progress = self.drill_progress_repository.get_progress_for_user(phone_number)
        drill_slug = drill_progress.next_drill_slug_to_trigger()
        self.trigger_drill(phone_number, drill_slug, idempotency_key)

    def trigger_drill_if_not_stale(self, phone_number: str, drill_slug: str, idempotency_key: str):
        drill_progress = self.drill_progress_repository.get_progress_for_user(phone_number)
        if drill_progress.next_drill_slug_to_trigger() != drill_slug:
            # the request is stale. Since it was enqueued, the user has started or
            # completed a drill.
            logging.info(
                f"Ignoring request to trigger {drill_slug} for {phone_number} because it is stale"
            )
            return
        self.trigger_drill(
            drill_progress.phone_number,
            drill_progress.next_drill_slug_to_trigger(),
            idempotency_key,
        )

    def trigger_drill(self, phone_number: str, drill_slug: Optional[str], idempotency_key: str):
        if drill_slug is None:
            logging.info(
                f"Ignoring request to trigger drill_slug=None for {phone_number}. "
                f"The user might be out of drills."
            )
            return
        consolidated_key = f"{phone_number}:{drill_slug}:{idempotency_key}"
        if not self.idempotency_checker.already_processed(consolidated_key, IDEMPOTENCY_REALM):
            self.command_publisher.publish_start_drill_command(phone_number, drill_slug)
            self.idempotency_checker.record_as_processed(
                consolidated_key, IDEMPOTENCY_REALM, IDEMPOTENCY_EXPIRATION_MINUTES
            )
