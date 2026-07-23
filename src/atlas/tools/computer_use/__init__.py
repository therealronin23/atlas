"""Computer-use tools for Gate F."""

from atlas.tools.computer_use.desktop_action import (
    MUTATING_DESKTOP_ACTIONS,
    DesktopAction,
    DesktopActionKind,
    normalize_desktop_approval,
)
from atlas.tools.computer_use.desktop_planner import DesktopPlanner
from atlas.tools.computer_use.desktop_tool import READ_ONLY_DESKTOP_TOOLS, DesktopTool

__all__ = [
    "DesktopAction",
    "DesktopActionKind",
    "DesktopPlanner",
    "DesktopTool",
    "MUTATING_DESKTOP_ACTIONS",
    "READ_ONLY_DESKTOP_TOOLS",
    "normalize_desktop_approval",
]
