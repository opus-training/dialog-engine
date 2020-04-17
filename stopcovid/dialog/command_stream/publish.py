import json
import logging
import os
from typing import Dict, Any, Optional, List, Tuple

import boto3

from stopcovid.drill_progress.drill_progress import DrillInstance


class CommandPublisher:
    def __init__(self):
        self.stage = os.environ.get("STAGE")

    def publish_start_drill_command(self, phone_number: str, drill_slug: str):
        logging.info(f"({phone_number}) publishing START_DRILL command")
        self._publish_commands(
            [
                (
                    phone_number,
                    {
                        "type": "START_DRILL",
                        "payload": {"phone_number": phone_number, "drill_slug": drill_slug},
                    },
                )
            ]
        )

    def publish_trigger_reminder_commands(self, drills: List[DrillInstance]):
        logging.info(f"publishing {len(drills)} TRIGGER_REMINDER commands")
        self._publish_commands(
            [
                (
                    drill.phone_number,
                    {
                        "type": "TRIGGER_REMINDER",
                        "payload": {
                            "phone_number": drill.phone_number,
                            "drill_instance_id": str(drill.drill_instance_id),
                            "prompt_slug": drill.current_prompt_slug,
                        },
                    },
                )
                for drill in drills
            ]
        )

    def publish_process_sms_command(self, phone_number: str, content: str, twilio_webhook: dict):
        logging.info(f"({phone_number}) publishing INBOUND_SMS command")
        self._publish_commands(
            [
                (
                    phone_number,
                    {
                        "type": "INBOUND_SMS",
                        "payload": {
                            "From": phone_number,
                            "Body": content,
                            "twilio_webhook": twilio_webhook,
                        },
                    },
                )
            ]
        )

    @staticmethod
    def _get_kinesis_client():
        return boto3.client("kinesis")

    @staticmethod
    def _get_last_seq(phone_number) -> Optional[str]:
        return None

    @staticmethod
    def _try_record_seq(phone_number, seq):
        pass

    def _publish_commands(self, commands: List[Tuple[str, Dict[str, Any]]]):
        kinesis = self._get_kinesis_client()
        records = []
        for phone_number, data in commands:
            last_seq = self._get_last_seq(phone_number)
            record = {"Data": json.dumps(data), "PartitionKey": phone_number}
            if last_seq:
                record["SequenceNumberForOrdering"] = last_seq
            records.append(record)
        response = kinesis.put_records(StreamName=f"command-stream-{self.stage}", Records=records)
        for i, result in enumerate(response["Records"]):
            self._try_record_seq(records[i]["PartitionKey"], result["SequenceNumber"])
