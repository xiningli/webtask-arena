"""Deterministic data pools. All episode randomness must flow through
`rng(task_id, seed)` so identical (task, seed) pairs replay identically."""

from __future__ import annotations

import random

FIRST_NAMES = [
    "Ava", "Noah", "Mia", "Liam", "Zoe", "Ethan", "Ruby", "Owen",
    "Isla", "Felix", "Nora", "Jasper", "Cleo", "Hugo", "Iris", "Miles",
]

LAST_NAMES = [
    "Tanaka", "Okafor", "Silva", "Novak", "Haddad", "Larsen", "Moreau",
    "Kaur", "Petrov", "Nguyen", "Rossi", "Andersson", "Mbeki", "Fischer",
]

EMAIL_DOMAINS = ["lumenmail.com", "postbox.io", "quillmail.net", "arcmail.org"]

TOPICS = [
    "Quarterly budget", "Team offsite", "Design review", "Security audit",
    "Roadmap draft", "Onboarding checklist", "Server migration", "Launch retro",
    "Hiring loop", "API deprecation", "Holiday schedule", "Expense report",
    "Incident postmortem", "Beta feedback", "License renewal", "Data backfill",
]

PREVIEWS = [
    "quick question about the timeline",
    "sharing the latest numbers before the sync",
    "can you take a look when you get a chance",
    "final version attached for sign-off",
    "following up on last week's thread",
    "notes from the meeting are inside",
    "please review before Thursday",
    "heads up on a change of plans",
]

STREETS = ["Maple Ave", "Birch St", "Harbor Rd", "Summit Blvd", "Cedar Ln", "Willow Way"]

CITIES = ["Riverton", "Lakewood", "Fairview", "Brookside", "Kingsport", "Milltown"]

TIMEZONES = [
    "UTC", "America/Vancouver", "America/New_York", "Europe/Paris",
    "Europe/Berlin", "Asia/Tokyo", "Asia/Singapore", "Australia/Sydney",
]

PRODUCTS = ["Standing Desk Mat", "Mechanical Keyboard", "USB-C Dock", "Desk Lamp", "Monitor Arm"]


def rng(task_id: str, seed: int) -> random.Random:
    return random.Random(f"{task_id}::{seed}")


def person(r: random.Random) -> dict[str, str]:
    first, last = r.choice(FIRST_NAMES), r.choice(LAST_NAMES)
    return {
        "name": f"{first} {last}",
        "email": f"{first.lower()}.{last.lower()}@{r.choice(EMAIL_DOMAINS)}",
    }
