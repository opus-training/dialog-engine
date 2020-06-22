import os
import sys

import rollbar


def _is_running_unit_tests():
    return sys.argv[0].split(" ")[-1] == "unittest"


def configure_rollbar():
    if _is_running_unit_tests():
        return

    rollbar.init(os.environ.get("ROLLBAR_TOKEN"), environment=os.environ.get("STAGE"))
