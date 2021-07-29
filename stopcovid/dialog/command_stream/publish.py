import json
import logging
import os
from typing import Dict, Any, List, Tuple
import rollbar

from stopcovid.utils.boto3 import get_boto3_client


class CommandPublisher:
    def __init__(self) -> None:
        self.stage = os.environ.get("STAGE")

    def publish_process_sms_command(
        self, phone_number: str, content: str, twilio_webhook: dict
    ) -> None:
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

    def _publish_commands(self, commands: List[Tuple[str, Dict[str, Any]]]) -> None:
        kinesis = get_boto3_client("kinesis")
        records = [
            {"Data": json.dumps(data), "PartitionKey": phone_number}
            for phone_number, data in commands
        ]
        response = kinesis.put_records(StreamName=f"command-stream-{self.stage}", Records=records)
        if response.get("FailedRecordCount"):
            rollbar.report_exc_info(extra_data=response)
