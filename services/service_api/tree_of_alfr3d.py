"""Project tree visualization router for ALFR3D using FastAPI."""

import os
import fnmatch
import asyncio
from typing import Optional, Any
from fastapi import APIRouter

EXCLUDED_PATTERNS = [
    "__pycache__",
    ".env",
    "*.pyc",
    ".pyo",
    ".DS_Store",
    "*.log",
    "mysql_data",
    "alfr3d.wiki",
    "k8s",
    ".git",
    ".pytest_cache",
    ".venv",
    "node_modules",
    "dist",
    "backup",
    ".opencode",
    ".osgrep",
    ".ruff_cache",
]

SCAN_ROOT = "/project"

_cached_tree = None
_last_mtime: Optional[float] = None
_manager = None

project_tree_router = APIRouter(prefix="/api", tags=["project-tree"])


def set_manager(manager: Any):
    global _manager
    _manager = manager


def should_exclude(name: str, path: str) -> bool:
    if name.startswith("."):
        return True
    for pattern in EXCLUDED_PATTERNS:
        if fnmatch.fnmatch(name, pattern):
            return True
    if ".git" in path.split(os.sep):
        return True
    return False


def scan_directory(path: str, root_name: Optional[str] = None) -> dict:
    if root_name is None:
        root_name = os.path.basename(path)

    node = {"name": root_name, "path": path}

    if not os.path.isdir(path):
        try:
            node["size"] = os.path.getsize(path)
        except OSError:
            node["size"] = 0
        return node

    try:
        entries = os.listdir(path)
    except PermissionError:
        node["children"] = []
        return node

    children = []
    for entry in entries:
        if should_exclude(entry, os.path.join(path, entry)):
            continue

        entry_path = os.path.join(path, entry)
        child_node = scan_directory(entry_path, entry)
        children.append(child_node)

    children.sort(key=lambda x: (not x.get("children"), x["name"].lower()))
    node["children"] = children

    return node


def get_project_tree() -> dict:
    global _cached_tree, _last_mtime

    if _cached_tree is None:
        _cached_tree = scan_directory(SCAN_ROOT)
        try:
            _last_mtime = os.path.getmtime(SCAN_ROOT)
        except OSError:
            pass

    try:
        current_mtime = os.path.getmtime(SCAN_ROOT)
        if _last_mtime is None or current_mtime > _last_mtime:
            _cached_tree = scan_directory(SCAN_ROOT)
            _last_mtime = current_mtime
    except OSError:
        _cached_tree = scan_directory(SCAN_ROOT)

    return _cached_tree


@project_tree_router.get("/project-tree")
async def get_project_tree_endpoint():
    """Get the current project tree structure."""
    tree = get_project_tree()
    return tree


async def start_file_watcher_task(interval: int = 10):
    """Background task to watch for file changes and broadcast updates."""
    global _last_mtime
    try:
        _last_mtime = os.path.getmtime(SCAN_ROOT)
    except OSError:
        return

    while True:
        await asyncio.sleep(interval)
        try:
            current_mtime = os.path.getmtime(SCAN_ROOT)
            if current_mtime > _last_mtime:
                _last_mtime = current_mtime
                tree = get_project_tree()
                if _manager:
                    await _manager.broadcast("project_tree", tree)
        except OSError:
            pass
