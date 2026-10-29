"""Past chats in the chat log folder (Settings.getChatLogFolder()).

Each chat is saved as Slicey-YYYYMMDD-HHMMSS.md (readable transcript) and, since chats can be
continued, Slicey-YYYYMMDD-HHMMSS.json (the message list, to restore the conversation). Chats
saved before the .json files existed can still be read and continued from their transcript.
"""

import datetime
import json
import os
import re

from . import Settings

_NAME = re.compile(r"^Slicey-(\d{8}-\d{6})$")
MAX_READ_CHARS = 50_000
MAX_SEARCH_MATCHES = 50

# The chat Slicey is in now (its .md path), left out of what the agent finds; set by SliceyLogic.
currentChatPath = None


def chatName(path):
    return os.path.splitext(os.path.basename(path))[0]


def startedAt(path):
    """The time the chat started, from its file name, or None."""
    match = _NAME.match(chatName(path))
    return datetime.datetime.strptime(match.group(1), "%Y%m%d-%H%M%S") if match else None


def jsonPath(mdPath):
    return os.path.splitext(mdPath)[0] + ".json"


def listChats(includeCurrent=True):
    """The saved chats, newest first: {"name", "path", "startedAt" (datetime), "title" (the first
    user message, shortened), "continuable" (has its message list)} dicts."""
    folder = Settings.getChatLogFolder()
    try:
        names = os.listdir(folder)
    except OSError:
        return []
    chats = []
    for fileName in names:
        path = os.path.join(folder, fileName)
        if not fileName.endswith(".md") or startedAt(path) is None:
            continue
        if not includeCurrent and _isCurrent(path):
            continue
        chats.append({"name": chatName(path), "path": path, "startedAt": startedAt(path), "title": _title(path),
                      "continuable": os.path.isfile(jsonPath(path))})
    chats.sort(key=lambda c: c["startedAt"], reverse=True)
    return chats


def _isCurrent(path):
    return bool(currentChatPath) and os.path.normcase(os.path.abspath(path)) == \
        os.path.normcase(os.path.abspath(currentChatPath))


def _title(path, maxLength=100):
    """The first user message of the chat transcript."""
    try:
        with open(path, encoding="utf-8") as f:
            text = f.read(20_000)
    except OSError:
        return ""
    match = re.search(r"^## You\n\n?(.+?)(?:\n## |\n### |\Z)", text, re.MULTILINE | re.DOTALL)
    title = " ".join(match.group(1).split()) if match else ""
    return title if len(title) <= maxLength else title[:maxLength - 3] + "..."


def _findChat(name):
    """The .md path of the saved chat `name` (with or without .md), or None. Only chats in the
    chat log folder can be found."""
    name = chatName(str(name).strip())
    if not _NAME.match(name):
        return None
    path = os.path.join(Settings.getChatLogFolder(), name + ".md")
    return path if os.path.isfile(path) else None


def readTranscript(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def loadMessages(path):
    """The message list of a chat, or None if only its transcript was saved."""
    try:
        with open(jsonPath(path), encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return None
    messages = data.get("messages") if isinstance(data, dict) else None
    return messages if isinstance(messages, list) else None


def saveMessages(path, messages, preamble=""):
    """Saves the message list of the chat whose transcript is at `path`; `preamble` is the
    transcript of a continued chat that has no message list."""
    with open(jsonPath(path), "w", encoding="utf-8") as f:
        json.dump({"version": 1, "preamble": preamble, "messages": messages}, f)


def loadPreamble(path):
    try:
        with open(jsonPath(path), encoding="utf-8") as f:
            return json.load(f).get("preamble", "")
    except (OSError, ValueError, AttributeError):
        return ""


# Agent tools

def toolListPastChats(query=None):
    chats = listChats(includeCurrent=False)
    if not query:
        return {"chats": [{"name": c["name"], "started": c["startedAt"].isoformat(sep=" "), "firstMessage": c["title"]}
                          for c in chats]}
    needle = query.lower()
    matches = []
    for c in chats:
        try:
            lines = readTranscript(c["path"]).splitlines()
        except OSError:
            continue
        for number, line in enumerate(lines, 1):
            if needle in line.lower():
                matches.append({"name": c["name"], "line": number, "text": line.strip()[:300]})
                if len(matches) >= MAX_SEARCH_MATCHES:
                    return {"matches": matches, "truncated": True}
    return {"matches": matches, "truncated": False}


def toolReadPastChat(name, offset=0, length=MAX_READ_CHARS):
    path = _findChat(name)
    if path is None:
        return {"error": f"No saved chat named {name!r}; list_past_chats lists them."}
    try:
        text = readTranscript(path)
    except OSError as e:
        return {"error": f"Could not read the chat: {e}"}
    offset = max(0, int(offset or 0))
    length = max(1, min(int(length or MAX_READ_CHARS), MAX_READ_CHARS))
    return {"name": chatName(path), "totalChars": len(text), "offset": offset,
            "content": text[offset:offset + length], "more": offset + length < len(text)}
