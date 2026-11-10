import json
from pathlib import Path

from .models import Classification, ProcessResult
from .provider import Classifier
from .store import Tracker, utc_now


class IntakeService:
    REVIEW_THRESHOLD = 0.75

    def __init__(self, tracker: Tracker, classifier: Classifier, outbox: str | Path):
        self.tracker = tracker
        self.classifier = classifier
        self.outbox = Path(outbox)

    def process_inbox(self, inbox_path: str | Path) -> list[ProcessResult]:
        requests = self._load_requests(Path(inbox_path))
        results: list[ProcessResult] = []
        for request in requests:
            request_id = request["id"]
            if self.tracker.request_exists(request_id):
                results.append(ProcessResult(request_id, "skipped", "already processed"))
                continue

            classification = self.classifier.classify(request["request"])
            if classification.confidence < self.REVIEW_THRESHOLD:
                review_id = self.tracker.create_review(request, classification)
                self.tracker.add_audit_event(
                    "review_requested", request_id, "review", review_id,
                    {"confidence": classification.confidence, "reason": "low confidence"},
                )
                results.append(
                    ProcessResult(
                        request_id,
                        "review",
                        f"human review | confidence {classification.confidence:.2f}",
                    )
                )
                continue

            ticket_id = self.tracker.create_ticket(request, classification)
            payload_path = self._write_outbox_payload(ticket_id, request, classification)
            self.tracker.add_audit_event(
                "ticket_created", request_id, "ticket", ticket_id,
                {"outbox": payload_path.name, "team": classification.owning_team},
            )
            results.append(
                ProcessResult(
                    request_id,
                    "ticketed",
                    f"ticket {ticket_id} -> {classification.owning_team} | "
                    f"{classification.urgency} | confidence {classification.confidence:.2f}",
                )
            )
        return results

    def _write_outbox_payload(
        self,
        ticket_id: int,
        request: dict[str, str],
        classification: Classification,
    ) -> Path:
        self.outbox.mkdir(parents=True, exist_ok=True)
        payload = {
            "event": "ticket.created",
            "occurred_at": utc_now(),
            "delivery": {"type": "webhook", "status": "pending"},
            "ticket": {
                "id": ticket_id,
                "request_id": request["id"],
                "requester": request["requester"],
                "request": request["request"],
                "category": classification.category,
                "urgency": classification.urgency,
                "owning_team": classification.owning_team,
                "confidence": classification.confidence,
            },
        }
        destination = self.outbox / f"ticket-{ticket_id:04d}.json"
        temporary = destination.with_suffix(".tmp")
        temporary.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        temporary.replace(destination)
        return destination

    def _load_requests(self, inbox_path: Path) -> list[dict[str, str]]:
        data = json.loads(inbox_path.read_text(encoding="utf-8"))
        if not isinstance(data, list):
            raise ValueError("Inbox must be a JSON array of requests")
        required = ("id", "requester", "request")
        for index, row in enumerate(data):
            if not isinstance(row, dict):
                raise ValueError(f"Request {index + 1} must be a JSON object")
            for field in required:
                if not isinstance(row.get(field), str) or not row[field].strip():
                    raise ValueError(f"Request {index + 1} needs a non-empty {field}")
        return data
