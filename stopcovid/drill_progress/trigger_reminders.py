import os

from stopcovid.drill_progress.drill_progress import DrillProgressRepository
from stopcovid.dialog.command_stream.publish import CommandPublisher
from stopcovid.utils.idempotency import IdempotencyChecker

REMINDER_TRIGGER_FLOOR_MINUTES = 60 * 4
REMINDER_TRIGGER_CEIL_MINUTES = 60 * 24

# The idempotency expiration must be larger than the reminder trigger ceiling
IDEMPOTENCY_EXPIRATION_MINUTES = REMINDER_TRIGGER_CEIL_MINUTES * 2
IDEMPOTENCY_REALM = "trigger-reminders"


class ReminderTriggerer:
    def __init__(self, **kwargs):
        self.stage = os.environ.get("STAGE")
        self.drill_progress_repo = self._get_drill_progress_repo()
        self.command_publisher = CommandPublisher()
        self.idempotency_checker = IdempotencyChecker()

    def _get_drill_progress_repo(self):
        return DrillProgressRepository()

    def trigger_reminders(self):
        drill_instances = self.drill_progress_repo.get_incomplete_drills(
            inactive_for_minutes_floor=REMINDER_TRIGGER_FLOOR_MINUTES,
            inactive_for_minutes_ceil=REMINDER_TRIGGER_CEIL_MINUTES,
        )

        for drill_instance in drill_instances:
            idempotency_key = (
                f"{drill_instance.drill_instance_id}-{drill_instance.current_prompt_slug}"
            )
            if self.idempotency_checker.already_processed(idempotency_key, IDEMPOTENCY_REALM):
                continue

            # The dialog agent wont send a reminder for the same drill/prompt combo twice
            # publishing to the stream twice should be avoided, but isn't a big deal.
            self.command_publisher.publish_trigger_reminder_commands([drill_instance])
            self.idempotency_checker.record_as_processed(
                idempotency_key, IDEMPOTENCY_REALM, IDEMPOTENCY_EXPIRATION_MINUTES
            )
