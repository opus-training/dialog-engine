import os

from sqlalchemy import create_engine
import sqlalchemy_aurora_data_api

sqlalchemy_aurora_data_api.register_dialects()


def get_sqlalchemy_engine():
    cluster_arn = os.environ.get("DB_CLUSTER_ARN")
    secret_arn = os.environ.get("DB_SECRET_ARN")
    return create_engine(
        "postgresql+auroradataapi://:@/postgres",
        connect_args=dict(aurora_cluster_arn=cluster_arn, secret_arn=secret_arn),
    )


def get_test_sqlalchemy_engine():
    return create_engine("postgresql://postgres:testing@localhost:6543/postgres")
