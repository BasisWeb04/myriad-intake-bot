import argparse
import os
from pathlib import Path

from .provider import RuleBasedClassifier
from .service import IntakeService
from .store import Tracker


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Route internal requests into a local ticket tracker.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    run_parser = subparsers.add_parser("run", help="Process a JSON inbox")
    run_parser.add_argument("inbox", type=Path)
    subparsers.add_parser("queue", help="Show requests waiting for human review")
    subparsers.add_parser("report", help="Show request counts by team and urgency")
    return parser


def paths() -> tuple[Path, Path]:
    database = Path(os.environ.get("INTAKE_BOT_DB", "intake.db"))
    outbox = Path(os.environ.get("INTAKE_BOT_OUTBOX", "outbox"))
    return database, outbox


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    database, outbox = paths()
    tracker = Tracker(database)
    try:
        if args.command == "run":
            service = IntakeService(tracker, RuleBasedClassifier(), outbox)
            for result in service.process_inbox(args.inbox):
                print(f"{result.request_id}: {result.status.upper()} | {result.message}")
            return 0
        if args.command == "queue":
            rows = tracker.list_review_queue()
            print(f"Human review queue: {len(rows)}")
            for row in rows:
                print(
                    f"{row['request_id']} | {row['requester']} | confidence {row['confidence']:.2f} | "
                    f"{row['request_text']}"
                )
            return 0

        report = tracker.report()
        print(
            f"Requests processed: {report['total_requests']} "
            f"({report['ticket_count']} ticketed, {report['review_count']} review)"
        )
        print("By team:")
        for name, count in report["by_team"].items():
            print(f"  {name}: {count}")
        print("By urgency:")
        for name, count in report["by_urgency"].items():
            print(f"  {name}: {count}")
        return 0
    finally:
        tracker.close()
