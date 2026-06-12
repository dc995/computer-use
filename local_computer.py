import asyncio
import base64
import io

import mss
import pyautogui
from PIL import Image


class LocalComputer:
    """Take screenshots and perform mouse/keyboard actions on the local computer.

    Screenshots are captured with ``mss`` (multi-monitor aware) while input is
    driven with ``pyautogui``. The ``monitor`` argument selects what the agent
    sees and controls:

      * ``None`` or ``"all"`` -> the full virtual desktop spanning every monitor.
      * a 1-based integer     -> a single physical monitor (1 = the first monitor
        reported by the OS).

    Screenshot pixel ``(0, 0)`` maps to the captured region's top-left corner, and
    all input coordinates are offset by that origin so clicks land on the correct
    monitor even when a window opens on a secondary display.
    """

    def __init__(self, monitor=None):
        self.size = None
        self._monitor = self._normalize_monitor(monitor)
        self._origin = (0, 0)  # absolute screen coords of screenshot pixel (0, 0)

    @staticmethod
    def _normalize_monitor(monitor):
        if monitor is None:
            return None
        if isinstance(monitor, str):
            if monitor.strip().lower() in {"all", "virtual"}:
                return None
            return int(monitor)
        return int(monitor)

    def _region(self, sct):
        # sct.monitors[0] is the full virtual desktop; [1..] are individual monitors.
        monitors = sct.monitors
        if self._monitor is None:
            return monitors[0]
        if 1 <= self._monitor < len(monitors):
            return monitors[self._monitor]
        # Out-of-range index: fall back to the full virtual desktop.
        return monitors[0]

    @property
    def dimensions(self):
        if not self.size:
            with mss.mss() as sct:
                region = self._region(sct)
            self.size = (region["width"], region["height"])
            self._origin = (region["left"], region["top"])
        return self.size

    async def screenshot(self) -> str:
        with mss.mss() as sct:
            region = self._region(sct)
            self._origin = (region["left"], region["top"])
            raw = sct.grab(region)
        image = Image.frombytes("RGB", raw.size, raw.bgra, "raw", "BGRX")
        self.size = image.size
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        buffer.seek(0)
        data = bytearray(buffer.getvalue())
        return base64.b64encode(data).decode("utf-8")

    def _to_screen(self, x, y):
        ox, oy = self._origin
        return ox + x, oy + y

    async def click(self, x: int, y: int, button: str = "left") -> None:
        width, height = self.size
        if 0 <= x < width and 0 <= y < height:
            button = "middle" if button == "wheel" else button
            ax, ay = self._to_screen(x, y)
            pyautogui.moveTo(ax, ay, duration=0.1)
            pyautogui.click(ax, ay, button=button)

    async def double_click(self, x: int, y: int) -> None:
        width, height = self.size
        if 0 <= x < width and 0 <= y < height:
            ax, ay = self._to_screen(x, y)
            pyautogui.moveTo(ax, ay, duration=0.1)
            pyautogui.doubleClick(ax, ay)

    async def scroll(self, x: int, y: int, scroll_x: int, scroll_y: int) -> None:
        ax, ay = self._to_screen(x, y)
        pyautogui.moveTo(ax, ay, duration=0.5)
        pyautogui.scroll(-scroll_y)
        pyautogui.hscroll(scroll_x)

    async def type(self, text: str) -> None:
        pyautogui.write(text)

    async def wait(self, ms: int = 1000) -> None:
        await asyncio.sleep(ms / 1000)

    async def move(self, x: int, y: int) -> None:
        ax, ay = self._to_screen(x, y)
        pyautogui.moveTo(ax, ay, duration=0.1)

    async def keypress(self, keys: list[str]) -> None:
        keys = [key.lower() for key in keys]
        keymap = {
            "arrowdown": "down",
            "arrowleft": "left",
            "arrowright": "right",
            "arrowup": "up",
        }
        keys = [keymap.get(key, key) for key in keys]
        for key in keys:
            pyautogui.keyDown(key)
        for key in keys:
            pyautogui.keyUp(key)

    async def drag(self, path: list[tuple[int, int]]) -> None:
        path = [self._to_screen(*point) for point in path]
        if len(path) <= 1:
            pass
        elif len(path) == 2:
            pyautogui.moveTo(*path[0], duration=0.5)
            pyautogui.dragTo(*path[1], duration=1.0, button="left")
        else:
            pyautogui.moveTo(*path[0], duration=0.5)
            pyautogui.mouseDown(button="left")
            for point in path[1:]:
                pyautogui.dragTo(*point, duration=1.0, mouseDownUp=False)
            pyautogui.mouseUp(button="left")
