import logging

import slicer

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
            "target='current' runs in the user's already-open Slicer window and affects their live "
            "scene/GUI immediately.\n"
            "target='new_instance' launches (or reuses) a separate, isolated Slicer process with no "
            "scene loaded - safer for testing a module load/reload without touching the user's open "
            "scene, at the cost of being slower the first time it starts up."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "code": {"type": "string", "description": "Python source code to execute."},
                "target": {"type": "string", "enum": ["current", "new_instance"], "description": "Default 'current'."},
            },
            "required": ["code"],
        },
    },
]


def buildSystemPrompt():
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
        folderLines = "  (none configured yet - ask the user to add one in the Shared Folders panel if you need file access)"

    return (
        "You are Slicey, an AI assistant embedded inside the user's local 3D Slicer application, "
        "helping them use, develop, and modify 3D Slicer extensions and modules.\n\n"
        "Shared folders you currently have access to:\n"
        f"{folderLines}\n\n"
        "You can only read/write inside the folders listed above (and only the read-write ones for "
        "writes); any other path will be rejected. Use run_python_in_slicer to act on the running "
        "Slicer application itself - never ask the user to manually paste code into Slicer's Python "
        "console. After changing a scripted module's .py file, reload it with "
        "slicer.util.reloadScriptedModule('ModuleName') instead of restarting Slicer."
    )


def requiresMainThread(name, toolInput):
    """Returns True if dispatching this tool call must happen on Slicer's main thread (it
    touches Slicer/Qt/VTK/MRML objects). The only tool call that's safe to run on a background
    thread is run_python_in_slicer targeting a separate companion instance, since that only
    involves subprocess/socket/HTTP calls on our side.
    """
    if name == "run_python_in_slicer":
        return toolInput.get("target", "current") != "new_instance"
    return True


def dispatchTool(name, toolInput):
    """Executes a tool call and returns its result as a JSON-serializable dict."""
    try:
        if name == "list_shared_folders":
            return {"folders": FolderAccess.listSharedFolders()}
        if name == "list_directory":
            return FolderAccess.listDirectory(toolInput["path"], toolInput.get("recursive", False))
        if name == "read_text_file":
            return FolderAccess.readTextFile(toolInput["path"])
        if name == "write_text_file":
            return FolderAccess.writeTextFile(toolInput["path"], toolInput["content"], toolInput.get("mode", "overwrite"))
        if name == "run_python_in_slicer":
            target = toolInput.get("target", "current")
            if target == "new_instance":
                return PythonExecutor.executeInNewInstance(toolInput["code"])
            return PythonExecutor.executeInProcess(toolInput["code"])
        return {"error": f"Unknown tool: {name}"}
    except Exception as e:
        logger.exception("Slicey: tool execution failed")
        return {"error": str(e)}


def _ensureAnthropicPackage():
    try:
        import anthropic
    except ImportError:
        slicer.util.pip_install("anthropic")
        import anthropic
    return anthropic


def createClient(apiKey):
    anthropic = _ensureAnthropicPackage()
    return anthropic.Anthropic(api_key=apiKey)


def testApiKey(apiKey):
    """Makes a minimal request to validate the key. Returns (ok: bool, message: str)."""
    try:
        client = createClient(apiKey)
        client.messages.create(
            model=Settings.VALIDATION_MODEL,
            max_tokens=1,
            messages=[{"role": "user", "content": "Hi"}],
        )
        return True, "Connected."
    except Exception as e:
        return False, str(e)


def sendMessage(client, model, messages, systemPrompt, maxTokens=4096):
    """Blocking call to the Messages API with tools enabled. Safe to call from a background
    thread - performs no Slicer/Qt access itself.
    """
    return client.messages.create(
        model=model,
        max_tokens=maxTokens,
        system=systemPrompt,
        tools=TOOLS,
        messages=messages,
    )
