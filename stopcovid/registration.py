import os
from collections import OrderedDict
import json

import requests
from requests.auth import HTTPBasicAuth
from serverless_sdk import tag_event  # type: ignore

BASE_URL = "https://eslworks-api-production.herokuapp.com/slowcovid"


def get_labels(data):
    labels = [label.strip() for label in data.get("labels", "").split(",") if label.strip()]

    # remove dups but preserve ordering
    return list(OrderedDict.fromkeys(labels))


def build_registration_payload(data):

    owner = {
        "email": data["email"],
        "first_name": data["first-name"],
        "last_name": data["last-name"],
        "title": data["title"],
        "intercom_id": data["intercom_id"],
    }

    company = {
        "name": data["company-name"],
        "state": data["state"],
        "employee_range": data["employee-range"],
        "zip_code": data["postal-code"],
        "business_type": data["business-type"],
    }

    labels = get_labels(data)

    return {
        "company": company,
        "owner": owner,
        "labels": labels,
        "how_did_you_hear_about_us": data["how-did-you-hear-about-us"],
    }


def register(payload):
    resp = requests.post(
        f"{BASE_URL}/register",
        auth=HTTPBasicAuth(os.environ.get("AUTH_USERNAME"), os.environ.get("AUTH_PASSWORD")),
        json=payload,
    )
    tag_event("eslworks_register_status", resp.status_code)
    resp.raise_for_status()
    return resp


def handle_registration(event, context):
    tag_event("registration", "raw_event", event)

    form_data = json.loads(event["body"])
    payload = build_registration_payload(form_data["data"])

    tag_event("registration", "computed_payload", payload)

    register(payload)

    return {"statusCode": 200}
