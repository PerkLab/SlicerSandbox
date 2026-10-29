"""Local agents as Slicey's LLM, the same choices as the nnInteractive Agent module
(nninteractive_agent.web.llm):

    claude      Claude Code on the Claude subscription (login) of this computer's user
    codex       Codex on the ChatGPT subscription (login) of this computer's user
    codex-api   Codex with an OpenAI API key
    server      Claude Code on an Anthropic-compatible server: open models, e.g. vLLM on this
                machine (the default URL, http://localhost:8000) or on another one

("claude-api", the Anthropic Messages API with an API key, is ClaudeClient.)

Agent sessions run on one asyncio loop in a background thread (AsyncRunner). They call Slicey's
tools through a callTool coroutine provided by SliceyLogic, which runs each tool on Slicer's main
thread (or a worker thread), after the user's confirmation when needed.
"""

import asyncio
import glob
import importlib
import importlib.util
import json
import logging
import os
import threading
import urllib.error
import urllib.parse
import urllib.request

import slicer

from . import ClaudeCodeAgent
from . import CodexAgent
from . import ServerRelay
from . import Settings

logger = logging.getLogger(__name__)

AGENT_BACKENDS = ("claude", "codex", "codex-api", "server")
CHECK_TIMEOUT_S = 180


class AsyncRunner:
    """One asyncio event loop on a daemon thread, started on first use."""

    def __init__(self):
        self._loop = None
        self._thread = None

    def submit(self, coro):
        """Schedules the coroutine on the loop; returns a concurrent.futures.Future."""
        if self._loop is None:
            self._loop = asyncio.new_event_loop()
            self._thread = threading.Thread(target=self._loop.run_forever, name="SliceyAgent", daemon=True)
            self._thread.start()
        return asyncio.run_coroutine_threadsafe(coro, self._loop)

    def stop(self):
        if self._loop is None:
            return
        loop, self._loop = self._loop, None
        loop.call_soon_threadsafe(loop.stop)
        self._thread.join(5)


def ensureClaudeAgentSdk():
    """Installs the Claude Agent SDK (which bundles Claude Code) into Slicer's Python if needed,
    after asking the user. Main thread only. (The SDK takes a second to import: it is imported on
    the agent thread, where it is used.)"""
    if _installedSdkVersion() >= (0, 2, 165):
        return
    from slicer.packaging import pip_ensure

    pip_ensure("claude-agent-sdk>=0.2.165", requester="Slicey")
    importlib.invalidate_caches()
    if _installedSdkVersion() < (0, 2, 165):
        raise RuntimeError("The Claude Agent SDK (claude-agent-sdk>=0.2.165) is not installed.")


def _installedSdkVersion():
    """The installed claude-agent-sdk version as a tuple, () if none. Reads the name of its
    .dist-info folder: pip_ensure and importlib.metadata scan every path of Slicer's Python, which
    takes about a second on the main thread."""
    spec = importlib.util.find_spec("claude_agent_sdk")
    if spec is None or not spec.origin:
        return ()
    sitePackages = os.path.dirname(os.path.dirname(spec.origin))
    for path in glob.glob(os.path.join(sitePackages, "claude_agent_sdk-*.dist-info")):
        try:
            return tuple(int(part) for part in os.path.basename(path)[len("claude_agent_sdk-"):-len(".dist-info")].split(".")[:3])
        except ValueError:
            continue
    return ()


def prepareCheck(backend):
    """What checkBackend needs from the main thread: installs the Claude Agent SDK if needed (asks
    the user first). Main thread."""
    if backend in ("claude", "server"):
        ensureClaudeAgentSdk()


def checkBackend(backend, runner, apiKey=None, serverUrl=None):
    """Checks that `backend` can be used (login present, key accepted, server reachable) and lists
    the models it offers. Blocking, without Slicer access: runs on a worker thread, after
    prepareCheck(). Returns (ok: bool, message: str, models: list or None); the main thread
    stores the models with storeModels()."""
    try:
        if backend == "claude":
            ok, message = ClaudeCodeAgent.checkLogin()
            models = None
            if ok:
                models = runner.submit(ClaudeCodeAgent.listModels(Settings.AGENT_WORK_DIR)).result(CHECK_TIMEOUT_S)
            return ok, message, models or None
        if backend in ("codex", "codex-api"):
            return _checkCodex(backend, runner, apiKey)
        if backend == "server":
            return _checkServer(serverUrl, apiKey)
        return False, f"Unknown backend {backend!r}", None
    except Exception as e:
        logger.exception("Slicey: backend check failed")
        return False, f"{type(e).__name__}: {e}", None


