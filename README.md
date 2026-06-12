# Copilot SDK Computer Use

> **GitHub Copilot SDK port.** This is a community fork of the [Azure-Samples/computer-use](https://github.com/Azure-Samples/computer-use) sample, ported from its original OpenAI computer-use implementation to the [GitHub Copilot SDK](https://github.com/github/copilot-sdk). The computer actions are now exposed as custom Copilot SDK tools and the SDK drives the agentic loop. See [Acknowledgments](#acknowledgments).

A sample application that uses the [GitHub Copilot SDK](https://github.com/github/copilot-sdk) to control a computer through natural language instructions. It captures screenshots, analyzes the GUI, and performs mouse and keyboard actions to complete tasks. The Copilot SDK runs the agentic loop, and the computer-control capabilities are exposed to the model as custom SDK tools.

## Features

* Natural language computer control powered by the GitHub Copilot SDK
* Screenshot capture and analysis
* Mouse and keyboard control exposed as custom Copilot tools
* Cross-platform compatibility (Windows, macOS, Linux)
* Screen resolution scaling for consistent AI model input
* Selectable model and reasoning effort

## Model Selection

The default model is **`gpt-5.5`**. It was selected empirically with the bundled eval harness (`eval.py`, run 2026-06-11): across the test tasks all candidate models tied on judged success, so the deciding factor was efficiency — `gpt-5.5` completed tasks in the fewest steps and lowest latency, and at a fraction of the cost of Claude Opus 4.8 with no loss in capability. You can switch models at any time with `--model` (for example `--model claude-sonnet-4.6`), or run `--list-models` to see what your Copilot account exposes.

## Getting Started

### Prerequisites

* Python 3.11 or higher
* Operating System: Windows, macOS, or Linux
* The [GitHub Copilot CLI](https://github.com/github/copilot-cli) installed and authenticated. The CLI is bundled with the Python SDK and provides the model access — no separate API key is required.

### Installation

1. Clone the repository:
```bash
git clone https://github.com/dc995/computer-use
cd computer-use
```

2. Install the required packages:
```bash
pip install -r requirements.txt
```

3. Authenticate the GitHub Copilot CLI (one time):
```bash
copilot auth login
```
If you authenticate through the GitHub CLI instead, make sure the Copilot scope is granted:
```bash
gh auth login
gh auth refresh --scopes copilot
```
Verify the CLI is available:
```bash
copilot --version
```

## Usage

### Local Computer Control

The framework is designed to work directly with your local computer. Here's how to use it:

1. Run the example application:
```bash
python main.py --instructions "Open web browser and go to microsoft.com"
```

2. The agent will:
   - Take screenshots of your screen
   - Analyze the visual information
   - Call computer-control tools to complete the task
   - Observe the resulting screenshot and continue until the task is done

3. After the initial task completes, you can type follow-up instructions, or enter `exit` (or a blank line) to quit.

### Command Line Arguments

* `--instructions`: The initial task to perform (default: "Open web browser and go to microsoft.com.")
* `--model`: The Copilot model to use (default: `gpt-5.5`)
* `--reasoning-effort`: Reasoning effort for models that support it (`low`, `medium`, `high`, or `xhigh`; omit to use the model default)
* `--list-models`: List the models available to your Copilot account and exit
* `--timeout`: Seconds to allow each task to run before timing out (default: 1800)
* `--monitor`: Which display to view and control — `all` for the full virtual desktop spanning every monitor (default), or a 1-based monitor index (`1` = first/primary). Screenshots and clicks are offset to the chosen region, so the agent can see and act on windows that open on a secondary monitor.
* `--no-done`: Suppress the completion indicator. By default, when a run finishes the agent opens `done.html` (a full-screen "I'm done" banner) in your default browser so you get a clear visual signal that it's finished. Pass `--no-done` to disable it.

> **Known limitation (mixed-DPI multi-monitor):** Screen capture (`mss`) and input (`pyautogui`) share one coordinate space, which works reliably when all monitors use the **same** display-scaling/DPI. On setups where monitors run at *different* scaling factors (e.g. a 150% laptop panel beside a 100% external monitor), `pyautogui`'s physical-pixel clicks can drift on the lower-DPI display because it only sets system-level (not per-monitor v2) DPI awareness. Workaround: pin the agent to a single display with `--monitor 1` (or the relevant index). A future improvement would be to enable per-monitor-v2 DPI awareness and translate coordinates per monitor.

### Safety

This agent controls your **real** mouse and keyboard. It is configured to run autonomously: tool permissions are auto-approved (`PermissionHandler.approve_all`) and a custom system prompt replaces the SDK's default guardrails (`system_message` uses `mode: "replace"`). Only run it on a machine where you are comfortable letting it act on your behalf, and supervise it while it works.

### VM/Remote Control

For scenarios requiring remote computer control or VM automation, we recommend using Playwright. Playwright provides robust browser automation capabilities and is well-suited for VM-based testing and automation scenarios.

For more information on VM automation with Playwright, please refer to:
* [Playwright Documentation](https://playwright.dev/docs/intro)
* [Playwright VM Setup Guide](https://playwright.dev/docs/ci-intro)

## Resources

* [GitHub Copilot SDK](https://github.com/github/copilot-sdk)
* [GitHub Copilot CLI](https://github.com/github/copilot-cli)
* [PyAutoGUI Documentation](https://pyautogui.readthedocs.io/)

## Acknowledgments

This project is a port of the [Azure-Samples/computer-use](https://github.com/Azure-Samples/computer-use) sample (originally an OpenAI computer-use sample) to the [GitHub Copilot SDK](https://github.com/github/copilot-sdk). It is distributed under the [MIT License](LICENSE.md); the original copyright is retained alongside the port author's. Thanks to the upstream maintainers for the foundation this builds on.

## License

Released under the [MIT License](LICENSE.md).
