import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .models import Classification


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Tracker:
    def __init__(self, database_path: str | Path):
        self.database_path = Path(database_path)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(self.database_path)
        self.connection.row_factory = sqlite3.Row
        self._create_schema()

    def _create_schema(self) -> None:
        self.connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS tickets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                request_id TEXT NOT NULL UNIQUE,
                requester TEXT NOT NULL,
                request_text TEXT NOT NULL,
                category TEXT NOT NULL,
                urgency TEXT NOT NULL,
                owning_team TEXT NOT NULL,
                confidence REAL NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS review_queue (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                request_id TEXT NOT NULL UNIQUE,
                requester TEXT NOT NULL,
                request_text TEXT NOT NULL,
                reason TEXT NOT NULL,
                confidence REAL NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS audit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_type TEXT NOT NULL,
                request_id TEXT NOT NULL,
                entity_type TEXT NOT NULL,
                entity_id INTEGER NOT NULL,
                details_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            """
        )
        self.connection.commit()

    def request_exists(self, request_id: str) -> bool:
        query = """
            SELECT request_id FROM tickets WHERE request_id = ?
            UNION ALL
            SELECT request_id FROM review_queue WHERE request_id = ?
            LIMIT 1
        """
        return self.connection.execute(query, (request_id, request_id)).fetchone() is not None

    def create_ticket(self, request: dict[str, str], classification: Classification) -> int:
        cursor = self.connection.execute(
            """
            INSERT INTO tickets (
                request_id, requester, request_text, category, urgency,
                owning_team, confidence, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                request["id"], request["requester"], request["request"],
                classification.category, classification.urgency,
                classification.owning_team, classification.confidence, utc_now(),
            ),
        )
        self.connection.commit()
        return int(cursor.lastrowid)

    def create_review(self, request: dict[str, str], classification: Classification) -> int:
        cursor = self.connection.execute(
            """
            INSERT INTO review_queue (
                request_id, requester, request_text, reason, confidence, created_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                request["id"], request["requester"], request["request"],
                "Classification confidence below 0.75", classification.confidence, utc_now(),
            ),
        )
        self.connection.commit()
        return int(cursor.lastrowid)

    def add_audit_event(
        self,
        event_type: str,
        request_id: str,
        entity_type: str,
        entity_id: int,
        details: dict[str, Any],
    ) -> None:
        self.connection.execute(
            """
            INSERT INTO audit_log (
                event_type, request_id, entity_type, entity_id, details_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (event_type, request_id, entity_type, entity_id, json.dumps(details, sort_keys=True), utc_now()),
        )
        self.connection.commit()

    def list_tickets(self) -> list[dict[str, Any]]:
        rows = self.connection.execute("SELECT * FROM tickets ORDER BY id").fetchall()
        return [dict(row) for row in rows]

    def list_review_queue(self) -> list[dict[str, Any]]:
        rows = self.connection.execute(
            "SELECT * FROM review_queue WHERE status = 'pending' ORDER BY id"
        ).fetchall()
        return [dict(row) for row in rows]

    def list_audit_events(self) -> list[dict[str, Any]]:
        rows = self.connection.execute("SELECT * FROM audit_log ORDER BY id").fetchall()
        return [dict(row) for row in rows]

    def report(self) -> dict[str, Any]:
        by_team = {
            row["owning_team"]: row["count"]
            for row in self.connection.execute(
                "SELECT owning_team, COUNT(*) AS count FROM tickets GROUP BY owning_team ORDER BY owning_team"
            )
        }
        by_urgency = {
            row["urgency"]: row["count"]
            for row in self.connection.execute(
                "SELECT urgency, COUNT(*) AS count FROM tickets GROUP BY urgency ORDER BY urgency"
            )
        }
        ticket_count = self.connection.execute("SELECT COUNT(*) FROM tickets").fetchone()[0]
        review_count = self.connection.execute("SELECT COUNT(*) FROM review_queue").fetchone()[0]
        if review_count:
            by_team["Human Review"] = review_count
            by_urgency["needs_review"] = review_count
        return {
            "ticket_count": ticket_count,
            "review_count": review_count,
            "total_requests": ticket_count + review_count,
            "by_team": by_team,
            "by_urgency": by_urgency,
        }

    def close(self) -> None:
        self.connection.close()
