"""The harness action vocabulary.

Actions are plain dicts in the same shape as Anthropic's computer-use action
space (`{"action": "left_click", "coordinate": [x, y]}`, `{"action": "type",
"text": ...}`, ...), so the Claude adapter passes model output through
unchanged and other adapters (UI-TARS, Qwen-VL) translate into it.

The harness adds one meta-action: `{"action": "done"}` — the agent believes
the task is complete. `verify` decides whether it's right.
"""

from __future__ import annotations

# Actions the executor implements. "screenshot" is accepted but a no-op:
# the runner screenshots before every step regardless.
EXECUTABLE = {
    "screenshot",
    "left_click",
    "right_click",
    "middle_click",
    "double_click",
    "triple_click",
    "mouse_move",
    "left_click_drag",
    "type",
    "key",
    "scroll",
    "wait",
}

META = {"done"}


def validate(action: dict) -> str | None:
    """Return an error string for malformed actions, else None."""
    name = action.get("action")
    if name in META:
        return None
    if name not in EXECUTABLE:
        return f"unsupported action '{name}'"
    if name in {"left_click", "right_click", "middle_click", "double_click",
                "triple_click", "mouse_move", "scroll"} and "coordinate" not in action:
        return f"action '{name}' requires 'coordinate': [x, y]"
    if name in {"type", "key"} and not action.get("text"):
        return f"action '{name}' requires 'text'"
    if name == "left_click_drag" and ("start_coordinate" not in action or "coordinate" not in action):
        return "left_click_drag requires 'start_coordinate' and 'coordinate'"
    return None
