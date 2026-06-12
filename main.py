"""
Computer-use agent built on the GitHub Copilot SDK.

This sample drives a real computer with natural-language instructions. The
GitHub Copilot SDK runs the agentic loop: the model captures a screenshot,
decides the next action, calls the matching computer tool, observes the
resulting screenshot, and repeats until the task is complete.

The computer-control capability is exposed to the model as a set of custom SDK
tools (see ``cua.build_computer_tools``).

Prerequisites:
  * GitHub Copilot CLI installed and authenticated (``copilot auth login``)
  * ``pip install -r requirements.txt``
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
import webbrowser
from pathlib import Path
from urllib.parse import urlencode

import cua
import local_computer
from copilot import CopilotClient
from copilot.session import PermissionHandler
from copilot.session_events import SessionEventType


def signal_done(message: str | None = None) -> None:
    """Open ``done.html`` in the default browser as a visible 'finished' signal.

    Best-effort: silently does nothing if the page is missing or no browser can
    be launched. Pass ``message`` to show a short summary on the page.
    """
    page = Path(__file__).resolve().parent / "done.html"
    if not page.exists():
        return
    url = page.as_uri()
    if message:
        url += "?" + urlencode({"msg": message})
    try:
        webbrowser.open(url)
    except Exception:
        pass

# Default model chosen empirically (see eval.py, 2026-06-11). Across the eval
# tasks all candidate models tied on success, so the differentiator was
# efficiency: gpt-5.5 used the fewest tool calls and lowest latency, and was far
# cheaper than Claude Opus 4.8 for no gain. Override with --model, or run
# --list-models to see what your Copilot account exposes.
DEFAULT_MODEL = "gpt-5.5"

SYSTEM_PROMPT = """You are an autonomous computer-use agent that controls a real \
computer by calling tools.

The screen you control is {width}x{height} pixels. Coordinate (0, 0) is the \
top-left corner. Every coordinate you pass to a tool MUST fall inside that range. \
The screen may span multiple physical monitors arranged side by side, so it can \
be much wider than a single display; scan the whole screenshot for the relevant \
window, which may appear on the left or right portion of the screen.

Workflow:
1. Call `screenshot` first to see the current state of the screen.
2. Choose the single best next action and call the matching tool (click, \
double_click, move, scroll, type, keypress, drag, or wait).
3. Each action tool returns a fresh screenshot. Inspect it to confirm the action \
worked before deciding the next step.
4. Repeat until the user's task is complete, then briefly summarize what you did.

Rules:
- Only click coordinates that are visible in the most recent screenshot.
- Prefer keyboard shortcuts (keypress) when they are more reliable than clicking.
- If the UI is loading or animating, call `wait` and then take another screenshot.
- Work autonomously; do not ask the user to confirm individual actions.
"""


async def main():
    logging.basicConfig(level=logging.WARNING, format="%(message)s")
    logger = logging.getLogger(__name__)
    logger.setLevel(logging.INFO)

    parser = argparse.ArgumentParser(description="Copilot SDK computer-use agent")
    parser.add_argument(
        "--instructions",
        dest="instructions",
        default="Open web browser and go to microsoft.com.",
        help="Initial task to perform",
    )
    parser.add_argument(
        "--model",
        dest="model",
        default=DEFAULT_MODEL,
        help=f"Copilot model to use (default: {DEFAULT_MODEL})",
    )
    parser.add_argument(
        "--reasoning-effort",
        dest="reasoning_effort",
        choices=["low", "medium", "high", "xhigh"],
        default=None,
        help="Reasoning effort for models that support it (omit to use the model default)",
    )
    parser.add_argument(
        "--list-models",
        dest="list_models",
        action="store_true",
        help="List the models available to your Copilot account and exit",
    )
    parser.add_argument(
        "--timeout",
        dest="timeout",
        type=float,
        default=1800.0,
        help="Seconds to allow each task to run before timing out (default: 1800)",
    )
    parser.add_argument(
        "--monitor",
        dest="monitor",
        default="all",
        help="Which monitor to view and control: 'all' for the full virtual desktop "
        "spanning every display (default), or a 1-based monitor index (1 = first).",
    )
    parser.add_argument(
        "--no-done",
        dest="done_signal",
        action="store_false",
        help="Do not open the done.html 'I'm done' page in the browser when finished",
    )
    args = parser.parse_args()

    # Computer takes screenshots and performs mouse/keyboard actions.
    # Scaler resizes the screen to a model-friendly resolution and translates
    # the model's coordinates back to real screen coordinates.
    computer = cua.Scaler(local_computer.LocalComputer(monitor=args.monitor))
    tools = cua.build_computer_tools(computer)
    width, height = computer.dimensions

    async with CopilotClient() as client:
        if args.list_models:
            for model in await client.list_models():
                logger.info(f"{getattr(model, 'id', model)}\t{getattr(model, 'name', '')}")
            return

        # Log each tool call (the model's actions) as it happens. Permissions are
        # already auto-approved via on_permission_request, so this only logs.
        async def on_pre_tool_use(payload, invocation):
            logger.info(f"\n  -> {payload.toolName} {payload.toolArgs}")
            return None

        session_kwargs = dict(
            on_permission_request=PermissionHandler.approve_all,
            model=args.model,
            tools=tools,
            streaming=True,
            system_message={
                "mode": "replace",
                "content": SYSTEM_PROMPT.format(width=width, height=height),
            },
            hooks={"on_pre_tool_use": on_pre_tool_use},
        )
        if args.reasoning_effort:
            session_kwargs["reasoning_effort"] = args.reasoning_effort

        async with await client.create_session(**session_kwargs) as session:

            def on_event(event):
                if event.type == SessionEventType.ASSISTANT_MESSAGE_DELTA:
                    sys.stdout.write(event.data.delta_content or "")
                    sys.stdout.flush()

            session.on(on_event)

            user_input = args.instructions
            while True:
                if not user_input:
                    try:
                        user_input = input("\nUser (blank or 'exit' to quit): ").strip()
                    except EOFError:
                        break
                    if not user_input or user_input.lower() in {"exit", "quit"}:
                        break

                logger.info(f"\nUser: {user_input}")
                sys.stdout.write("\nAgent: ")
                sys.stdout.flush()
                await session.send_and_wait(user_input, timeout=args.timeout)
                print()
                user_input = ""

    if args.done_signal:
        signal_done("The computer-use agent has finished.")


if __name__ == "__main__":
    asyncio.run(main())
