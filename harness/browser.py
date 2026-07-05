"""Playwright wrapper: fixed-viewport browser + computer-use action executor.

Model agents interact only through `screenshot()` and `execute()` (pixels in,
mouse/keyboard out). `center()` is a DOM oracle used exclusively by the
scripted reference agent to validate the harness plumbing — never expose it
to a model under evaluation.
"""

from __future__ import annotations

import time

from playwright.sync_api import sync_playwright

VIEWPORT = (1280, 800)

# xdotool-style key names (what computer-use models emit) -> Playwright names
_KEY_MAP = {
    "return": "Enter",
    "enter": "Enter",
    "kp_enter": "Enter",
    "tab": "Tab",
    "escape": "Escape",
    "esc": "Escape",
    "backspace": "Backspace",
    "delete": "Delete",
    "space": "Space",
    "up": "ArrowUp",
    "down": "ArrowDown",
    "left": "ArrowLeft",
    "right": "ArrowRight",
    "page_down": "PageDown",
    "page_up": "PageUp",
    "home": "Home",
    "end": "End",
    "ctrl": "Control",
    "control": "Control",
    "alt": "Alt",
    "shift": "Shift",
    "super": "Meta",
    "cmd": "Meta",
    "meta": "Meta",
}


def _translate_key(combo: str) -> str:
    parts = [p.strip() for p in combo.replace(" ", "+").split("+") if p.strip()]
    out = []
    for p in parts:
        mapped = _KEY_MAP.get(p.lower())
        out.append(mapped if mapped else (p if len(p) > 1 else p))
    return "+".join(out)


class Browser:
    def __init__(self, base_url: str, headless: bool = True, viewport=VIEWPORT):
        self.base_url = base_url.rstrip("/")
        self.viewport = viewport
        self._pw = sync_playwright().start()
        self._browser = self._pw.chromium.launch(headless=headless)
        self.page = self._browser.new_page(
            viewport={"width": viewport[0], "height": viewport[1]}
        )

    def close(self) -> None:
        self._browser.close()
        self._pw.stop()

    def open_task(self, task_id: str, timeout_ms: int = 15000) -> None:
        self.page.goto(f"{self.base_url}/task/{task_id}")
        # env may be running with an artificial-latency flag; wait it out
        self.page.wait_for_selector("#app", state="visible", timeout=timeout_ms)

    def screenshot(self) -> bytes:
        return self.page.screenshot(type="png")

    def execute(self, action: dict) -> str | None:
        """Execute a computer-use action dict. Returns feedback text or None."""
        name = action["action"]
        page = self.page
        if name == "screenshot":
            return None
        if name in {"left_click", "right_click", "middle_click",
                    "double_click", "triple_click"}:
            x, y = action["coordinate"]
            button = {"right_click": "right", "middle_click": "middle"}.get(name, "left")
            clicks = {"double_click": 2, "triple_click": 3}.get(name, 1)
            modifiers = [_translate_key(m) for m in action.get("text", "").split("+") if m]
            for m in modifiers:
                page.keyboard.down(m)
            page.mouse.click(x, y, button=button, click_count=clicks)
            for m in reversed(modifiers):
                page.keyboard.up(m)
            return None
        if name == "mouse_move":
            x, y = action["coordinate"]
            page.mouse.move(x, y)
            return None
        if name == "left_click_drag":
            sx, sy = action["start_coordinate"]
            ex, ey = action["coordinate"]
            page.mouse.move(sx, sy)
            page.mouse.down()
            page.mouse.move(ex, ey, steps=12)
            page.mouse.up()
            return None
        if name == "type":
            page.keyboard.type(action["text"], delay=15)
            return None
        if name == "key":
            page.keyboard.press(_translate_key(action["text"]))
            return None
        if name == "scroll":
            x, y = action["coordinate"]
            direction = action.get("scroll_direction", "down")
            amount = int(action.get("scroll_amount", 3))
            dx, dy = 0, 0
            if direction == "down":
                dy = amount * 120
            elif direction == "up":
                dy = -amount * 120
            elif direction == "right":
                dx = amount * 120
            elif direction == "left":
                dx = -amount * 120
            page.mouse.move(x, y)
            page.mouse.wheel(dx, dy)
            return None
        if name == "wait":
            time.sleep(min(float(action.get("duration", 1.0)), 5.0))
            return None
        return f"action '{name}' is not supported in this environment"

    # ------------------------------------------------------------- DOM oracle
    def center(self, selector: str, has_text: str | None = None) -> tuple[float, float]:
        """Center of an element's bounding box. Scripted reference agent only."""
        loc = self.page.locator(selector)
        if has_text is not None:
            loc = loc.filter(has_text=has_text)
        box = loc.first.bounding_box()
        if box is None:
            raise LookupError(f"element not visible: {selector!r} (text={has_text!r})")
        return box["x"] + box["width"] / 2, box["y"] + box["height"] / 2

    def exists(self, selector: str, has_text: str | None = None) -> bool:
        loc = self.page.locator(selector)
        if has_text is not None:
            loc = loc.filter(has_text=has_text)
        return loc.count() > 0