def _checkCodex(backend, runner, apiKey):
    if CodexAgent.codexExecutable() is None:
        return False, (
            "Codex is not installed. Install Node.js, then run\n\n  npm install -g @openai/codex\n\n"
            "in a terminal, and restart Slicer."
        ), None
    if backend == "codex-api":
        if not apiKey:
            return False, "No OpenAI API key.", None
        _checkKey("https://api.openai.com/v1/models", {"authorization": f"Bearer {apiKey}"}, "OpenAI")
    home = Settings.CODEX_API_HOME if backend == "codex-api" else None
    info = runner.submit(CodexAgent.probe(home, apiKey if backend == "codex-api" else None)).result(CHECK_TIMEOUT_S)
    account = info["account"] or {}
    if backend == "codex" and account.get("type") != "chatgpt":
        return False, "Codex is not logged in with ChatGPT. Open a terminal, run\n\n  codex login\n\nand check again.", None
    if backend == "codex-api" and account.get("type") != "apiKey":
        return False, "Codex did not accept the API key.", None
    models = info["models"]
    if not models:
        return False, "Codex lists no models.", None
    models.sort(key=lambda m: not m["default"])  # the default model first
    plan = account.get("planType")
    return True, f"Logged in ({'ChatGPT ' + plan if plan else account.get('type')}).", [
        {"id": m["id"], "label": m["label"], "description": m.get("description", "")} for m in models]


def _serverHeaders(key):
    key = key or "none"
    return {"x-api-key": key, "authorization": f"Bearer {key}", "anthropic-version": "2023-06-01"}


def _checkServer(url, key):
    url = url.rstrip("/")
    _bypassProxy(url)
    status, body = _http(f"{url}/v1/models", _serverHeaders(key))
    if status != 200:
        return False, f"{url}/v1/models answered {status}: {str(body)[:300]}", None
    ids = [m.get("id") for m in (body.get("data") or []) if m.get("id")]
    if not ids:
        return False, f"{url} lists no models.", None
    return True, f"Connected; {len(ids)} model(s): {', '.join(ids)}.", [
        {"id": i, "label": i, "description": ""} for i in ids]


def storeModels(backend, models):
    """Offers `models` for `backend`; the chosen model becomes the first one if it is not among
    them. Main thread."""
    Settings.setBackendModels(backend, models)
    ids = [m["id"] for m in models]
    if Settings.getBackendModel(backend) not in ids:
        Settings.setBackendModel(backend, ids[0])


def _bypassProxy(url):
    """Internal hosts are often not reachable through a proxy."""
    host = urllib.parse.urlparse(url).hostname or url
    for var in ("NO_PROXY", "no_proxy"):
        values = [v for v in (os.environ.get(var) or "").split(",") if v]
        if host not in values:
            os.environ[var] = ",".join(values + [host])


def createSession(backend, systemPrompt, tools, callTool, onEvent):
    """A new agent conversation for `backend`, configured from the current settings. Main thread."""
    model = Settings.getBackendModel(backend)
    effort = Settings.getEffort()
    workDir = Settings.AGENT_WORK_DIR
    if backend == "claude":
        ensureClaudeAgentSdk()
        return ClaudeCodeAgent.ClaudeCodeSession(systemPrompt, tools, callTool, onEvent, workDir, model, effort,
                                                 unsetVars=ClaudeCodeAgent.ANTHROPIC_VARS)
    if backend == "server":
        ensureClaudeAgentSdk()
        url = Settings.getLlmServerUrl().rstrip("/")
        if not model:
            raise RuntimeError("No model chosen for the LLM server: click Connect in the Connection panel.")
        _bypassProxy(url)
        relay = ServerRelay.relayUrl(url)
        _bypassProxy(relay)
        env = {
            # Claude Code sends system messages mid-conversation, which many local models reject.
            "ANTHROPIC_BASE_URL": relay,
            "ANTHROPIC_API_KEY": Settings.getApiKey(Settings.LLM_SERVER_KEYRING_USERNAME) or "none",
            # Claude Code's own small requests use the same model.
            "ANTHROPIC_DEFAULT_OPUS_MODEL": model, "ANTHROPIC_DEFAULT_SONNET_MODEL": model,
            "ANTHROPIC_DEFAULT_HAIKU_MODEL": model,
            "ENABLE_TOOL_SEARCH": "false", "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1",
        }
        return ClaudeCodeAgent.ClaudeCodeSession(systemPrompt, tools, callTool, onEvent, workDir, model, effort,
                                                 env=env, unsetVars=("ANTHROPIC_AUTH_TOKEN",))
    if backend in ("codex", "codex-api"):
        home = Settings.CODEX_API_HOME if backend == "codex-api" else None
        return CodexAgent.CodexSession(systemPrompt, tools, callTool, onEvent, workDir, model, effort, home)
    raise RuntimeError(f"{backend!r} is not a local-agent backend")


def _checkKey(url, headers, provider):
    status, body = _http(url, headers)
    if status in (401, 403):
        raise RuntimeError(f"the {provider} API rejected the key ({status})")
    if status != 200:
        raise RuntimeError(f"could not check the {provider} API key: {url} answered {status}: {str(body)[:200]}")


def _http(url, headers, payload=None, timeout=60):
    """(status, parsed JSON or text); RuntimeError if the server cannot be reached."""
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data, {**headers, "content-type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            status, raw = r.status, r.read()
    except urllib.error.HTTPError as e:
        status, raw = e.code, e.read()
    except (urllib.error.URLError, OSError) as e:
        raise RuntimeError(f"cannot reach {url}: {getattr(e, 'reason', e)}") from e
    try:
        return status, json.loads(raw)
    except ValueError:
        return status, raw.decode(errors="replace")
