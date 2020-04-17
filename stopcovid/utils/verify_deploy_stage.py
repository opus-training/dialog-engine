import os


def verify_deploy_stage():
    stage = os.environ["STAGE"]
    deploy_stage = os.getenv("DEPLOY_STAGE")
    if stage != deploy_stage:
        raise EnvironmentError(
            f"There is a mismatch between the stage and environment variables. "
            f"Exiting. (STAGE={stage}, DEPLOY_STAGE={deploy_stage})"
        )
    db_cluster_arn = os.getenv("DB_CLUSTER_ARN", "")
    if not db_cluster_arn.endswith(stage):
        raise EnvironmentError(
            f"Wrong db configuration. (STAGE={stage}, DB_CLUSTER_ARN={db_cluster_arn})"
        )
