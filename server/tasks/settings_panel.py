"""Settings panel: enable dark mode (Appearance) and set a timezone
(General), then Save. The trap: draft changes don't count until saved,
and unrelated settings must stay untouched."""

from __future__ import annotations

from typing import Any

from ..seeding import TIMEZONES, rng

DEFAULTS = {
    "language": "English",
    "timezone": "UTC",
    "dark_mode": False,
    "compact_layout": False,
    "email_notifications": True,
    "push_notifications": False,
    "beta_features": False,
    "usage_analytics": True,
}

# which section of the UI each field lives in
SECTIONS = {
    "General": ["language", "timezone"],
    "Appearance": ["dark_mode", "compact_layout"],
    "Notifications": ["email_notifications", "push_notifications"],
    "Advanced": ["beta_features", "usage_analytics"],
}

LANGUAGES = ["English", "Français", "Deutsch", "日本語", "Español"]


class SettingsPanel:
    id = "settings-panel"
    title = "Settings"
    template = "settings_panel.html"

    def generate(self, seed: int) -> dict[str, Any]:
        r = rng(self.id, seed)
        target_tz = r.choice([tz for tz in TIMEZONES if tz != DEFAULTS["timezone"]])
        return {"saved": dict(DEFAULTS), "target_timezone": target_tz}

    def instruction(self, state: dict[str, Any]) -> str:
        return (
            "In Settings, enable Dark Mode and set the timezone to "
            f"{state['target_timezone']}, then save your changes. "
            "Leave every other setting as it is."
        )

    def view(self, state: dict[str, Any]) -> dict[str, Any]:
        return {
            "saved": state["saved"],
            "sections": SECTIONS,
            "timezones": TIMEZONES,
            "languages": LANGUAGES,
        }

    def handle_action(self, state: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
        if payload.get("op") != "save":
            return {"ok": False, "error": "unknown op"}
        draft = payload.get("draft", {})
        unknown = set(draft) - set(DEFAULTS)
        if unknown:
            return {"ok": False, "error": f"unknown fields: {sorted(unknown)}"}
        state["saved"].update(draft)
        return {"ok": True}

    def verify(self, state: dict[str, Any]) -> dict[str, bool]:
        saved = state["saved"]
        untouched = [k for k in DEFAULTS if k not in ("dark_mode", "timezone")]
        return {
            "dark_mode_saved": saved["dark_mode"] is True,
            "timezone_saved": saved["timezone"] == state["target_timezone"],
            "no_unrelated_changes": all(saved[k] == DEFAULTS[k] for k in untouched),
        }
