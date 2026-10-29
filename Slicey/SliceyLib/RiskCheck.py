"""Decides which actions need the user's approval in the "auto" approval mode.

assess(name, toolInput) returns None for an action that may run without asking, or the reason
to ask. Python code is analyzed without running it: it may run only if none of the risky
patterns below appear in it. This saves approvals for everyday code (reading and changing the
scene, computing, displaying); it is not a sandbox. Code the check cannot see through (computed
attribute names, eval, aliased modules, ...) counts as risky.
"""

import ast
import re
from pathlib import Path

# Importing any of these (or a submodule) is risky: processes, network, native code, code
# loading, deserialization, archives, credentials, Slicey's own settings.
RISKY_MODULES = {
    "subprocess": "starts other programs",
    "multiprocessing": "starts other processes",
    "concurrent": "starts other processes",
    "signal": "sends signals to processes",
    "shutil": "copies, moves or deletes files",
    "zipfile": "reads or writes archives",
    "tarfile": "reads or writes archives",
    "socket": "uses the network",
    "ssl": "uses the network",
    "urllib": "uses the network",
    "urllib3": "uses the network",
    "http": "uses the network",
    "requests": "uses the network",
    "httpx": "uses the network",
    "aiohttp": "uses the network",
    "ftplib": "uses the network",
    "smtplib": "uses the network",
    "webbrowser": "opens a web browser",
    "ctypes": "calls native code",
    "cffi": "calls native code",
    "_winapi": "calls the Windows API",
    "winreg": "uses the Windows registry",
    "msvcrt": "calls the C runtime",
    "importlib": "loads code dynamically",
    "runpy": "runs other scripts",
    "builtins": "changes Python's built-in functions",
    "pickle": "loads pickled objects, which can run code",
    "marshal": "loads compiled code",
    "shelve": "loads pickled objects, which can run code",
    "pip": "installs Python packages",
    "ensurepip": "installs Python packages",
    "keyring": "reads stored passwords and API keys",
    "SliceyLib": "changes Slicey itself",
}

# The os module is safe only for these (path handling, listing, environment reads).
OS_SAFE_NAMES = {
    "path", "getcwd", "listdir", "scandir", "walk", "stat", "fspath", "fsdecode", "fsencode",
    "sep", "altsep", "linesep", "pathsep", "curdir", "pardir", "extsep", "devnull", "name",
    "environ", "getenv", "cpu_count", "getpid", "getlogin",
}
OS_ENVIRON_SAFE_METHODS = {"get", "keys", "values", "items", "copy"}

# Built-in functions that can run or reach arbitrary code.
RISKY_BUILTINS = {
    "eval": "runs code from a string",
    "exec": "runs code from a string",
    "compile": "compiles code from a string",
    "__import__": "imports a module dynamically",
    "globals": "accesses the interpreter's globals",
    "breakpoint": "starts the debugger",
    "input": "waits for console input",
}
BUILTINS_TAKING_ATTRIBUTE_NAMES = {"getattr", "setattr", "delattr", "hasattr"}

