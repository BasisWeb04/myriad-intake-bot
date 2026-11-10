from dataclasses import dataclass


@dataclass(frozen=True)
class Classification:
    category: str
    urgency: str
    owning_team: str
    confidence: float


@dataclass(frozen=True)
class ProcessResult:
    request_id: str
    status: str
    message: str
