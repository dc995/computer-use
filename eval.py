"""
Model eval harness for the computer-use agent.

For each (model, task) pair it:
  1. Resets the desktop (Win+D) to a consistent starting state.
  2. Runs the task live on this machine using the same tools and system prompt
     as ``main.py``, counting tool calls (steps), wall-clock latency, and token /
     cost usage reported by the SDK.
  3. Captures the final screenshot and asks a fixed judge model to score how well
     the success criteria were met (LLM-as-judge, 0.0-1.0).

Results are printed as a table and written to ``eval_results.json``.

WARNING: This drives the REAL mouse and keyboard and consumes premium model
quota across several models. Run it supervised, and only with benign tasks.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import time
from dataclasses import asdict, dataclass, field

import cua
import local_computer
from copilot import CopilotClient
from copilot.session import PermissionHandler
from copilot.session_events import SessionEventType
from main import SYSTEM_PROMPT, signal_done

# Benign, supervised tasks. Each has a natural-language goal plus a success
# criteria string handed to the judge.
DEFAULT_TASKS: list[dict[str, str]] = [
    {
        "id": "browser_microsoft",
        "instruction": (
            "Open a web browser and navigate to https://www.microsoft.com. "
            "Wait until the Microsoft homepage has fully loaded and is visible — "
            "the page content must be rendered and the address bar must show "
            "microsoft.com — before you finish. Use the wait tool and take another "
            "screenshot if the page is still loading."
        ),
        "criteria": "A web browser is open and showing the Microsoft homepage (microsoft.com).",
    },
    {
        "id": "open_notepad",
        "instruction": "Open the Notepad application.",
        "criteria": "The Notepad application window is open and visible on screen.",
    },
    {
        "id": "settings_about",
        "instruction": "Open the Windows Settings app and go to the System > About page.",
        "criteria": "The Windows Settings app is open and showing the System About page.",
    },
]

JUDGE_PROMPT = """You are a strict evaluator of a computer-use agent.

The agent was asked to perform this task:
{instruction}

Success criteria:
{criteria}

