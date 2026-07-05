#!/usr/bin/env python3
"""Package recorded agent episodes into the Space's replay-player format.

Input: run directories produced by an arena runner (uitars-webtask-eval's
run_arena.py or this repo's harness) containing frames/, transcript.txt, and
result.json. Frames are assumed to be saved 8x per step (video padding);
one frame per step is kept, downscaled to JPEG.

    python3 scripts/build_replays.py --agent "UI-TARS-1.5-7B (4-bit)" RUN_DIR...

Output: server/static/replays/<task>/step_NNN.jpg + replay.json, and a
top-level manifest.json the landing/replay/play pages read.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from PIL import Image

OUT_ROOT = Path(__file__).resolve().parent.parent / "server" / "static" / "replays"
FRAME_DUP = 8      # frames saved per step by the runners
JPEG_WIDTH = 880
JPEG_QUALITY = 68

_STEP = re.compile(r"^\[step (\d+)\] (\w+) point=([^ ]+) .*?content=(.*)$")

DIAGNOSIS = {
    "checkout-form": "Clean run: precise field clicks, correct typing, "
                     "three wizard steps, submit.",
    "email-triage": "State-tracking failure: archives worked, but the model never "
                    "perceived rows disappearing — it re-clicked fixed coordinates "
                    "while the list reflowed underneath, archiving 7 extra emails "
                    "while blaming 'an unresponsive system'.",
    "settings-panel": "Environment finding: headless chromium renders native "
                      "<select> dropdowns outside the page — the timezone options "
                      "are invisible to any screenshot agent. Dark Mode itself was "
                      "correctly enabled and saved.",
}


def parse_transcript(path: Path) -> list[dict]:
    steps, current = [], None
    for line in path.read_text().splitlines():
        m = _STEP.match(line)
        if m:
            current = {"step": int(m.group(1)), "action": m.group(2),
                       "point": m.group(3), "content": m.group(4), "thought": ""}
            steps.append(current)
        elif current is not None and line.strip().startswith("thought:"):
            current["thought"] = line.split("thought:", 1)[1].strip()
    return steps


def action_label(s: dict) -> str:
    label = s["action"]
    if s["point"] not in ("None", ""):
        label += f" @ {s['point']}"
    if s["content"] not in ("None", "''", '""'):
        label += f" {s['content']}"
    return label


def build_one(run_dir: Path, agent: str) -> dict:
    result = json.loads((run_dir / "result.json").read_text())
    task = result["task"]
    steps = parse_transcript(run_dir / "transcript.txt")
    frames = sorted((run_dir / "frames").glob("frame_*.png"))

    out_dir = OUT_ROOT / task
    out_dir.mkdir(parents=True, exist_ok=True)
    step_entries = []
    for s in steps:
        idx = s["step"] * FRAME_DUP
        if idx >= len(frames):
            break
        img = Image.open(frames[idx]).convert("RGB")
        img = img.resize((JPEG_WIDTH, round(img.height * JPEG_WIDTH / img.width)))
        name = f"step_{s['step']:03d}.jpg"
        img.save(out_dir / name, quality=JPEG_QUALITY, optimize=True)
        step_entries.append({"img": name, "action": action_label(s),
                             "thought": s["thought"]})

    # trailing "final state" frame, if recorded beyond the last step
    final_idx = len(steps) * FRAME_DUP
    if final_idx < len(frames):
        img = Image.open(frames[final_idx]).convert("RGB")
        img = img.resize((JPEG_WIDTH, round(img.height * JPEG_WIDTH / img.width)))
        img.save(out_dir / "final.jpg", quality=JPEG_QUALITY, optimize=True)
        step_entries.append({"img": "final.jpg", "action": "final state",
                             "thought": ""})

    entry = {
        "task": task,
        "agent": agent,
        "seed": result["seed"],
        "instruction": result["instruction"],
        "success": result["success"],
        "subgoals": result["subgoals"],
        "diagnosis": DIAGNOSIS.get(task, ""),
        "steps": step_entries,
    }
    (out_dir / "replay.json").write_text(json.dumps(entry, indent=1))
    return entry


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("run_dirs", nargs="+", type=Path)
    ap.add_argument("--agent", default="UI-TARS-1.5-7B (4-bit)")
    args = ap.parse_args()

    manifest = [build_one(d, args.agent) for d in args.run_dirs]
    OUT_ROOT.mkdir(parents=True, exist_ok=True)
    # manifest omits per-step data to keep the landing page light
    slim = [{k: v for k, v in e.items() if k != "steps"} | {"n_steps": len(e["steps"])}
            for e in manifest]
    (OUT_ROOT / "manifest.json").write_text(json.dumps(slim, indent=1))
    total = sum(f.stat().st_size for f in OUT_ROOT.rglob("*") if f.is_file())
    print(f"built {len(manifest)} replays -> {OUT_ROOT} ({total/1e6:.1f} MB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
