from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional

@dataclass
class QueryIntent:
    event_type: Optional[str] = None
    label: Optional[str] = None
    zone: Optional[str] = None
    summarize: bool = False
    attributes: Dict[str, str] = field(default_factory=dict)


def parse_question(question: str) -> QueryIntent:
    q = question.lower()
    intent = QueryIntent()
    if "summarize" in q or "summary" in q:
        intent.summarize = True
    if "person" in q or "someone" in q or "who" in q:
        intent.label = "person"
        intent.event_type = "person_detected"
    if "vehicle" in q or "car" in q or "bike" in q:
        intent.label = "vehicle"
        intent.event_type = "vehicle_detected"
    if "motion" in q or "activity" in q:
        intent.event_type = intent.event_type or "motion_detected"
    if "gate" in q:
        intent.zone = "gate"
    if "red shirt" in q or "red-shirt" in q:
        intent.attributes["shirt_color"] = "red"
    if "after closing" in q or "after hours" in q:
        intent.event_type = intent.event_type or "after_hours_entry"
    return intent
