"""Agent interface: screenshots in, computer-use action dicts out."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass
class Observation:
    instruction: str
    step: int
    screenshot_png: bytes
    feedback: str | None = None  # error/info from executing the previous action


class Agent(Protocol):
    def begin(self, instruction: str) -> None:
        """Start a fresh episode."""

    def step(self, obs: Observation) -> dict:
        """Return the next action dict (see harness/actions.py)."""
