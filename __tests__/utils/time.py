import datetime


def get_timestamp_min_in_past(min_ago: int) -> datetime.datetime:
    dt = datetime.datetime.now() - datetime.timedelta(minutes=min_ago)
    return dt.replace(tzinfo=datetime.timezone.utc)
