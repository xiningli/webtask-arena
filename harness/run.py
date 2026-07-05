"""Episode runner + CLI.

    python -m harness.run --agent scripted --task all --seeds 0,1,2
    python -m harness.run --agent scripted --task email-triage --seeds 0 \
        --latency-ms 800 --layout-shift
    python -m harness.run --agent claude --task all --seeds 0-4   # needs API key

Each episode writes results/<run>/<task>_s<seed>/ containing step_NNN.png,
actions.jsonl, and result.json; the run directory gets summary.json.
The runner talks to the env via the oracle API (reset/verify); the agent
only ever sees screenshots.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx

from . import actions as action_spec
from .agents import make_agent
from .agents.base import Observation
from .browser import Browser

ALL_TASKS = ["email-triage", "settings-panel", "checkout-form"]
SETTLE_SECONDS = 0.4


def run_episode(browser, agent, base_url, task_id, seed, opts, out_dir, max_steps):
    out_dir.mkdir(parents=True, exist_ok=True)
    api = httpx.Client(base_url=base_url, timeout=15)

    reset = api.post(f"/api/{task_id}/reset",
                     json={"seed": seed, **opts}).raise_for_status().json()
    instruction = reset["instruction"]
    browser.open_task(task_id)
    agent.begin(instruction)

    feedback = None
    steps_taken = 0
    with open(out_dir / "actions.jsonl", "w") as log:
        for step in range(max_steps):
            png = browser.screenshot()
            (out_dir / f"step_{step:03d}.png").write_bytes(png)
            action = agent.step(Observation(
                instruction=instruction, step=step,
                screenshot_png=png, feedback=feedback,
            ))
            log.write(json.dumps({"step": step, "action": action,
                                  "feedback_in": feedback}) + "\n")
            steps_taken = step + 1
            if action.get("action") == "done":
                break
            feedback = action_spec.validate(action)
            if feedback is None:
                feedback = browser.execute(action)
            time.sleep(SETTLE_SECONDS)

    verdict = api.get(f"/api/{task_id}/verify").raise_for_status().json()
    result = {
        "task": task_id, "seed": seed, "opts": opts,
        "instruction": instruction, "steps": steps_taken,
        "success": verdict["success"], "subgoals": verdict["subgoals"],
    }
    (out_dir / "result.json").write_text(json.dumps(result, indent=2))
    api.close()
    return result


def parse_seeds(spec: str) -> list[int]:
    seeds = []
    for part in spec.split(","):
        if "-" in part:
            lo, hi = part.split("-")
            seeds.extend(range(int(lo), int(hi) + 1))
        else:
            seeds.append(int(part))
    return seeds


def main() -> int:
    p = argparse.ArgumentParser(description="WebTask Arena harness")
    p.add_argument("--agent", default="scripted", help="scripted | claude")
    p.add_argument("--task", default="all", help="task id or 'all'")
    p.add_argument("--seeds", default="0", help="e.g. 0,1,2 or 0-4")
    p.add_argument("--base-url", default="http://localhost:8000")
    p.add_argument("--latency-ms", type=int, default=0)
    p.add_argument("--layout-shift", action="store_true")
    p.add_argument("--max-steps", type=int, default=30)
    p.add_argument("--headed", action="store_true", help="show the browser")
    p.add_argument("--out", default="results")
    args = p.parse_args()

    tasks = ALL_TASKS if args.task == "all" else [args.task]
    seeds = parse_seeds(args.seeds)
    opts = {"latency_ms": args.latency_ms, "layout_shift": args.layout_shift}
    run_id = datetime.now(timezone.utc).strftime(f"%Y%m%d-%H%M%S-{args.agent}")
    run_dir = Path(args.out) / run_id

    browser = Browser(args.base_url, headless=not args.headed)
    results = []
    try:
        for task_id in tasks:
            for seed in seeds:
                agent = make_agent(args.agent, browser=browser, task_id=task_id)
                ep_dir = run_dir / f"{task_id}_s{seed}"
                result = run_episode(browser, agent, args.base_url, task_id,
                                     seed, opts, ep_dir, args.max_steps)
                results.append(result)
                status = "PASS" if result["success"] else "FAIL"
                failed = [k for k, v in result["subgoals"].items() if not v]
                print(f"[{status}] {task_id} seed={seed} steps={result['steps']}"
                      + (f" failed_subgoals={failed}" if failed else ""))
    finally:
        browser.close()

    by_task = {}
    for r in results:
        by_task.setdefault(r["task"], []).append(r["success"])
    summary = {
        "run_id": run_id, "agent": args.agent, "opts": opts,
        "episodes": len(results),
        "pass_rate": sum(r["success"] for r in results) / max(len(results), 1),
        "per_task": {t: {"pass": sum(v), "n": len(v)} for t, v in by_task.items()},
    }
    (run_dir / "summary.json").write_text(json.dumps(summary, indent=2))
    print(f"\npass rate: {summary['pass_rate']:.0%} "
          f"({sum(r['success'] for r in results)}/{len(results)}) -> {run_dir}")
    return 0 if summary["pass_rate"] == 1.0 else 1


if __name__ == "__main__":
    sys.exit(main())
