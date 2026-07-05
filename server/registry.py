"""Task registry. Adding a task = implement the Task protocol, register here."""

from __future__ import annotations

from typing import Any, Protocol

from .tasks.checkout_form import CheckoutForm
from .tasks.email_triage import EmailTriage
from .tasks.settings_panel import SettingsPanel


class Task(Protocol):
    id: str
    title: str
    template: str

    def generate(self, seed: int) -> dict[str, Any]:
        """Build a fresh, fully seed-determined episode state."""

    def instruction(self, state: dict[str, Any]) -> str:
        """Natural-language goal handed to the agent out-of-band."""

    def view(self, state: dict[str, Any]) -> dict[str, Any]:
        """Template context for rendering the task page."""

    def handle_action(self, state: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
        """Mutate state in response to a UI action. Return {'ok': bool, ...}."""

    def verify(self, state: dict[str, Any]) -> dict[str, bool]:
        """Named subgoals; episode succeeds iff all are true."""


_ALL = [EmailTriage(), SettingsPanel(), CheckoutForm()]
TASKS: dict[str, Task] = {t.id: t for t in _ALL}
