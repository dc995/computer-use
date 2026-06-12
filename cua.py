"""
Computer-use tooling for the GitHub Copilot SDK.

The original implementation drove the OpenAI Responses API "computer" tool
directly. This version exposes the local computer's capabilities (screenshot,
click, type, scroll, drag, ...) as GitHub Copilot SDK custom tools. The SDK runs
the agentic loop: the model calls ``screenshot`` to see the screen, issues an
action tool, observes the returned screenshot, and repeats until the task is
complete.

``Scaler`` is unchanged — it resizes screenshots to a model-friendly resolution
and translates the model's coordinates back to the real screen.
"""

from __future__ import annotations

import base64
import io

import PIL.Image
from pydantic import BaseModel, Field

from copilot import define_tool
from copilot.tools import Tool, ToolBinaryResult, ToolResult


class Scaler:
    """Wrapper for a computer that performs resizing and coordinate translation."""

    def __init__(self, computer, dimensions: tuple[int, int] | None = None):
        self.computer = computer
        self.size = dimensions
        self.screen_width = -1
        self.screen_height = -1

    @property
    def dimensions(self):
        if not self.size:
            # Scale to fit within 1440x900 while preserving aspect ratio
            # 1440x900 recommended by OpenAI for computer use
            # https://developers.openai.com/api/docs/guides/tools-computer-use
            width, height = self.computer.dimensions
            max_width, max_height = 1440, 900
            scale = min(max_width / width, max_height / height)
            if scale >= 1:
                self.size = (width, height)
            else:
                self.size = (int(width * scale), int(height * scale))
        return self.size

    async def screenshot(self) -> str:
        # Take a screenshot from the actual computer
        screenshot = await self.computer.screenshot()
        screenshot = base64.b64decode(screenshot)
        buffer = io.BytesIO(screenshot)
        image = PIL.Image.open(buffer)
        # Scale the screenshot
        self.screen_width, self.screen_height = image.size
        width, height = self.dimensions
        ratio = min(width / self.screen_width, height / self.screen_height)
        new_width = int(self.screen_width * ratio)
        new_height = int(self.screen_height * ratio)
        new_size = (new_width, new_height)
        resized_image = image.resize(new_size, PIL.Image.Resampling.LANCZOS)
        image = PIL.Image.new("RGB", (width, height), (0, 0, 0))
        image.paste(resized_image, (0, 0))
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        buffer.seek(0)
        data = bytearray(buffer.getvalue())
        return base64.b64encode(data).decode("utf-8")

    async def click(self, x: int, y: int, button: str = "left") -> None:
        x, y = self._point_to_screen_coords(x, y)
        await self.computer.click(x, y, button=button)

    async def double_click(self, x: int, y: int) -> None:
        x, y = self._point_to_screen_coords(x, y)
        await self.computer.double_click(x, y)

    async def scroll(self, x: int, y: int, scroll_x: int, scroll_y: int) -> None:
        x, y = self._point_to_screen_coords(x, y)
        await self.computer.scroll(x, y, scroll_x, scroll_y)

    async def type(self, text: str) -> None:
        await self.computer.type(text)

    async def wait(self, ms: int = 1000) -> None:
        await self.computer.wait(ms)

    async def move(self, x: int, y: int) -> None:
        x, y = self._point_to_screen_coords(x, y)
        await self.computer.move(x, y)

    async def keypress(self, keys: list[str]) -> None:
        await self.computer.keypress(keys)

    async def drag(self, path: list[tuple[int, int]]) -> None:
        path = [self._point_to_screen_coords(*point) for point in path]
        await self.computer.drag(path)

    def _point_to_screen_coords(self, x, y):
        width, height = self.dimensions
        ratio = min(width / self.screen_width, height / self.screen_height)
        x = x / ratio
        y = y / ratio
        return int(x), int(y)


# ---------------------------------------------------------------------------
# Tool parameter schemas. These must live at module level so the SDK can resolve
# the handler annotations while ``from __future__ import annotations`` is active.
# ---------------------------------------------------------------------------


class ClickParams(BaseModel):
    x: int = Field(description="X coordinate within the screenshot, 0 at the left edge")
    y: int = Field(description="Y coordinate within the screenshot, 0 at the top edge")
    button: str = Field(default="left", description="Mouse button: 'left', 'right', or 'wheel'")


class PointParams(BaseModel):
    x: int = Field(description="X coordinate within the screenshot, 0 at the left edge")
    y: int = Field(description="Y coordinate within the screenshot, 0 at the top edge")


