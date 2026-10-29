import logging

import slicer

from . import ChatHistory
from . import FolderAccess
from . import PythonExecutor
from . import Settings

logger = logging.getLogger(__name__)

TOOLS = [
    {
        "name": "list_shared_folders",
        "description": (
            "List the folders the user has explicitly shared with you, and whether each is "
            "read-only or read-write. You can only read/write inside these folders - there is "
            "no other filesystem access. Call this first if you don't already know what's shared."
        ),
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "list_directory",
        "description": "List files and subdirectories under an absolute path inside one of the shared folders.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Absolute path inside a shared folder."},
                "recursive": {"type": "boolean", "description": "List subdirectories recursively. Default false."},
            },
            "required": ["path"],
        },
    },
    {
        "name": "read_text_file",
        "description": "Read a UTF-8 text file's contents. The path must be inside a shared folder. Large files are truncated.",
        "input_schema": {
            "type": "object",
            "properties": {"path": {"type": "string", "description": "Absolute path to the file."}},
            "required": ["path"],
        },
    },
    {
        "name": "write_text_file",
        "description": (
            "Create or overwrite a UTF-8 text file. The path must be inside a shared folder that "
            "is marked read-write. Parent directories are created automatically."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Absolute path to the file."},
                "content": {"type": "string", "description": "Full text content to write."},
                "mode": {"type": "string", "enum": ["overwrite", "append"], "description": "Default overwrite."},
            },
            "required": ["path", "content"],
        },
    },
    {
        "name": "run_python_in_slicer",
        "description": (
            "Execute Python code inside a real, running 3D Slicer application's Python environment "
            "(the same interpreter the Script Repository snippets target: slicer, vtk, qt, ctk are "
            "already importable). Use this instead of ever asking the user to copy-paste code. "
            "Prefer slicer.util.reloadScriptedModule('ModuleName') after editing a module rather than "
            "restarting Slicer. Set a dict on a variable named __execResult if you want structured "
            "data back in addition to stdout/stderr.\n"
            "Where this runs is fixed by the user in the Settings panel's Execution section, not by "
            "you: either their already-open Slicer window (affects their live scene/GUI immediately), "
            "or a separate, isolated companion Slicer process with no scene loaded.\n"
            "When running in the user's current Slicer window, getPythonConsoleOutput(historyIndex=0, "
            "offset=0, length=None) is also already available - it returns text recently printed to "
            "Slicer's own Python console, including from things other than your own code (e.g. the "
            "user manually interacting with the GUI, or other modules logging/erroring). historyIndex=0 "
            "(default) is everything since the user's last chat message, 1 is the window one chat "
            "message before that, 2 two messages before that, etc. (up to 10 kept); offset/length page "
            "through a long result, character-based."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "code": {"type": "string", "description": "Python source code to execute."},
            },
            "required": ["code"],
        },
    },
]

# Offered when the user lets Slicey look up earlier chats (Settings.getPastChatsAccess()).
PAST_CHAT_TOOLS = [
    {
        "name": "list_past_chats",
        "description": (
            "List the user's earlier Slicey chats (newest first, with each one's first message), or, "
            "with a query, find the lines of earlier chats that contain the query text (case-"
            "insensitive). Use it when the user refers to earlier work or conversations."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"query": {"type": "string", "description": "Text to search for. Omit to list all chats."}},
            "required": [],
        },
    },
    {
        "name": "read_past_chat",
        "description": (
            "Read the transcript (Markdown, including tool calls and results) of an earlier chat "
            "found with list_past_chats. Long transcripts are returned in parts: use offset to read on."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "The chat's name, e.g. Slicey-20260101-120000."},
                "offset": {"type": "integer", "description": "Character offset to start at. Default 0."},
                "length": {"type": "integer", "description": f"Characters to read, at most {ChatHistory.MAX_READ_CHARS}."},
            },
            "required": ["name"],
        },
    },
]


def activeTools():
    """The tools Slicey currently offers."""
    return TOOLS + (PAST_CHAT_TOOLS if Settings.getPastChatsAccess() else [])


def buildContextText():
    """The part of the system prompt that follows the user's settings (where code runs, the shared
    folders, the custom instructions). A local agent keeps the system prompt it started with, so
    SliceyLogic sends this again with the next message when it changes."""
    folders = FolderAccess.listSharedFolders()
    if folders:
        folderLines = "\n".join(
            "  - {}{}{}".format(
                f["path"],
                " (read-write)" if f["writable"] else " (read-only)",
                "" if f["exists"] else " [MISSING]",
            )
            for f in folders
        )
    else:
        folderLines = "  (none configured yet - ask the user to add one in the Settings panel if you need file access)"

    if Settings.getExecutionTarget() == "new_instance":
        executionNote = (
            "run_python_in_slicer currently runs in a separate, isolated companion Slicer "
            "process with no scene loaded - it will NOT affect the user's open scene/GUI."
        )
    else:
        executionNote = (
            "run_python_in_slicer currently runs in the user's already-open Slicer window - it "
            "affects their live scene/GUI immediately."
        )

    text = f"{executionNote}\n\nShared folders you currently have access to:\n{folderLines}"

    if Settings.getPastChatsAccess():
        text += ("\n\nThe user's earlier Slicey chats are available through list_past_chats and "
                 "read_past_chat; look them up when the user refers to earlier work.")

    customText = Settings.getCustomSystemPromptText().strip()
    if customText:
        text += f"\n\nAdditional instructions from the user:\n{customText}"

    return text