# Method or function names that are risky whatever object they are called on.
RISKY_ATTRIBUTES = {
    # Files
    "write_text": "writes a file",
    "write_bytes": "writes a file",
    "unlink": "deletes a file",
    "rmdir": "deletes a folder",
    "rmtree": "deletes a folder",
    "removeRecursively": "deletes a folder",
    "touch": "creates a file",
    "chmod": "changes file permissions",
    "symlink_to": "creates a link",
    "hardlink_to": "creates a link",
    "Write": "writes a file",
    "WriteImage": "writes a file",
    "WriteTransform": "writes a file",
    "save": "writes a file",
    "savez": "writes a file",
    "savez_compressed": "writes a file",
    "savetxt": "writes a file",
    "savefig": "writes a file",
    "tofile": "writes a file",
    "to_csv": "writes a file",
    "to_excel": "writes a file",
    "to_parquet": "writes a file",
    "saveNode": "writes a file",
    "saveScene": "writes a file",
    "exportNode": "writes a file",
    # Slicer and its Python environment
    "quit": "closes Slicer",
    "exit": "closes Slicer",
    "_exit": "closes Slicer",
    "restart": "restarts Slicer",
    "pip_install": "installs Python packages",
    "pip_uninstall": "uninstalls Python packages",
    "pip_ensure": "installs Python packages",
    "downloadFile": "downloads from the internet",
    "downloadFromURL": "downloads from the internet",
    "executeString": "runs code from a string",
    "executeFile": "runs a script file",
    "userSettings": "uses Slicer's settings",
    "revisionUserSettings": "uses Slicer's settings",
    "settings": "uses Slicer's settings",
    "QSettings": "uses Slicer's settings",
    "QProcess": "starts other programs",
    "QNetworkAccessManager": "uses the network",
    "QDesktopServices": "opens files or links in other programs",
    "slicey": "changes Slicey itself",
    # Introspection that reaches around the checks above
    "__globals__": "accesses a function's globals",
    "__builtins__": "accesses Python's built-in functions",
    "__subclasses__": "accesses the interpreter's internals",
    "__bases__": "accesses the interpreter's internals",
    "__mro__": "accesses the interpreter's internals",
    "__code__": "accesses compiled code",
    "__dict__": "accesses an object's internals",
    "__loader__": "accesses the interpreter's internals",
    "__import__": "imports a module dynamically",
}
# Calls whose dotted name ends with one of these are risky (the method name alone is too common).
RISKY_DOTTED_SUFFIXES = {
    "mrmlScene.Clear": "clears the scene",
}
# open(file, mode) and Path.open(mode) write when the mode has one of these.
_WRITE_MODE = re.compile(r"[wax+]")


def assess(name, toolInput):
    """None if this tool call may run without the user's approval, else the reason to ask."""
    if name == "run_python_in_slicer":
        return assessPython(toolInput.get("code", ""))
    if name == "write_text_file":
        return _assessWrite(toolInput.get("path", ""))
    return None


def _assessWrite(path):
    try:
        exists = Path(path).expanduser().resolve().exists()
    except (OSError, ValueError):
        return "The file path could not be checked."
    if exists:
        return "The file already exists and would be changed."
    return None


def assessPython(code):
    """None if the code shows none of the risky patterns, else the first reason found."""
    try:
        tree = ast.parse(code)
    except (SyntaxError, ValueError) as e:
        return f"The code could not be analyzed ({type(e).__name__})."
    reasons = _PythonChecker().check(tree)
    if not reasons:
        return None
    return "The code " + "; ".join(reasons[:3]) + "."


