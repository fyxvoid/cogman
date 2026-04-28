"""Window and desktop management: list, focus, move, resize, workspaces."""
import shutil
import logging
from core.tool_registry import ToolRegistry
from core.system_controller import run_shell

log = logging.getLogger("cogman.tools.window")


def _has(cmd: str) -> bool:
    return shutil.which(cmd) is not None


def list_windows() -> str:
    if _has("wmctrl"):
        return run_shell("wmctrl -l")
    if _has("xdotool"):
        return run_shell("xdotool search --onlyvisible --name '' 2>/dev/null | xargs -I{} xdotool getwindowname {} 2>/dev/null | head -20")
    return "Install wmctrl: sudo apt install wmctrl"


def focus_window(title: str) -> str:
    if _has("wmctrl"):
        return run_shell(f"wmctrl -a '{title}'") or f"Focused window: {title}"
    if _has("xdotool"):
        return run_shell(f"xdotool search --name '{title}' | head -1 | xargs xdotool windowactivate 2>/dev/null")
    return "wmctrl or xdotool required"


def close_window(title: str) -> str:
    if _has("wmctrl"):
        return run_shell(f"wmctrl -c '{title}'") or f"Closed window: {title}"
    return "wmctrl required: sudo apt install wmctrl"


def maximize_window(title: str = "") -> str:
    if title and _has("wmctrl"):
        return run_shell(f"wmctrl -r '{title}' -b add,maximized_vert,maximized_horz")
    # Maximize active window
    if _has("xdotool"):
        return run_shell("xdotool getactivewindow windowsize --usehints 100% 100%")
    return "wmctrl or xdotool required"


def minimize_window(title: str = "") -> str:
    if _has("xdotool"):
        if title:
            return run_shell(f"xdotool search --name '{title}' | head -1 | xargs xdotool windowminimize 2>/dev/null")
        return run_shell("xdotool getactivewindow windowminimize")
    return "xdotool required: sudo apt install xdotool"


def move_window(title: str, x: int, y: int) -> str:
    if _has("wmctrl"):
        return run_shell(f"wmctrl -r '{title}' -e 0,{x},{y},-1,-1")
    return "wmctrl required"


def resize_window(title: str, width: int, height: int) -> str:
    if _has("wmctrl"):
        return run_shell(f"wmctrl -r '{title}' -e 0,-1,-1,{width},{height}")
    return "wmctrl required"


def list_workspaces() -> str:
    if _has("wmctrl"):
        return run_shell("wmctrl -d")
    return "wmctrl required"


def switch_workspace(number: int) -> str:
    if _has("wmctrl"):
        return run_shell(f"wmctrl -s {number - 1}")
    if _has("xdotool"):
        return run_shell(f"xdotool set_desktop {number - 1}")
    return "wmctrl or xdotool required"


def move_window_to_workspace(title: str, workspace: int) -> str:
    if _has("wmctrl"):
        return run_shell(f"wmctrl -r '{title}' -t {workspace - 1}")
    return "wmctrl required"


def get_active_window() -> str:
    if _has("xdotool"):
        wid = run_shell("xdotool getactivewindow 2>/dev/null").strip()
        if wid:
            name = run_shell(f"xdotool getwindowname {wid} 2>/dev/null").strip()
            pid = run_shell(f"xdotool getwindowpid {wid} 2>/dev/null").strip()
            return f"Active window: '{name}' (WID: {wid}, PID: {pid})"
    return "xdotool required"


def fullscreen_window(title: str = "") -> str:
    if _has("wmctrl"):
        target = f"'{title}'" if title else ":ACTIVE:"
        return run_shell(f"wmctrl -r {target} -b toggle,fullscreen")
    return "wmctrl required"


def always_on_top(title: str = "") -> str:
    if _has("wmctrl"):
        target = f"'{title}'" if title else ":ACTIVE:"
        return run_shell(f"wmctrl -r {target} -b toggle,above")
    return "wmctrl required"


def desktop_screenshot(output: str = "~/desktop.png") -> str:
    import os
    output = os.path.expanduser(output)
    if _has("scrot"):
        return run_shell(f"scrot '{output}'") or f"Desktop screenshot: {output}"
    if _has("import"):
        return run_shell(f"import -window root '{output}'") or f"Desktop screenshot: {output}"
    return "scrot or imagemagick required"


def set_wallpaper(path: str) -> str:
    import os
    path = os.path.expanduser(path)
    for cmd in [
        f"gsettings set org.gnome.desktop.background picture-uri 'file://{path}'",
        f"feh --bg-scale '{path}'",
        f"nitrogen --set-scaled '{path}'",
    ]:
        result = run_shell(cmd)
        if "[exit" not in result:
            return f"Wallpaper set to {path}"
    return "Could not set wallpaper — install feh or nitrogen"


def register_window_tools(registry: ToolRegistry):
    registry.register("list_windows", list_windows, "List all open windows", {})
    registry.register("focus_window", focus_window, "Focus (activate) a window by title",
        {"title": {"type": "string", "description": "Window title (partial match)", "required": True}})
    registry.register("close_window", close_window, "Close a window by title",
        {"title": {"type": "string", "description": "Window title to close", "required": True}})
    registry.register("maximize_window", maximize_window, "Maximize a window",
        {"title": {"type": "string", "description": "Window title (empty = active window)"}})
    registry.register("minimize_window", minimize_window, "Minimize a window",
        {"title": {"type": "string", "description": "Window title (empty = active window)"}})
    registry.register("move_window", move_window, "Move a window to specific coordinates",
        {
            "title": {"type": "string", "description": "Window title", "required": True},
            "x": {"type": "integer", "description": "X position", "required": True},
            "y": {"type": "integer", "description": "Y position", "required": True},
        })
    registry.register("resize_window", resize_window, "Resize a window",
        {
            "title": {"type": "string", "description": "Window title", "required": True},
            "width": {"type": "integer", "description": "Width in pixels", "required": True},
            "height": {"type": "integer", "description": "Height in pixels", "required": True},
        })
    registry.register("list_workspaces", list_workspaces, "List virtual desktops/workspaces", {})
    registry.register("switch_workspace", switch_workspace, "Switch to a workspace number",
        {"number": {"type": "integer", "description": "Workspace number (1-based)", "required": True}})
    registry.register("move_window_to_workspace", move_window_to_workspace, "Move a window to a workspace",
        {
            "title": {"type": "string", "description": "Window title", "required": True},
            "workspace": {"type": "integer", "description": "Target workspace number", "required": True},
        })
    registry.register("get_active_window", get_active_window, "Get info about the currently active window", {})
    registry.register("fullscreen_window", fullscreen_window, "Toggle fullscreen for a window",
        {"title": {"type": "string", "description": "Window title (empty = active)"}})
    registry.register("always_on_top", always_on_top, "Toggle always-on-top for a window",
        {"title": {"type": "string", "description": "Window title (empty = active)"}})
    registry.register("set_wallpaper", set_wallpaper, "Set desktop wallpaper",
        {"path": {"type": "string", "description": "Path to image file", "required": True}})