class ScrollParams(BaseModel):
    x: int = Field(description="X coordinate of the cursor before scrolling")
    y: int = Field(description="Y coordinate of the cursor before scrolling")
    scroll_x: int = Field(default=0, description="Horizontal scroll amount (positive = right)")
    scroll_y: int = Field(default=0, description="Vertical scroll amount (positive = down)")


class TypeParams(BaseModel):
    text: str = Field(description="The literal text to type at the current keyboard focus")


class KeypressParams(BaseModel):
    keys: list[str] = Field(
        description="Keys to press together, e.g. ['ctrl', 'c'] or ['enter']",
    )


class DragParams(BaseModel):
    path: list[list[int]] = Field(
        description="Ordered list of [x, y] points to drag through with the left button held",
    )


class WaitParams(BaseModel):
    ms: int = Field(default=1000, description="Milliseconds to wait before the next screenshot")


def build_computer_tools(computer: Scaler) -> list[Tool]:
    """Build the Copilot SDK tool set that lets the model drive ``computer``.

    Every action tool returns a fresh screenshot so the model can immediately
    observe the result, mirroring the screenshot-after-action loop of the
    original computer-use implementation.
    """

    async def ensure_initialized() -> None:
        # ``_point_to_screen_coords`` needs the real screen size, which is only
        # known after the first screenshot. Take one lazily if needed.
        if computer.screen_width <= 0:
            await computer.screenshot()

    async def result_with_screenshot(note: str) -> ToolResult:
        image = await computer.screenshot()
        return ToolResult(
            text_result_for_llm=note,
            binary_results_for_llm=[
                ToolBinaryResult(data=image, mime_type="image/png", type="image")
            ],
        )

    @define_tool(
        "screenshot",
        description="Capture the current screen. Call first, and after any action, to see the result.",
        skip_permission=True,
    )
    async def screenshot() -> ToolResult:
        await ensure_initialized()
        return await result_with_screenshot("Current screen.")

    @define_tool("click", description="Click the mouse at the given screenshot coordinates.")
    async def click(params: ClickParams) -> ToolResult:
        await ensure_initialized()
        await computer.click(params.x, params.y, button=params.button)
        return await result_with_screenshot(
            f"Clicked {params.button} button at ({params.x}, {params.y})."
        )

    @define_tool("double_click", description="Double-click the mouse at the given coordinates.")
    async def double_click(params: PointParams) -> ToolResult:
        await ensure_initialized()
        await computer.double_click(params.x, params.y)
        return await result_with_screenshot(f"Double-clicked at ({params.x}, {params.y}).")

    @define_tool("move", description="Move the mouse cursor to the given coordinates.")
    async def move(params: PointParams) -> ToolResult:
        await ensure_initialized()
        await computer.move(params.x, params.y)
        return await result_with_screenshot(f"Moved cursor to ({params.x}, {params.y}).")

    @define_tool("scroll", description="Scroll the wheel at the given coordinates.")
    async def scroll(params: ScrollParams) -> ToolResult:
        await ensure_initialized()
        await computer.scroll(params.x, params.y, params.scroll_x, params.scroll_y)
        return await result_with_screenshot(
            f"Scrolled by ({params.scroll_x}, {params.scroll_y}) at ({params.x}, {params.y})."
        )

    @define_tool("type", description="Type literal text at the current keyboard focus.")
    async def type_text(params: TypeParams) -> ToolResult:
        await ensure_initialized()
        await computer.type(params.text)
        return await result_with_screenshot(f"Typed: {params.text!r}.")

    @define_tool(
        "keypress",
        description="Press one or more keys together (e.g. ['ctrl', 'c'], ['enter'], ['win']).",
    )
    async def keypress(params: KeypressParams) -> ToolResult:
        await ensure_initialized()
        await computer.keypress(params.keys)
        return await result_with_screenshot(f"Pressed keys: {params.keys}.")

    @define_tool("drag", description="Press the left button and drag through a path of points.")
    async def drag(params: DragParams) -> ToolResult:
        await ensure_initialized()
        await computer.drag([tuple(point) for point in params.path])
        return await result_with_screenshot(f"Dragged through {len(params.path)} point(s).")

    @define_tool(
        "wait",
        description="Wait for the UI to settle (e.g. a page to load), then return a screenshot.",
        skip_permission=True,
    )
    async def wait(params: WaitParams) -> ToolResult:
        await computer.wait(params.ms)
        return await result_with_screenshot(f"Waited {params.ms} ms.")

    return [screenshot, click, double_click, move, scroll, type_text, keypress, drag, wait]
