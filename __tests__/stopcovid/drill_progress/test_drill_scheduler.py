import datetime
import os
import unittest
import uuid
from unittest.mock import patch

from stopcovid.drill_progress.drill_progress import DrillProgress
from stopcovid.drill_progress.drill_scheduler import DrillScheduler

NOW = datetime.datetime.now(tz=datetime.timezone.utc)


class TestDrillScheduler(unittest.TestCase):
    def setUp(self) -> None:
        os.environ["STAGE"] = "test"
        self.scheduler = DrillScheduler(
            region_name="us-west-2",
            endpoint_url="http://localhost:9000",
            aws_access_key_id="fake-key",
            aws_secret_access_key="fake-secret",
        )
        self.scheduler.ensure_tables_exist()

    @patch("stopcovid.drill_progress.drill_scheduler.DrillScheduler._now", return_value=NOW)
    def test_schedule_drill(self, now_mock):
        drill_progresses = [
            DrillProgress(
                phone_number="123456789",
                user_id=uuid.uuid4(),
                first_unstarted_drill_slug="first",
                first_incomplete_drill_slug="second",
            ),
            DrillProgress(
                phone_number="987654321",
                user_id=uuid.uuid4(),
                first_unstarted_drill_slug="first",
                first_incomplete_drill_slug="second",
            ),
        ]
        self.scheduler.schedule_drills_to_trigger(drill_progresses, 2)

        scheduled_drill1 = self.scheduler.get_scheduled_drill(drill_progresses[0])
        self.assertEqual(drill_progresses[0], scheduled_drill1.drill_progress)
        delay = scheduled_drill1.trigger_ts - NOW.timestamp()
        self.assertTrue(0 <= delay <= 120)

        scheduled_drill2 = self.scheduler.get_scheduled_drill(drill_progresses[1])
        self.assertEqual(drill_progresses[1], scheduled_drill2.drill_progress)
        delay = scheduled_drill2.trigger_ts - NOW.timestamp()
        self.assertTrue(0 <= delay <= 120)
