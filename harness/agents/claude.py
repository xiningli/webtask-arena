"""Claude computer-use adapter.

Drives the standard computer-use loop against the live browser: the model
receives screenshots as tool results and emits actions from the
`computer_20251124` action space, which the harness executes verbatim
(see harness/actions.py — the action vocabularies are identical).

Requires ANTHROPIC_API_KEY (or an `ant auth login` profile) in the
environment and `pip install anthropic`.
"""

from __future__ import annotations

import base64

from ..browser import VIEWPORT
from .base import Observation

BETA = "computer-use-2025-11-24"
MODEL = "claude-opus-4-8"

SYSTEM = (
    "You are completing a task in a web application shown in the screenshots. "
    "Use the computer tool to interact with it. The page is fully loaded when "
    "content is visible. When you believe the task is complete, stop calling "
    "tools and say you are done."
)


class ClaudeComputerUseAgent:
    def __init__(self, model: str = MODEL, viewport=VIEWPORT, max_tokens: int = 4096):
        import anthropic

        self.client = anthropic.Anthropic()
        self.model = model
        self.viewport = viewport
        self.max_tokens = max_tokens
        self.messages: list = []
        self._pending_tool_use: str | None = None

    def begin(self, instruction: str) -> None:
        self.messages = [{
            "role": "user",
            "content": [{"type": "text", "text": instruction}],
        }]
        self._pending_tool_use = None

    def step(self, obs: Observation) -> dict:
        image_block = {
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": "image/png",
                "data": base64.standard_b64encode(obs.screenshot_png).decode(),
            },
        }
        if self._pending_tool_use is None:
            # first step: attach the initial screenshot to the instruction turn
            self.messages[-1]["content"].append(image_block)
        else:
            content = []
            if obs.feedback:
                content.append({"type": "text", "text": obs.feedback})
            content.append(image_block)
            self.messages.append({
                "role": "user",
                "content": [{
                    "type": "tool_result",
                    "tool_use_id": self._pending_tool_use,
                    "content": content,
                }],
            })

        response = self.client.beta.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            betas=[BETA],
            thinking={"type": "adaptive"},
            system=SYSTEM,
            tools=[{
                "type": "computer_20251124",
                "name": "computer",
                "display_width_px": self.viewport[0],
                "display_height_px": self.viewport[1],
            }],
            messages=self.messages,
        )
        # append full content (incl. thinking blocks) — required for replay
        self.messages.append({"role": "assistant", "content": response.content})

        tool_use = next((b for b in response.content if b.type == "tool_use"), None)
        if tool_use is None:
            self._pending_tool_use = None
            return {"action": "done"}
        self._pending_tool_use = tool_use.id
        return dict(tool_use.input)
