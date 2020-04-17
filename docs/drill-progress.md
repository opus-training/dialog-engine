# Drill Progress Context

The Drill Progress Context is responsible for tracking how users are progressing through drills. This information is used in three ways:

* To report progress back to users of the platform.
* To remind users to finish drills that are in progress.
* To initiate new drills daily for users who have remaining drills.

The Drill Progress Context stores data in a relational database (Amazon Aurora) to make it easy to write queries against all of these use cases.

## Initiation and reminders

New drills can be initiated either on a schedule or on-demand. The Drill Progress Context handles both of those cases.

For scheduled initiation and reminders, the Drill Progress Context runs cron jobs to trigger reminders and to initiate new drills. Those crons query its database to find which reminders/drills to trigger, and then enqueues commands for the Dialog Context.

The Drill Progress Context also is responsible for initiating drills on demand in response to an event from the Dialog Context:

* A `USER_VALIDATED` event indicates that a user has just validated and needs to receive their first drill.
* A `NEXT_DRILL_REQUESTED` event indicates that a user has requested a new drill (e.g., by texting "MORE").

## Data model

Tables:

* `users`: One row per user.
* `phone_numbers`: Maps phone numbers to users.
* `drill_statuses`: Maintains one row per user per drill. If we want to introduce a new drill, we need to insert a row in `drill_statuses` for each user who'll receive it.
* `drill_instances`: One row per *instance* of a drill. Each time a drill kicks off, we generate a unique drill instance ID.

All of the tables have foreign key references back to `users`, which means that the data model is a tree of objects, rooted at the user. (It's an [aggregate](https://medium.com/@philsarin/whats-the-point-of-the-aggregate-pattern-741a3132da5c).)

As we process each event, we update a user's entire tree of objects (`users`, `phone_numbers`, `drill_statuses`, and `drill_instances`) in one transaction.

**NOTE**: Though our data model allows each user to have multiple phone numbers, the system won't handle it well if more than one phone number is actively being used. We assume that the updater (described below) processes one event at a time for each user. If a user is actively receiving events for two phone numbers at once, they may come in on different Dialog Event Stream shards and violate this assumption.

## Components

* A relational database (Amazon Aurora, postgresql-compatible version)
* A DynamoDB table used for drill scheduling
* [Updater](../stopcovid/drill_progress/aws_lambdas/update_drill_status.py): A consumer of the Dialog Event Stream that updates the database based on each event. The Updater also handles on-demand drill initiation, which occurs when a user first validates or when they request a new drill by typing MORE.
* [Next Drill Scheduler](../stopcovid/drill_progress/aws_lambdas/schedule_next_drills_to_trigger.py): A cron that runs daily to find users who need new drills. Those user-drill combinations are recorded in DynamoDB for distribution over the next 3 hours — to avoid flooding twilio with a bunch of messages at once.
* [Scheduled Drill Initiator](../stopcovid/drill_progress/aws_lambdas/trigger_scheduled_drill.py): Initiates drills scheduled by the Next Drill Scheduler lambda, by enqueueing a command for the Dialog Context. 
* [Reminder sender](../stopcovid/drill_progress/aws_lambdas/trigger_reminders.py): A cron that sends reminders for users who haven't interacted in a while. Enqueues a command for the Dialog Context to send the reminders.