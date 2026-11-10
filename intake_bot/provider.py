from typing import Protocol

from .models import Classification


class Classifier(Protocol):
    def classify(self, request_text: str) -> Classification:
        """Return a routing recommendation for one request."""


class RuleBasedClassifier:
    """Deterministic local classifier used by the runnable sample."""

    _ROUTES = (
        ("security", "Security Operations", ("phishing", "suspicious", "malware", "security alert")),
        ("business_systems", "Business Systems", ("crm", "salesforce", "n8n", "automate", "workflow", "integration")),
        ("network", "Network Operations", ("vpn", "wi-fi", "wifi", "network", "internet")),
        ("hardware", "Endpoint Support", ("laptop", "monitor", "printer", "dock", "battery")),
        ("software", "Application Support", ("license", "install", "application", "software")),
        ("access", "Service Desk", ("password", "locked out", "account", "mfa", "multi-factor", "mailbox access")),
    )

    _CRITICAL_MARKERS = ("whole office", "all staff", "everyone", "company-wide", "entire office")
    _HIGH_MARKERS = (
        "down", "cannot work", "can't work", "locked out", "urgent", "today",
        "phishing", "suspicious", "malware",
    )
    _LOW_MARKERS = ("when possible", "next month", "no rush", "would like")

    def classify(self, request_text: str) -> Classification:
        text = request_text.casefold()
        urgency = self._urgency(text)
        for category, team, keywords in self._ROUTES:
            matches = sum(keyword in text for keyword in keywords)
            if matches:
                confidence = min(0.97, 0.88 + (matches - 1) * 0.04)
                return Classification(category, urgency, team, confidence)
        return Classification("needs_review", "unassigned", "Unassigned", 0.20)

    def _urgency(self, text: str) -> str:
        office_wide = "office" in text and any(scope in text for scope in ("whole", "entire", "all"))
        if office_wide or any(marker in text for marker in self._CRITICAL_MARKERS):
            return "critical"
        if any(marker in text for marker in self._HIGH_MARKERS):
            return "high"
        if any(marker in text for marker in self._LOW_MARKERS):
            return "low"
        return "normal"
