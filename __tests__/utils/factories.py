import datetime
import uuid
from stopcovid.drill_progress.drill_progress import DrillInstance


def make_drill_instance(**overrides) -> DrillInstance:
    def _get_value(key, default):
        return overrides[key] if key in overrides else default

    return DrillInstance(
        drill_instance_id=_get_value("drill_instance_id", uuid.uuid4()),
        user_id=_get_value("user_id", uuid.uuid4()),
        phone_number=_get_value("phone_number", "+14803335555"),
        drill_slug=_get_value("drill_slug", "test"),
        current_prompt_slug=_get_value("current_prompt_slug", "test-prompt"),
        current_prompt_start_time=_get_value(
            "current_prompt_start_time", datetime.datetime.now(datetime.timezone.utc)
        ),
        current_prompt_last_response_time=_get_value(
            "current_prompt_last_response_time", datetime.datetime.now(datetime.timezone.utc)
        ),
        completion_time=_get_value("completion_time", None),
        is_valid=_get_value("is_valid", True),
    )