The attached image is the FINAL screenshot of the screen after the agent stopped.
Judge only what is visible in the screenshot. Respond with ONLY a JSON object and
nothing else, in this exact form:
{{"success": <number between 0.0 and 1.0>, "reason": "<one short sentence>"}}
Use 1.0 if the criteria are fully met, 0.0 if not met at all, and a value in
between for partial success.
"""


@dataclass
class RunResult:
    model: str
    task_id: str
    success: float | None = None
    reason: str = ""
    steps: int = 0
    latency_s: float = 0.0
    input_tokens: int = 0
    output_tokens: int = 0
    reasoning_tokens: int = 0
    cost: float = 0.0
    error: str | None = None


@dataclass
class _Usage:
    input_tokens: int = 0
    output_tokens: int = 0
    reasoning_tokens: int = 0
    cost: float = 0.0
    text: str = ""
    steps: int = 0


def _attach_collectors(session, usage: _Usage):
    """Subscribe to a session to accumulate token usage and assistant text."""

    def on_event(event):
        if event.type == SessionEventType.ASSISTANT_USAGE:
            d = event.data
            usage.input_tokens += getattr(d, "input_tokens", 0) or 0
            usage.output_tokens += getattr(d, "output_tokens", 0) or 0
            usage.reasoning_tokens += getattr(d, "reasoning_tokens", 0) or 0
            usage.cost += getattr(d, "cost", 0.0) or 0.0
        elif event.type == SessionEventType.ASSISTANT_MESSAGE_DELTA:
            usage.text += event.data.delta_content or ""

    session.on(on_event)


async def run_task(
    client: CopilotClient, model: str, computer, tools, task, timeout: float, judge_model: str
) -> RunResult:
    result = RunResult(model=model, task_id=task["id"])
    usage = _Usage()

    async def on_pre_tool_use(payload, invocation):
        usage.steps += 1
        return None

    try:
        # Reset to a consistent starting point and let the desktop settle.
        await computer.keypress(["win", "d"])
        await computer.wait(1500)

        width, height = computer.dimensions
        session_kwargs = dict(
            on_permission_request=PermissionHandler.approve_all,
            model=model,
            tools=tools,
            streaming=True,
            system_message={
                "mode": "replace",
                "content": SYSTEM_PROMPT.format(width=width, height=height),
            },
            hooks={"on_pre_tool_use": on_pre_tool_use},
        )
        async with await client.create_session(**session_kwargs) as session:
            _attach_collectors(session, usage)
            t0 = time.monotonic()
            await session.send_and_wait(task["instruction"], timeout=timeout)
            result.latency_s = round(time.monotonic() - t0, 2)

        result.steps = usage.steps
        result.input_tokens = usage.input_tokens
        result.output_tokens = usage.output_tokens
        result.reasoning_tokens = usage.reasoning_tokens
        result.cost = round(usage.cost, 6)

        # Let the screen settle (e.g. a page finishing loading) before scoring.
        await computer.wait(3000)
        final_png = await computer.screenshot()
        score, reason = await judge(client, task, final_png, judge_model)
        result.success = score
        result.reason = reason
    except Exception as exc:  # noqa: BLE001 - record and continue to next run
        result.error = f"{type(exc).__name__}: {exc}"
    return result


async def judge(client: CopilotClient, task, screenshot_b64: str, judge_model: str) -> tuple[float | None, str]:
    usage = _Usage()
    attachment = {
        "type": "blob",
        "data": screenshot_b64,
        "mimeType": "image/png",
        "displayName": "final_screenshot.png",
    }
    async with await client.create_session(
        model=judge_model,
        streaming=True,
        system_message={"mode": "replace", "content": "You are a precise visual evaluator."},
    ) as session:
        _attach_collectors(session, usage)
        prompt = JUDGE_PROMPT.format(instruction=task["instruction"], criteria=task["criteria"])
        await session.send_and_wait(prompt, attachments=[attachment], timeout=120.0)

    text = usage.text.strip()
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        return None, f"unparseable judge output: {text[:120]}"
    try:
        data = json.loads(match.group(0))
        return float(data.get("success")), str(data.get("reason", ""))
    except (ValueError, TypeError) as exc:
        return None, f"bad judge JSON ({exc}): {text[:120]}"


def print_table(results: list[RunResult]) -> None:
    header = f"{'model':<26}{'task':<20}{'ok':>5}{'steps':>7}{'lat(s)':>9}{'in':>9}{'out':>9}{'cost':>10}"
    print("\n" + header)
    print("-" * len(header))
    for r in results:
        ok = "ERR" if r.error else ("-" if r.success is None else f"{r.success:.2f}")
        print(
            f"{r.model:<26}{r.task_id:<20}{ok:>5}{r.steps:>7}{r.latency_s:>9}"
            f"{r.input_tokens:>9}{r.output_tokens:>9}{r.cost:>10.4f}"
        )

    print("\nPer-model averages (successful judged runs only):")
    by_model: dict[str, list[RunResult]] = {}
    for r in results:
        by_model.setdefault(r.model, []).append(r)
    ranked = []
    for model, runs in by_model.items():
        scored = [r for r in runs if r.success is not None]
        if scored:
            avg_success = sum(r.success for r in scored) / len(scored)
            avg_steps = sum(r.steps for r in scored) / len(scored)
            avg_lat = sum(r.latency_s for r in scored) / len(scored)
            total_cost = sum(r.cost for r in runs)
        else:
            avg_success = avg_steps = avg_lat = total_cost = 0.0
        ranked.append((model, avg_success, avg_steps, avg_lat, total_cost))
    ranked.sort(key=lambda x: x[1], reverse=True)
    for model, avg_success, avg_steps, avg_lat, total_cost in ranked:
        print(
            f"  {model:<26} success={avg_success:.2f}  steps={avg_steps:.1f}  "
            f"latency={avg_lat:.1f}s  total_cost={total_cost:.4f}"
        )
    if ranked and ranked[0][1] > 0:
        print(f"\nBest by judged success: {ranked[0][0]}")


async def main():
    parser = argparse.ArgumentParser(description="Eval candidate models on computer-use tasks")
    parser.add_argument(
        "--models",
        nargs="+",
        default=[
            "claude-opus-4.8",
            "claude-sonnet-4.6",
            "gpt-5.5",
            "gemini-3.1-pro-preview",
        ],
        help="Candidate models to compare",
    )
    parser.add_argument(
        "--judge-model",
        default="gpt-5.5",
        help="Model used to score the final screenshots (default: gpt-5.5, a neutral judge)",
    )
    parser.add_argument(
        "--tasks",
        nargs="*",
        default=None,
        help="Subset of task ids to run (default: all)",
    )
    parser.add_argument("--timeout", type=float, default=600.0, help="Per-task timeout (seconds)")
    parser.add_argument("--output", default="eval_results.json", help="Where to write JSON results")
    parser.add_argument(
        "--monitor",
        default="all",
        help="Which monitor to view/control: 'all' (default) or a 1-based index.",
    )
    parser.add_argument(
        "--no-done",
        dest="done_signal",
        action="store_false",
        help="Do not open the done.html 'I'm done' page in the browser when finished",
    )
    args = parser.parse_args()

    tasks = DEFAULT_TASKS
    if args.tasks:
        tasks = [t for t in DEFAULT_TASKS if t["id"] in args.tasks]
    if not tasks:
        raise SystemExit("No matching tasks.")

    total = len(args.models) * len(tasks)
    print(
        f"Running {total} live runs ({len(args.models)} models x {len(tasks)} tasks).\n"
        "This drives the real mouse/keyboard and uses premium quota. Ctrl+C to abort.\n"
        f"Models: {', '.join(args.models)}\n"
        f"Judge:  {args.judge_model}"
    )

    computer = cua.Scaler(local_computer.LocalComputer(monitor=args.monitor))
    tools = cua.build_computer_tools(computer)

    results: list[RunResult] = []
    async with CopilotClient() as client:
        for model in args.models:
            for task in tasks:
                print(f"\n=== {model} / {task['id']} ===")
                r = await run_task(client, model, computer, tools, task, args.timeout, args.judge_model)
                status = r.error or (f"success={r.success}" if r.success is not None else "unjudged")
                print(f"  -> {status}  steps={r.steps}  latency={r.latency_s}s")
                results.append(r)

    print_table(results)
    with open(args.output, "w", encoding="utf-8") as fh:
        json.dump([asdict(r) for r in results], fh, indent=2)
    print(f"\nWrote {args.output}")

    if args.done_signal:
        judged = [r for r in results if r.success is not None]
        avg = (sum(r.success for r in judged) / len(judged)) if judged else 0.0
        signal_done(f"Eval finished: {len(results)} runs, avg success {avg:.2f}.")


if __name__ == "__main__":
    asyncio.run(main())
