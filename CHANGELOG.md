## Computer Use Changelog

<a name="1.0.0-copilot"></a>
# 1.0.0 (2026-06-11) — GitHub Copilot SDK port

This release is a community fork of the [Azure-Samples/computer-use](https://github.com/Azure-Samples/computer-use)
sample, ported from its original OpenAI computer-use implementation to the
[GitHub Copilot SDK](https://github.com/github/copilot-sdk). It intentionally deviates from the
upstream sample's goal of demonstrating the Azure/OpenAI integration: here the computer-control
capabilities are exposed as custom Copilot SDK tools and the SDK drives the agentic loop.

*Features*
* Ported the agentic loop and computer-control tools to the GitHub Copilot SDK (authenticated via the Copilot CLI; no API key required).
* Added multi-monitor support: `LocalComputer(monitor=...)` captures the full virtual desktop by default (`--monitor all`) or a specific 1-based monitor, using `mss`. Input coordinates are offset to the target monitor's origin so clicks land correctly across displays.
* Added a completion indicator: on finish the agent opens a full-screen `done.html` banner (disable with `--no-done`).
* Added CLI options: `--model`, `--reasoning-effort`, `--list-models`, `--timeout`, `--monitor`, and `--no-done`.

*Bug Fixes*
* Fixed universal browser-task failures caused by the agent only capturing the primary monitor while the browser opened on a secondary display; the capture space now matches the input space.

*Breaking Changes*
* Replaced the OpenAI computer-use backend with the GitHub Copilot SDK; configuration and model names now follow the Copilot SDK.

<a name="x.y.z"></a>
# x.y.z (yyyy-mm-dd)

*Features*
* ...

*Bug Fixes*
* ...

*Breaking Changes*
* ...
