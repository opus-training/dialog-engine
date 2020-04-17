import logging
import sys


def _is_running_unit_tests():
    return sys.argv[0].split(" ")[-1] == "unittest"


def configure_logging():
    if _is_running_unit_tests():
        logging.disable(logging.CRITICAL)
        return

    root = logging.getLogger()
    root.setLevel(logging.INFO)
