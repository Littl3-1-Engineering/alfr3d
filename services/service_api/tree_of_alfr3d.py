"""Project tree visualization blueprint for ALFR3D."""

import os
import time
import fnmatch
from flask import Blueprint, jsonify, current_app

PROJECT_TREE_BLUEPRINT = Blueprint("project_tree", __name__)

EXCLUDED_PATTERNS = [
    "__pycache__",
    ".env",
    "*.pyc",
    ".pytest_cache",
    ".venv",
    "node_modules",
    "dist",
    "backup",
    ".git",
    ".pytest_cache",
    "*.pyc",
    "*.pyo",
    ".DS_Store",
    "*.log",
    "mysql_data",
    "alfr3d.wiki",
    "k8s",
]

SCAN_ROOT = "/project"

_cached_tree = None
_last_mtime = None


def should_exclude(name, path):
    """Check if file/directory should be excluded based on patterns."""
    for pattern in EXCLUDED_PATTERNS:
        if fnmatch.fnmatch(name, pattern):
            return True
    if ".git" in path.split(os.sep):
        return True
    return False


def scan_directory(path, root_name=None):
    """
    Recursively scan directory and return tree structure.

    Args:
        path: Directory path to scan
        root_name: Optional root name for the tree

    Returns:
        dict: Tree structure with 'name' and 'children' (for dirs) or 'size' (for files)
    """
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


def get_project_tree():
    """Get cached project tree, regenerating if needed."""
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


@PROJECT_TREE_BLUEPRINT.route("/api/project-tree")
def get_project_tree_endpoint():
    """API endpoint to return project tree as JSON."""
    tree = get_project_tree()
    return jsonify(tree)


def start_file_watcher(socketio, interval=10):
    """
    Background thread to watch for file changes and emit updates.

    Args:
        socketio: SocketIO instance to emit events
        interval: Polling interval in seconds
    """
    global _last_mtime
    _last_mtime = os.path.getmtime(SCAN_ROOT)

    while True:
        time.sleep(interval)
        try:
            current_mtime = os.path.getmtime(SCAN_ROOT)
            if current_mtime > _last_mtime:
                _last_mtime = current_mtime
                tree = get_project_tree()
                socketio.emit("project_tree", tree)
                current_app.logger.info("Project tree updated and broadcasted")
        except OSError as e:
            current_app.logger.warning(f"Error checking file changes: {e}")
