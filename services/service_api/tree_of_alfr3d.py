"""Project tree visualization router for ALFR3D using FastAPI."""

import os
import fnmatch
import asyncio
from typing import Optional, Any
from fastapi import APIRouter, Query

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


def count_children(path: str) -> int:
    """Count immediate non-excluded children of a directory."""
    try:
        entries = os.listdir(path)
    except (PermissionError, OSError):
        return 0
    return sum(1 for e in entries if not should_exclude(e, os.path.join(path, e)))


def scan_directory(
    path: str, root_name: Optional[str] = None, max_depth: Optional[int] = None, _depth: int = 0
) -> dict:
    if root_name is None:
        root_name = os.path.basename(path)

    node = {"name": root_name, "path": path}

    if not os.path.isdir(path):
        try:
            node["size"] = os.path.getsize(path)
        except OSError:
            node["size"] = 0
        return node

    if max_depth is not None and _depth >= max_depth:
        node["truncated"] = True
        node["children_count"] = count_children(path)
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
        child_node = scan_directory(entry_path, entry, max_depth=max_depth, _depth=_depth + 1)
        children.append(child_node)

    children.sort(key=lambda x: (not x.get("children"), x["name"].lower()))
    node["children"] = children

    return node


def get_project_tree(max_depth: Optional[int] = None) -> dict:
    global _cached_tree, _last_mtime

    if max_depth is None:
        max_depth = 3

    # Use cache for default depth only
    if max_depth == 3:
        if _cached_tree is None:
            _cached_tree = scan_directory(SCAN_ROOT, max_depth=max_depth)
            try:
                _last_mtime = os.path.getmtime(SCAN_ROOT)
            except OSError:
                pass

        try:
            current_mtime = os.path.getmtime(SCAN_ROOT)
            if _last_mtime is None or current_mtime > _last_mtime:
                _cached_tree = scan_directory(SCAN_ROOT, max_depth=max_depth)
                _last_mtime = current_mtime
        except OSError:
            _cached_tree = scan_directory(SCAN_ROOT, max_depth=max_depth)

        return _cached_tree

    return scan_directory(SCAN_ROOT, max_depth=max_depth)


@project_tree_router.get("/project-tree")
async def get_project_tree_endpoint(max_depth: Optional[int] = Query(None)):
    """Get the current project tree structure. Optional max_depth limits recursion."""
    tree = await asyncio.get_event_loop().run_in_executor(None, get_project_tree, max_depth)
    return tree


@project_tree_router.get("/project-tree/expand")
async def expand_node_endpoint(
    path: str = Query(..., description="Absolute path of the folder to expand")
):
    """Lazy-load: expand a truncated node by returning its immediate children."""
    if not path.startswith(SCAN_ROOT):
        return {"error": "Path must be under /project"}
    if not os.path.isdir(path):
        return {"error": "Path is not a directory"}
    subtree = await asyncio.get_event_loop().run_in_executor(
        None, scan_directory, path, os.path.basename(path), 2, 0
    )
    return subtree


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
                tree = await asyncio.get_event_loop().run_in_executor(None, get_project_tree)
                if _manager:
                    await _manager.broadcast("project_tree", tree)
        except OSError:
            pass
