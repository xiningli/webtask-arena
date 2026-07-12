"""Causal gate: a form field that exists *only because* of a prior causal
choice elsewhere on the page, plus an always-visible, causally-unrelated
decoy field with the same shape. Tests whether the agent has a genuine
cause-effect model of the UI, versus the failure mode UI-TARS's authors
flag in their thought-annotation process (arXiv:2501.12326 sec 4.4): a
thought that matches its action "only by coincidence rather than through
logical reasoning." A superficial pattern-matcher sees "discount context +
code-shaped field" and types the code into whichever field is visible first
(the gift card field) instead of recognizing the referral field's existence
is conditional on the dropdown selection.

Like `settings-panel`, only the state as of the "Save changes" click counts
— fields are read live from the DOM at save time, there is no separate
per-field commit step (an earlier version required one via a per-field
"Apply" button with no visual cue, which meant a typed-but-unsaved value
looked identical to a saved one in a screenshot; that tested "did you guess
an undocumented UI convention," not causal reasoning, so it was removed)."""

from __future__ import annotations

from typing import Any

from ..seeding import rng

SOURCES = ["Search engine", "Social media", "Friend referral", "Online advertisement", "Other"]
UNLOCKING_SOURCE = "Friend referral"
CODE_CHARS = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


class CausalGate:
    id = "causal-gate"
    title = "Account Settings"
    template = "causal_gate.html"

    def generate(self, seed: int) -> dict[str, Any]:
        r = rng(self.id, seed)
        code = "".join(r.choice(CODE_CHARS) for _ in range(6))
        return {
            "expected_code": code,
            "source": SOURCES[0],
            "code_value": "",
            "gift_card_value": "",
            "saved": False,
        }

    def instruction(self, state: dict[str, Any]) -> str:
        return (
            'You heard about us from a friend. Set "How did you hear about us?" to '
            f'"{UNLOCKING_SOURCE}", then enter the referral code {state["expected_code"]} '
            "in the field that appears. Leave the gift card field blank. Save your changes."
        )

    def view(self, state: dict[str, Any]) -> dict[str, Any]:
        return {"sources": SOURCES, "source": state["source"]}

    def handle_action(self, state: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
        op = payload.get("op")
        if op == "set_source":
            value = payload.get("value")
            if value not in SOURCES:
                return {"ok": False, "error": "unknown source"}
            state["source"] = value
            return {"ok": True}
        if op == "save":
            draft = payload.get("draft", {})
            state["code_value"] = str(draft.get("referral_code", "")).strip()
            state["gift_card_value"] = str(draft.get("gift_card", "")).strip()
            state["saved"] = True
            return {"ok": True}
        return {"ok": False, "error": f"unknown op '{op}'"}

    def verify(self, state: dict[str, Any]) -> dict[str, bool]:
        return {
            "source_selected_correctly": state["source"] == UNLOCKING_SOURCE,
            "referral_code_correct": (
                state["source"] == UNLOCKING_SOURCE
                and state["code_value"] == state["expected_code"]
            ),
            "gift_card_untouched": not state["gift_card_value"],
            "saved": state["saved"] is True,
        }
