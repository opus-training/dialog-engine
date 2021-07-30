import os

from boto3 import client, resource


LOCALSTACK_ENDPOINT_URL = "http://localhost:4566"


def get_boto3_client(service_name: str, **kwargs):  # type: ignore
    if os.environ.get("STAGE") == "local":
        return client(service_name, **kwargs, endpoint_url=LOCALSTACK_ENDPOINT_URL, use_ssl=False)
    return client(service_name, **kwargs)


def get_boto3_resource(service_name: str, **kwargs):  # type: ignore
    if os.environ.get("STAGE") == "local":
        return resource(service_name, **kwargs, endpoint_url=LOCALSTACK_ENDPOINT_URL, use_ssl=False)
    return resource(service_name, **kwargs)
