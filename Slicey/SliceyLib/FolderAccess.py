import os
from pathlib import Path

from . import Settings

MAX_READ_BYTES = 200_000


def _resolveRoot(folderPath):
    return Path(folderPath).expanduser().resolve()


def _findContainingRoot(path):
    """Returns (folderSettingsDict, resolvedPath) if path resolves inside one of the
    configured shared folders, else (None, resolvedPath). Resolves symlinks so a link
    inside a shared folder cannot be used to escape it.
    """
    resolved = Path(path).expanduser().resolve()
    for folder in Settings.getSharedFolders():
        root = _resolveRoot(folder["path"])
        try:
            if resolved == root or resolved.is_relative_to(root):
                return folder, resolved
        except (OSError, ValueError):
            continue
    return None, resolved


def listSharedFolders():
    result = []
    for folder in Settings.getSharedFolders():
        root = _resolveRoot(folder["path"])
        result.append({
            "path": str(root),
            "writable": bool(folder.get("writable", False)),
            "exists": root.is_dir(),
        })
    return result


def addSharedFolder(path, writable=False):
    folders = Settings.getSharedFolders()
    resolved = str(_resolveRoot(path))
    for folder in folders:
        if str(_resolveRoot(folder["path"])) == resolved:
            folder["path"] = resolved
            folder["writable"] = writable
            Settings.setSharedFolders(folders)
            return
    folders.append({"path": resolved, "writable": writable})
    Settings.setSharedFolders(folders)


def removeSharedFolder(path):
    resolved = str(_resolveRoot(path))
    folders = [f for f in Settings.getSharedFolders() if str(_resolveRoot(f["path"])) != resolved]
    Settings.setSharedFolders(folders)


def listDirectory(path, recursive=False):
    folder, resolved = _findContainingRoot(path)
    if folder is None:
        return {"error": f"Path is not inside any shared folder: {path}"}
    if not resolved.exists():
        return {"error": f"Path does not exist: {resolved}"}
    if not resolved.is_dir():
        return {"error": f"Path is not a directory: {resolved}"}

    entries = []
    if recursive:
        for dirpath, dirnames, filenames in os.walk(resolved):
            relDir = os.path.relpath(dirpath, resolved)
            for name in sorted(dirnames):
                relPath = name if relDir == "." else os.path.join(relDir, name)
                entries.append({"path": relPath.replace("\\", "/"), "type": "directory"})
            for name in sorted(filenames):
                relPath = name if relDir == "." else os.path.join(relDir, name)
                fullPath = os.path.join(dirpath, name)
                entries.append({"path": relPath.replace("\\", "/"), "type": "file", "size": os.path.getsize(fullPath)})
    else:
        for entry in sorted(resolved.iterdir(), key=lambda p: p.name):
            entries.append({
                "path": entry.name,
                "type": "directory" if entry.is_dir() else "file",
                "size": None if entry.is_dir() else entry.stat().st_size,
            })
    return {"root": str(resolved), "entries": entries}


def readTextFile(path):
    folder, resolved = _findContainingRoot(path)
    if folder is None:
        return {"error": f"Path is not inside any shared folder: {path}"}
    if not resolved.is_file():
        return {"error": f"File does not exist: {resolved}"}
    try:
        data = resolved.read_bytes()
    except OSError as e:
        return {"error": f"Could not read file: {e}"}
    truncated = False
    if len(data) > MAX_READ_BYTES:
        data = data[:MAX_READ_BYTES]
        truncated = True
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        return {"error": f"File does not appear to be a UTF-8 text file: {resolved}"}
    return {"path": str(resolved), "content": text, "truncated": truncated}


def writeTextFile(path, content, mode="overwrite"):
    folder, resolved = _findContainingRoot(path)
    if folder is None:
        return {"error": f"Path is not inside any shared folder: {path}"}
    if not folder.get("writable", False):
        return {"error": f"Shared folder is read-only, cannot write: {folder['path']}"}
    try:
        resolved.parent.mkdir(parents=True, exist_ok=True)
        writeMode = "a" if mode == "append" else "w"
        with open(resolved, writeMode, encoding="utf-8", newline="") as f:
            f.write(content)
    except OSError as e:
        return {"error": f"Could not write file: {e}"}
    return {"path": str(resolved), "bytesWritten": len(content.encode("utf-8")), "mode": mode}
