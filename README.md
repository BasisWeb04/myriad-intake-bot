# Intake Bot

This Python 3.11+ command-line sample turns plain-English internal IT and operations requests into routed tickets. It stores accepted tickets in SQLite, writes one webhook-style JSON file per ticket, sends uncertain requests to a human review queue, and records an audit event for every decision. It uses only the Python standard library.

A two-minute screen recording of the tool running is in [demo/demo.mp4](demo/demo.mp4).

The classify step is a local, rule-based stand-in, not a real AI model; it keeps the sample runnable without an API key. A production model provider would implement `Classifier` in `intake_bot/provider.py` and be passed to `IntakeService` without changing the routing or review controls.

## Run it

From this `app` folder:

```text
python -B -m intake_bot run examples/inbox.json
python -B -m intake_bot queue
python -B -m intake_bot report
python -B -m unittest discover -s tests
```

The default database is `intake.db`; notification files go to `outbox/`. Set `INTAKE_BOT_DB` or `INTAKE_BOT_OUTBOX` to use different local paths.

## Processing rules

- Confidence below `0.75` creates a pending human-review item. It never creates a ticket or notification file.
- Recognized requests are routed to Service Desk, Endpoint Support, Network Operations, Application Support, Business Systems, or Security Operations.
- Company-wide impact is critical. Clear work blockers are high urgency. Deferred requests are low urgency.
- A repeated request ID is skipped so rerunning an inbox does not duplicate work.

## Local records

- `tickets`: accepted requests and their routing fields.
- `review_queue`: low-confidence requests awaiting a person.
- `audit_log`: the decision event and its linked record.
- `outbox/ticket-NNNN.json`: a pending webhook payload that matches the saved ticket.