def buildSystemPrompt():
    return f"{Settings.SYSTEM_PROMPT_INSTRUCTIONS}\n\n{buildContextText()}"


def requiresMainThread(name, toolInput):
    """Returns True if dispatching this tool call must happen on Slicer's main thread (it
    touches Slicer/Qt/VTK/MRML objects). The only tool call that's safe to run on a background
    thread is run_python_in_slicer targeting a separate companion instance, since that only
    involves subprocess/socket/HTTP calls on our side. The target is the user's Settings panel
    choice (Settings.getExecutionTarget()), not something Claude requests per call.
    """
    if name == "run_python_in_slicer":
        return Settings.getExecutionTarget() != "new_instance"
    return True


class _MissingToolArgument(Exception):
    pass


def _require(toolInput, key):
    """Looks up a required tool argument, raising an actionable error (instead of a bare
    KeyError) if it's missing - most often because the response got cut off by the max_tokens
    limit partway through a large tool call (e.g. writing a big file), which can leave the
    JSON for that argument incomplete."""
    if key not in toolInput:
        raise _MissingToolArgument(
            f"Missing required '{key}' argument - the response was likely cut off by the "
            f"max_tokens limit while generating this tool call. Try again with a smaller "
            f"amount of content per call (e.g. write a short file first, then use "
            f"write_text_file with mode='append' one or more times to add the rest)."
        )
    return toolInput[key]


def dispatchTool(name, toolInput):
    """Executes a tool call and returns its result as a JSON-serializable dict."""
    try:
        if name == "list_shared_folders":
            return {"folders": FolderAccess.listSharedFolders()}
        if name == "list_directory":
            return FolderAccess.listDirectory(_require(toolInput, "path"), toolInput.get("recursive", False))
        if name == "read_text_file":
            return FolderAccess.readTextFile(_require(toolInput, "path"))
        if name == "write_text_file":
            return FolderAccess.writeTextFile(_require(toolInput, "path"), _require(toolInput, "content"), toolInput.get("mode", "overwrite"))
        if name in ("list_past_chats", "read_past_chat") and not Settings.getPastChatsAccess():
            return {"error": "The user has not allowed access to earlier chats."}
        if name == "list_past_chats":
            return ChatHistory.toolListPastChats(toolInput.get("query"))
        if name == "read_past_chat":
            return ChatHistory.toolReadPastChat(_require(toolInput, "name"), toolInput.get("offset", 0),
                                                toolInput.get("length", ChatHistory.MAX_READ_CHARS))
        if name == "run_python_in_slicer":
            code = _require(toolInput, "code")
            if Settings.getExecutionTarget() == "new_instance":
                return PythonExecutor.executeInNewInstance(code)
            return PythonExecutor.executeInProcess(code)
        return {"error": f"Unknown tool: {name}"}
    except _MissingToolArgument as e:
        return {"error": str(e)}
    except Exception as e:
        logger.exception("Slicey: tool execution failed")
        return {"error": str(e)}


def ensureAnthropicPackage():
    try:
        import anthropic
    except ImportError:
        slicer.util.pip_install("anthropic")
        import anthropic
    return anthropic


def createClient(apiKey):
    anthropic = ensureAnthropicPackage()
    return anthropic.Anthropic(api_key=apiKey)


def listModels(apiKey):
    """Validates the key by listing the models it can use (free, unlike a message), newest first.
    Raises if the key is not accepted. No Slicer access: runs on a worker thread, after
    ensureAnthropicPackage() on the main thread."""
    import anthropic

    client = anthropic.Anthropic(api_key=apiKey)
    return [{"id": m.id, "label": m.display_name or m.id, "description": m.id} for m in client.models.list(limit=100)]


def storeModels(models):
    """Offers `models` (from listModels) in the model selector. Main thread."""
    if models:
        Settings.setBackendModels("claude-api", models)
        if Settings.getModel() not in [m["id"] for m in models]:
            Settings.setModel(models[0]["id"])


def sendMessage(client, model, messages, systemPrompt, tools, onDelta=None, maxTokens=16000):
    """Blocking call to the Messages API with tools enabled (activeTools(), read on the main
    thread); onDelta(text) gets the reply text while it streams in. Returns the complete message.
    Safe to call from a background thread - performs no Slicer/Qt access itself.
    """
    with client.messages.stream(
        model=model,
        max_tokens=maxTokens,
        system=systemPrompt,
        tools=tools,
        messages=messages,
    ) as stream:
        for text in stream.text_stream:
            if onDelta:
                onDelta(text)
        return stream.get_final_message()
