"""Flash-offer: a discount code that rotates on a fixed wall-clock schedule,
independent of anything the agent does. Tests whether the agent re-perceives
the *current* on-screen value right before acting, rather than trusting a
value it read a few steps earlier — the exogenous-time analogue of the
list-reflow-after-own-action failure `email-triage` already found in
practice (see ../../ui-tars-example/testing/README.md). Because grading is
tied to real elapsed time, this task's pass/fail is not seed-pure the way
the other tasks are — same-seed re-resets get the same *code set* but not
the same *currently-valid code* at an arbitrary later instant, so it's kept
out of the fully-generic determinism tests and given its own in
tests/test_environment.py. Known v0 limitation: only 4 candidate codes
cycle, so an agent could pass by unwitting sequential guessing within the
step budget rather than genuine perception; not a design goal to close here."""

from __future__ import annotations

import json
import time
from typing import Any

from ..seeding import rng

CODE_POOL = ["NOVA", "ZEST", "GLOW", "FLUX", "PEAK", "SPARK", "ECHO", "BOLT"]
CYCLE_SECONDS = 8


class FlashOffer:
    id = "flash-offer"
    title = "Flash Sale"
    template = "flash_offer.html"

    def generate(self, seed: int) -> dict[str, Any]:
        r = rng(self.id, seed)
        codes = r.sample(CODE_POOL, 4)
        return {
            "codes": codes,
            "start_ts": time.time(),
            "redeemed": False,
            "redeemed_code": None,
            "redeemed_code_correct": None,
        }

    def instruction(self, state: dict[str, Any]) -> str:
        return (
            "A flash-sale discount code is shown on the page and rotates every "
            "few seconds. Read whichever code is CURRENTLY displayed — not one "
            "you saw earlier — type it into the box, and click Redeem."
        )

    def view(self, state: dict[str, Any]) -> dict[str, Any]:
        return {
            "codes_json": json.dumps(state["codes"]),
            "start_ts_ms": int(state["start_ts"] * 1000),
            "cycle_seconds": CYCLE_SECONDS,
        }

    def _current_code(self, state: dict[str, Any]) -> str:
        elapsed = time.time() - state["start_ts"]
        idx = int(elapsed // CYCLE_SECONDS) % len(state["codes"])
        return state["codes"][idx]

    def handle_action(self, state: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
        if payload.get("op") != "redeem":
            return {"ok": False, "error": f"unknown op '{payload.get('op')}'"}
        code = str(payload.get("code", "")).strip().upper()
        current = self._current_code(state)
        state["redeemed"] = True
        state["redeemed_code"] = code
        state["redeemed_code_correct"] = code == current
        return {"ok": True, "correct": state["redeemed_code_correct"]}

    def verify(self, state: dict[str, Any]) -> dict[str, bool]:
        return {
            "redeemed": state["redeemed"] is True,
            "code_matched_live_value": state["redeemed_code_correct"] is True,
        }
