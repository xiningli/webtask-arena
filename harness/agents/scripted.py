"""Scripted oracle agent — the harness's own reference implementation.

It parses the natural-language instruction (never the oracle API) and emits
ordinary computer-use actions, but it locates click targets via the DOM
(`browser.center`) instead of pixels. Its purpose is to validate the full
pipeline — env → screenshot loop → action executor → server state → verify —
not to be a fair baseline. Model adapters must not receive the browser handle.
"""

from __future__ import annotations

import re
from typing import Iterator

from ..browser import Browser
from .base import Observation

# must match server/seeding.py TIMEZONES order (oracle knowledge, documented)
TIMEZONES = [
    "UTC", "America/Vancouver", "America/New_York", "Europe/Paris",
    "Europe/Berlin", "Asia/Tokyo", "Asia/Singapore", "Australia/Sydney",
]


class ScriptedAgent:
    def __init__(self, browser: Browser, task_id: str):
        self.browser = browser
        self.task_id = task_id
        self._plan: Iterator[dict] | None = None

    def begin(self, instruction: str) -> None:
        plans = {
            "email-triage": self._email_plan,
            "settings-panel": self._settings_plan,
            "checkout-form": self._checkout_plan,
        }
        if self.task_id not in plans:
            raise ValueError(f"scripted agent has no plan for '{self.task_id}'")
        self._plan = plans[self.task_id](instruction)

    def step(self, obs: Observation) -> dict:
        assert self._plan is not None, "begin() not called"
        try:
            return next(self._plan)
        except StopIteration:
            return {"action": "done"}

    # ------------------------------------------------------------------ plans

    def _click(self, selector: str, has_text: str | None = None) -> dict:
        x, y = self.browser.center(selector, has_text)
        return {"action": "left_click", "coordinate": [round(x), round(y)]}

    def _email_plan(self, instruction: str) -> Iterator[dict]:
        m = re.search(r"archive every email from (.+?) and star the email "
                      r"with the subject “(.+?)”", instruction)
        assert m, f"could not parse instruction: {instruction!r}"
        sender, subject = m.group(1), m.group(2)

        while self.browser.exists("tr.email-row", has_text=sender):
            row = f"tr.email-row:has(td.sender:text-is('{sender}'))"
            x, y = self.browser.center(f"{row} .archive-btn")
            yield {"action": "left_click", "coordinate": [round(x), round(y)]}
            yield {"action": "wait", "duration": 0.3}

        star_row = f"tr.email-row:has-text('{subject}')"
        yield self._click(f"{star_row} .star-btn")

    def _settings_plan(self, instruction: str) -> Iterator[dict]:
        m = re.search(r"set the timezone to (\S+?),", instruction)
        assert m, f"could not parse instruction: {instruction!r}"
        target_tz = m.group(1)

        yield self._click("#nav button", has_text="Appearance")
        yield self._click("input[data-field='dark_mode']")
        yield self._click("#nav button", has_text="General")
        # focus the timezone <select>, then arrow down from UTC (index 0)
        yield self._click("select[data-field='timezone']")
        for _ in range(TIMEZONES.index(target_tz)):
            yield {"action": "key", "text": "Down"}
        yield {"action": "key", "text": "Return"}  # close the dropdown
        yield self._click("#save")
        yield {"action": "wait", "duration": 0.3}

    def _checkout_plan(self, instruction: str) -> Iterator[dict]:
        m = re.search(r"checkout for (.+?) \(email: (.+?)\)\. "
                      r"Ship to (.+?), (.+?), ZIP (\d{5})", instruction)
        assert m, f"could not parse instruction: {instruction!r}"
        name, email, street, city, zip_code = m.groups()

        for field, value in (("#name", name), ("#email", email)):
            yield self._click(field)
            yield {"action": "type", "text": value}
        yield self._click("#next1")
        yield {"action": "wait", "duration": 0.3}

        for field, value in (("#street", street), ("#city", city), ("#zip", zip_code)):
            yield self._click(field)
            yield {"action": "type", "text": value}
        yield self._click("#next2")
        yield {"action": "wait", "duration": 0.3}

        yield self._click("#submit")
        yield {"action": "wait", "duration": 0.3}
