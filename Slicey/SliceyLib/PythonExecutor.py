import atexit
import base64
import contextlib
import io
import json
import logging
import os
import socket
import subprocess
import tempfile
import time
import traceback
import urllib.error
import urllib.request

import slicer

logger = logging.getLogger(__name__)


def executeInProcess(code):
    """Executes `code` directly inside this already-running Slicer process. Must be called
    from the main thread (touches slicer/vtk/qt/ctk).
    """
    import ctk
    import qt
    import vtk

    execGlobals = {"slicer": slicer, "vtk": vtk, "qt": qt, "ctk": ctk}
    try:
        import numpy
        execGlobals["numpy"] = numpy
    except ImportError:
        pass

    stdoutBuf = io.StringIO()
    stderrBuf = io.StringIO()
    try:
        with contextlib.redirect_stdout(stdoutBuf), contextlib.redirect_stderr(stderrBuf):
            exec(code, execGlobals)
        result = execGlobals.get("__execResult")
        return {
            "stdout": stdoutBuf.getvalue(),
            "stderr": stderrBuf.getvalue(),
            "success": True,
            "error": None,
            "result": result if isinstance(result, dict) else None,
        }
    except Exception:
        return {
            "stdout": stdoutBuf.getvalue(),
            "stderr": stderrBuf.getvalue(),
            "success": False,
            "error": traceback.format_exc(),
            "result": None,
        }


def _wrapCodeForRemoteCapture(code):
    """Returns Python source text that, when exec'd by WebServer's /slicer/exec handler,
    runs `code` while capturing stdout/stderr into the __execResult dict the handler already
    returns as JSON. The user code is embedded as base64 so no escaping/quoting concerns
    arise regardless of its content.
    """
    encoded = base64.b64encode(code.encode("utf-8")).decode("ascii")
    return (
        "import base64, io, contextlib, traceback\n"
        f"__slicey_code = base64.b64decode({encoded!r}).decode('utf-8')\n"
        "__slicey_stdout = io.StringIO()\n"
        "__slicey_stderr = io.StringIO()\n"
        "__slicey_globals = globals()\n"
        "try:\n"
        "    with contextlib.redirect_stdout(__slicey_stdout), contextlib.redirect_stderr(__slicey_stderr):\n"
        "        exec(__slicey_code, __slicey_globals)\n"
        "    __slicey_result = __slicey_globals.get('__execResult')\n"
        "    __execResult = {\n"
        "        'stdout': __slicey_stdout.getvalue(),\n"
        "        'stderr': __slicey_stderr.getvalue(),\n"
        "        'success': True,\n"
        "        'error': None,\n"
        "        'result': __slicey_result if isinstance(__slicey_result, dict) else None,\n"
        "    }\n"
        "except Exception:\n"
        "    __execResult = {\n"
        "        'stdout': __slicey_stdout.getvalue(),\n"
        "        'stderr': __slicey_stderr.getvalue(),\n"
        "        'success': False,\n"
        "        'error': traceback.format_exc(),\n"
        "        'result': None,\n"
        "    }\n"
    )


class _CompanionInstance:
    def __init__(self):
        self.process = None
        self.port = None

    def isRunning(self):
        return self.process is not None and self.process.poll() is None

    def stop(self):
        if self.process is not None and self.process.poll() is None:
            try:
                self.process.terminate()
                try:
                    self.process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    self.process.kill()
            except Exception:
                logger.warning("Slicey: error stopping companion Slicer instance", exc_info=True)
        self.process = None
        self.port = None


_companion = _CompanionInstance()
atexit.register(_companion.stop)


def _findFreePort():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]
    finally:
        s.close()


def _writeStartupScript(port):
    script = (
        "widget = slicer.modules.webserver.widgetRepresentation().self()\n"
        "widget.enableSlicerHandler.checked = True\n"
        "widget.enableSlicerHandlerExec.checked = True\n"
        f"widget.logic.port = {port}\n"
        "widget.startServer()\n"
    )
    fd, path = tempfile.mkstemp(prefix="SliceyWebServerStartup_", suffix=".py")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(script)
    return path


def _isServerReady(port, timeoutSeconds):
    deadline = time.time() + timeoutSeconds
    url = f"http://localhost:{port}/slicer/system/version"
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2) as response:
                if response.status == 200:
                    return True
        except Exception:
            pass
        time.sleep(0.3)
    return False


def companionInstanceRunning():
    return _companion.isRunning()


def stopCompanionInstance():
    _companion.stop()


def ensureCompanionInstance(timeoutSeconds=60):
    """Launches (if not already running) a companion Slicer process with the WebServer exec
    API enabled, and waits until it responds. Safe to call from a background thread (only
    touches subprocess/socket/urllib, not Slicer/Qt objects). Returns the port number.
    """
    if _companion.isRunning() and _isServerReady(_companion.port, timeoutSeconds=1):
        return _companion.port

    _companion.stop()
    port = _findFreePort()
    scriptPath = _writeStartupScript(port)
    exePath = slicer.app.applicationFilePath()
    process = subprocess.Popen([exePath, "--python-script", scriptPath, "--no-splash"])
    _companion.process = process
    _companion.port = port

    if not _isServerReady(port, timeoutSeconds=timeoutSeconds):
        _companion.stop()
        raise RuntimeError(f"Timed out waiting for the companion Slicer instance's web server to start on port {port}")

    return port


def executeInNewInstance(code, timeoutSeconds=120):
    """Runs `code` in a companion Slicer instance over its WebServer exec API. Safe to call
    from a background thread.
    """
    try:
        port = ensureCompanionInstance()
    except Exception as e:
        return {"stdout": "", "stderr": "", "success": False, "error": str(e), "result": None}

    wrapped = _wrapCodeForRemoteCapture(code)
    url = f"http://localhost:{port}/slicer/exec"
    request = urllib.request.Request(url, data=wrapped.encode("utf-8"), method="POST")
    try:
        with urllib.request.urlopen(request, timeout=timeoutSeconds) as response:
            body = response.read().decode("utf-8")
    except urllib.error.URLError as e:
        return {"stdout": "", "stderr": "", "success": False, "error": f"Could not reach companion Slicer instance: {e}", "result": None}

    try:
        result = json.loads(body)
    except json.JSONDecodeError:
        return {"stdout": "", "stderr": body, "success": False, "error": "Companion instance returned a non-JSON response", "result": None}
    return result