class _PythonChecker(ast.NodeVisitor):
    def check(self, tree):
        self.reasons = []
        self.osNames = set()  # names bound to the os module
        self.parents = {}
        for node in ast.walk(tree):
            for child in ast.iter_child_nodes(node):
                self.parents[child] = node
        self.visit(tree)
        return self.reasons

    def _flag(self, reason):
        if reason and reason not in self.reasons:
            self.reasons.append(reason)

    # Imports

    def visit_Import(self, node):
        for alias in node.names:
            self._checkModule(alias.name)
            if alias.name == "os":
                self.osNames.add(alias.asname or "os")
            elif alias.name.startswith("os.") and alias.asname is None:
                self.osNames.add("os")
        self.generic_visit(node)

    def visit_ImportFrom(self, node):
        module = node.module or ""
        if node.level:
            self._flag("uses a relative import")
        self._checkModule(module)
        for alias in node.names:
            self._checkModule(f"{module}.{alias.name}")
            if alias.name == "*":
                self._flag(f"imports everything from {module}")
            elif module == "os" and alias.name not in OS_SAFE_NAMES:
                self._flag(f"uses os.{alias.name}")
            elif alias.name in RISKY_ATTRIBUTES:
                self._flag(RISKY_ATTRIBUTES[alias.name])
            elif alias.name in RISKY_BUILTINS and module == "builtins":
                self._flag(RISKY_BUILTINS[alias.name])
        self.generic_visit(node)

    def _checkModule(self, dotted):
        parts = dotted.split(".")
        for i in range(1, len(parts) + 1):
            reason = RISKY_MODULES.get(".".join(parts[:i]))
            if reason:
                self._flag(reason)

    # Names, attributes, calls

    def visit_Name(self, node):
        if node.id in RISKY_BUILTINS:
            self._flag(RISKY_BUILTINS[node.id])
        elif node.id == "__builtins__":
            self._flag(RISKY_ATTRIBUTES["__builtins__"])
        elif node.id in self.osNames and not isinstance(self.parents.get(node), ast.Attribute):
            self._flag("uses the os module indirectly")
        elif node.id == "open" and not self._isCallee(node):
            self._flag("uses open() indirectly")
        elif node.id in BUILTINS_TAKING_ATTRIBUTE_NAMES and not self._isCallee(node):
            self._flag(f"uses {node.id}() indirectly")

    def visit_Attribute(self, node):
        self._checkAttributeName(node.value, node.attr)
        self.generic_visit(node)

    def _checkAttributeName(self, valueNode, attr):
        if attr in RISKY_ATTRIBUTES:
            self._flag(RISKY_ATTRIBUTES[attr])
        if isinstance(valueNode, ast.Name) and valueNode.id in self.osNames and attr not in OS_SAFE_NAMES:
            self._flag(f"uses os.{attr}")

    def visit_Call(self, node):
        func = node.func
        if isinstance(func, ast.Name) and func.id == "open":
            self._checkOpenMode(node, modeIndex=1)
        elif isinstance(func, ast.Attribute) and func.attr == "open":
            self._checkOpenMode(node, modeIndex=None)
        elif isinstance(func, ast.Name) and func.id in BUILTINS_TAKING_ATTRIBUTE_NAMES:
            if len(node.args) < 2 or not _isStringConstant(node.args[1]):
                self._flag(f"uses {func.id}() with a computed attribute name")
            else:
                self._checkAttributeName(node.args[0], node.args[1].value)
        if isinstance(func, ast.Attribute):
            dotted = _dottedName(func)
            for suffix, reason in RISKY_DOTTED_SUFFIXES.items():
                if dotted == suffix or dotted.endswith("." + suffix):
                    self._flag(reason)
            if _isOsEnviron(func.value, self.osNames) and func.attr not in OS_ENVIRON_SAFE_METHODS:
                self._flag("changes environment variables")
        self.generic_visit(node)

    def _checkOpenMode(self, node, modeIndex):
        """open(file, mode=...) writes if its mode says so. For a method named open (Path.open,
        codecs.open, io.open, ...) any string argument that looks like a write mode counts."""
        modes = [kw.value for kw in node.keywords if kw.arg == "mode"]
        if modeIndex is not None:
            if len(node.args) > modeIndex:
                modes.append(node.args[modeIndex])
        else:
            modes += [a for a in node.args if _isStringConstant(a) and re.fullmatch(r"[rwxabt+U]{1,4}", a.value)]
        for mode in modes:
            if not _isStringConstant(mode):
                self._flag("opens a file with a computed mode")
            elif _WRITE_MODE.search(mode.value):
                self._flag("writes a file")
        if any(kw.arg is None for kw in node.keywords):
            self._flag("opens a file with computed arguments")

    def visit_Subscript(self, node):
        if isinstance(node.ctx, (ast.Store, ast.Del)) and _isOsEnviron(node.value, self.osNames):
            self._flag("changes environment variables")
        self.generic_visit(node)

    def _isCallee(self, node):
        parent = self.parents.get(node)
        return isinstance(parent, ast.Call) and parent.func is node


def _isStringConstant(node):
    return isinstance(node, ast.Constant) and isinstance(node.value, str)


def _isOsEnviron(node, osNames):
    return (isinstance(node, ast.Attribute) and node.attr == "environ"
            and isinstance(node.value, ast.Name) and node.value.id in osNames)


def _dottedName(node):
    parts = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
    elif isinstance(node, ast.Call):
        parts.append(_dottedName(node.func) + "()")
    return ".".join(reversed(parts))
