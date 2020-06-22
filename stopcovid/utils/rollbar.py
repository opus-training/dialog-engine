import os
import sys

import rollbar


def _is_running_unit_tests():
    return sys.argv[0].split(" ")[-1] == "unittest"


def configure_rollbar():
    if _is_running_unit_tests():
        return

    stage = os.environ.get("STAGE")
    rollbar.init(os.environ.get("ROLLBAR_TOKEN"), environment=f"dialog-engine-{stage}")
