import json
import tempfile
import unittest
from pathlib import Path

from intake_bot.provider import RuleBasedClassifier
from intake_bot.service import IntakeService
from intake_bot.store import Tracker


class ClassifierTests(unittest.TestCase):
    def setUp(self):
        self.classifier = RuleBasedClassifier()

    def test_password_reset_routes_to_service_desk(self):
        result = self.classifier.classify("I am locked out and need a password reset")
        self.assertEqual("access", result.category)
        self.assertEqual("Service Desk", result.owning_team)
        self.assertGreaterEqual(result.confidence, 0.75)

    def test_office_vpn_outage_is_critical(self):
        result = self.classifier.classify("VPN is down for our whole Phoenix office")
        self.assertEqual("network", result.category)
        self.assertEqual("Network Operations", result.owning_team)
        self.assertEqual("critical", result.urgency)

    def test_software_license_routes_to_application_support(self):
        result = self.classifier.classify("Please assign a Figma software license")
        self.assertEqual("software", result.category)
        self.assertEqual("Application Support", result.owning_team)

    def test_vague_request_has_low_confidence(self):
        result = self.classifier.classify("Something is weird. Can someone look at it?")
        self.assertLess(result.confidence, 0.75)
        self.assertEqual("Unassigned", result.owning_team)

    def test_clicked_phishing_link_is_high_urgency(self):
        result = self.classifier.classify("I clicked a suspicious link in a phishing email")
        self.assertEqual("Security Operations", result.owning_team)
        self.assertEqual("high", result.urgency)


class IntakeServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        root = Path(self.temp_dir.name)
        self.db_path = root / "tracker.db"
        self.outbox = root / "outbox"
        self.inbox = root / "inbox.json"
        self.tracker = Tracker(self.db_path)
        self.service = IntakeService(self.tracker, RuleBasedClassifier(), self.outbox)

    def tearDown(self):
        self.tracker.close()
        self.temp_dir.cleanup()

    def write_inbox(self, rows):
        self.inbox.write_text(json.dumps(rows), encoding="utf-8")

    def test_accepted_request_creates_ticket(self):
        self.write_inbox([{"id": "REQ-1", "requester": "Maya", "request": "Reset my password"}])
        results = self.service.process_inbox(self.inbox)
        tickets = self.tracker.list_tickets()
        self.assertEqual("ticketed", results[0].status)
        self.assertEqual(1, len(tickets))
        self.assertEqual("REQ-1", tickets[0]["request_id"])

    def test_vague_request_enters_review_without_ticket(self):
        self.write_inbox([{"id": "REQ-2", "requester": "Leo", "request": "Something is weird"}])
        results = self.service.process_inbox(self.inbox)
        self.assertEqual("review", results[0].status)
        self.assertEqual(1, len(self.tracker.list_review_queue()))
        self.assertEqual([], self.tracker.list_tickets())
        self.assertEqual([], list(self.outbox.glob("*.json")))

    def test_outbox_payload_matches_its_ticket(self):
        self.write_inbox([{"id": "REQ-3", "requester": "Nina", "request": "Need a new laptop"}])
        self.service.process_inbox(self.inbox)
        ticket = self.tracker.list_tickets()[0]
        payload = json.loads(next(self.outbox.glob("*.json")).read_text(encoding="utf-8"))
        self.assertEqual("ticket.created", payload["event"])
        self.assertEqual(ticket["id"], payload["ticket"]["id"])
        self.assertEqual(ticket["request_id"], payload["ticket"]["request_id"])
        self.assertEqual(ticket["owning_team"], payload["ticket"]["owning_team"])

    def test_report_counts_ticket_and_review_requests(self):
        self.write_inbox([
            {"id": "REQ-4", "requester": "Omar", "request": "Reset my password"},
            {"id": "REQ-5", "requester": "Priya", "request": "Something feels off"},
        ])
        self.service.process_inbox(self.inbox)
        report = self.tracker.report()
        self.assertEqual(2, report["total_requests"])
        self.assertEqual(2, sum(report["by_team"].values()))
        self.assertEqual(2, sum(report["by_urgency"].values()))

    def test_every_request_creates_an_audit_event(self):
        self.write_inbox([
            {"id": "REQ-6", "requester": "Quinn", "request": "WiFi is down"},
            {"id": "REQ-7", "requester": "Rae", "request": "Please help with this"},
        ])
        self.service.process_inbox(self.inbox)
        events = self.tracker.list_audit_events()
        self.assertEqual(2, len(events))
        self.assertEqual({"ticket_created", "review_requested"}, {row["event_type"] for row in events})

    def test_duplicate_request_is_skipped(self):
        row = {"id": "REQ-8", "requester": "Sam", "request": "Reset my password"}
        self.write_inbox([row])
        self.service.process_inbox(self.inbox)
        results = self.service.process_inbox(self.inbox)
        self.assertEqual("skipped", results[0].status)
        self.assertEqual(1, len(self.tracker.list_tickets()))

    def test_invalid_inbox_is_rejected(self):
        self.write_inbox({"id": "REQ-9", "request": "Reset my password"})
        with self.assertRaisesRegex(ValueError, "JSON array"):
            self.service.process_inbox(self.inbox)


if __name__ == "__main__":
    unittest.main()
