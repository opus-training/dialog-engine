# The StopCOVID Dialog Engine

The code in this repo is deployed on Amazon's serverless platform, using Lambda, Kinesis, DynamoDB, among other things. This was our first substantial experience writing a serverless app, and we were pleasantly surprised by how quickly we could create a useful app with well-defined, decoupled components. If you're curious about building serverless event-driven applications, have a look around this repo and copy what you'd like.

## Architecture

The StopCOVID backend is serverless and event-driven. The core of the system is a Lambda function that receives commands from a Kinesis stream and produces events to a DynamoDB table and stream. Consumers of the event stream respond to the user and track per-user drill progress.

![simplified architecture](simplified-architecture.png)

*A simplified overview of the StopCOVID architecture.*

For a lot more detail, see the [architecture overview](docs/README.md).

## The simulator

You can simulate the core of dialog processing on the command line — by feeding the dialog engine with command-line entries rather than entries from a kinesis stream. Try it out by running `python simulator.py`.

## Interesting parts of the code

The heart of the system is in [`engine.py`](stopcovid/dialog/engine.py) and, in particular, the `process_command()` function. Here you'll see how we process commands and churn out a series of events in response.

We aggressively adopted type checking. We used Python type hints wherever we could and we used the [pyright](https://github.com/microsoft/pyright) type checker to enforce type hints. We also used [Marshmallow](https://marshmallow.readthedocs.io/en/stable/) schemas for everything that we serialized to or deserialized from JSON.

## `manage.py`

The `manage.py` script contains commands that we've found helpful while operating the Dialog Engine in production. You'll need appropriate AWS credentials in your environment to use this script. Type `python manage.py --help` for info on what this script can do.

## CI
We use [black](https://black.readthedocs.io/en/stable/) for code formatting and flake8 for linting, with a custom rule setting maximum line length to 100.
- `black --config black.toml .`
- `flake8`

## Running tests
- Run `docker-compose up` in the `db_local` directory
- `python -m unittest`

## localstack

To run `dialog-engine` (and `scadmin`) against local, mocked AWS infrastructure, we use [localstack](https://localstack.cloud/).

1. [Start localstack](https://github.com/localstack/localstack#running). This README & config assumes you'll run it in host mode on your machine (by passing the `--host` option), not using Docker. Make sure to include the configuration in `.locastack-env`. e.g.:
```
pip install localstack
set -a
. ./.localstack-env
set +a
localstack start --host
```

2. Install serverless dependencies with `yarn i`

3. `yarn deploy`

4. In `scadmin`, ensure the `BOTO_ENDPOINT_URL` env var is set

### Notes

- Running in host mode requires Java 8+--which you must install yourself--for DynamoDB to run
- When restarting localstack in host mode, Kinesis/DynamoDB will sometimes end up in a corrupted state and/or fail to shut down, leaving lingering processes & blocked ports. Usually, manually stopping any `java` or `kinesis-*` processes will fix this, or removing the localstack `infra` directory (more details in [this GitHub issue](https://github.com/localstack/localstack/issues/514))
- At time of writing, [localstack Kinesis directly invokes Lambda functions (if they are linked to a stream) before returning a response to PUT record requests](https://github.com/localstack/localstack/issues/4354). If there are errors in the lambda invocation, this can result in confusing "timeouts" in the client PUTing records to Kinesis
- The `start` npm script should work in theory, but is currently broken in practice: Cloudformation updates in localstack "fail" to deploy our lambdas (even though they successfully provision), so the `deploy` script always has an exit code of 1
