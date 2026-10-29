"""Running Slicey with Codex (ChatGPT subscription login, or an OpenAI API key) through
``codex app-server``, the same way as the nnInteractive Agent (nninteractive_agent.web.agent_codex).

The app server speaks JSON-RPC over stdio, one JSON object per line. Slicey's tools are registered
as dynamic tools: Codex sends ``item/tool/call`` back and the tool runs in Slicer (after the user's
confirmation if needed). Codex's own tools (shell, patches, plugins, browser, web search, ...) are
switched off; code mode stays, because the current models call tools from JavaScript in ``exec``,
run by the ``codex-code-mode-host`` that ships with Codex. All methods run on the asyncio loop of
AgentBackends.AsyncRunner; no Slicer/Qt access happens here.

Written against codex-cli 0.162.1.
"""

import asyncio
import json
import os
import shutil

# Codex features switched off: everything that reaches beyond Slicey's tools.
# Not "code_mode_host": code mode is how the current models call tools.
DISABLED_FEATURES = (
    "shell_tool", "unified_exec", "apps", "plugins", "remote_plugin", "browser_use",
    "browser_use_external", "computer_use", "in_app_browser", "image_generation", "view_image", "goals",
    "sleep_tool", "tool_suggest", "skill_search", "skill_mcp_dependency_install", "workspace_dependencies",
    "memories", "hooks", "multi_agent",
)
# Streaming deltas Slicey does not show (it streams only the reply text, item/agentMessage/delta).
_QUIET = (
    "item/reasoning/textDelta", "item/reasoning/summaryTextDelta",
    "item/reasoning/summaryPartAdded", "item/plan/delta", "item/commandExecution/outputDelta",
    "item/fileChange/outputDelta",
)
EFFORTS = ("low", "medium", "high", "xhigh", "max")
CLIENT_VERSION = "1.0"


class CodexError(RuntimeError):
    """A failed request to the app server, or the app server is gone."""


def codexExecutable():
    """The codex CLI on PATH (codex.cmd of the npm package on Windows), or None."""
    return shutil.which("codex")


def toolSpecs(tools):
    return [{"type": "function", "name": t["name"], "description": t["description"], "inputSchema": t["input_schema"]}
            for t in tools]


class AppServer:
    """One ``codex app-server`` process. onRequest(method, params) (async) answers the server's
    requests (None declines them); onNotification(method, params) receives everything else."""

    def __init__(self, codexHome=None, onNotification=None, onRequest=None, logFile=None):
        self.codexHome = codexHome
        self.onNotification = onNotification
        self.onRequest = onRequest
        self.logFile = logFile
        self.proc = None
        self.closed = asyncio.Event()
        self._reader = None
        self._pending = {}
        self._tasks = set()
        self._nextId = 0
        self._writeLock = asyncio.Lock()

    async def start(self):
        exe = codexExecutable()
        if exe is None:
            raise CodexError("codex is not installed (npm install -g @openai/codex)")
        # The API key of codex-api is stored in its own CODEX_HOME at login; keys in the environment
        # must not override the ChatGPT login of the default home.
        env = {k: v for k, v in os.environ.items() if k not in ("OPENAI_API_KEY", "CODEX_API_KEY")}
        if self.codexHome is not None:
            os.makedirs(self.codexHome, mode=0o700, exist_ok=True)
            env["CODEX_HOME"] = self.codexHome
        args = [exe, "app-server"] + [a for f in DISABLED_FEATURES for a in ("--disable", f)]
        # The child keeps its own copy of the log's file descriptor.
        log = open(self.logFile, "ab") if self.logFile else None
        kwargs = {"creationflags": 0x08000000} if os.name == "nt" else {}  # CREATE_NO_WINDOW
        try:
            self.proc = await asyncio.create_subprocess_exec(
                *args, stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
                stderr=log or asyncio.subprocess.DEVNULL, env=env, limit=1 << 28, **kwargs,
            )
        finally:
            if log is not None:
                log.close()
        self._reader = asyncio.ensure_future(self._read())
        info = await self.request("initialize", {
            "clientInfo": {"name": "slicey", "title": "Slicey", "version": CLIENT_VERSION},
            "capabilities": {"experimentalApi": True, "optOutNotificationMethods": list(_QUIET)},
        }, timeout=120)
        await self._send({"method": "initialized"})
        return info

    async def request(self, method, params, timeout=None):
        if self.closed.is_set():
            raise CodexError(f"codex app-server is not running{self._logTail()}")
        self._nextId += 1
        fut = asyncio.get_running_loop().create_future()
        self._pending[self._nextId] = fut
        await self._send({"id": self._nextId, "method": method, "params": params})
        return await asyncio.wait_for(fut, timeout)

    async def _send(self, msg):
        async with self._writeLock:
            self.proc.stdin.write((json.dumps(msg) + "\n").encode())
            await self.proc.stdin.drain()

    async def _read(self):
        try:
            while True:
                line = await self.proc.stdout.readline()
                if not line:
                    break
                try:
                    msg = json.loads(line)
                except ValueError:
                    continue
                if "method" not in msg:  # a response
                    fut = self._pending.pop(msg.get("id"), None)
                    if fut is not None and not fut.done():
                        if "error" in msg:
                            fut.set_exception(CodexError(msg["error"].get("message") or str(msg["error"])))
                        else:
                            fut.set_result(msg.get("result") or {})
                elif "id" in msg:  # a request from the server
                    task = asyncio.ensure_future(self._answer(msg))
                    self._tasks.add(task)
                    task.add_done_callback(self._tasks.discard)
                elif self.onNotification is not None:
                    self.onNotification(msg["method"], msg.get("params") or {})
        except (OSError, ValueError):  # a broken pipe or an oversized line ends the connection
            pass
        finally:
            self.closed.set()
            for fut in self._pending.values():
                if not fut.done():
                    fut.set_exception(CodexError(f"codex app-server exited{self._logTail()}"))
            self._pending.clear()

    async def _answer(self, msg):
        method = msg["method"]
        try:
            result = await self.onRequest(method, msg.get("params") or {}) if self.onRequest else None
            if result is not None:
                reply = {"id": msg["id"], "result": result}
            else:
                reply = {"id": msg["id"], "error": {"code": -32601, "message": f"{method} is not available in Slicey"}}
        except Exception as e:  # reported to Codex, which tells the model
            reply = {"id": msg["id"], "error": {"code": -32603, "message": f"{type(e).__name__}: {e}"}}
        try:
            await self._send(reply)
        except (OSError, RuntimeError):
            pass

    def _logTail(self):
        if self.logFile is None or not os.path.exists(self.logFile):
            return ""
        with open(self.logFile, encoding="utf-8", errors="replace") as f:
            lines = [s for s in f.read().splitlines() if s.strip()]
        return (": " + " | ".join(lines[-3:])[-600:]) if lines else ""

    async def close(self):
        if self.proc is not None and self.proc.returncode is None:
            try:
                self.proc.stdin.close()
                await asyncio.wait_for(self.proc.wait(), 3)
            except (asyncio.TimeoutError, OSError, RuntimeError):
                self.proc.terminate()
                try:
                    await asyncio.wait_for(self.proc.wait(), 3)
                except asyncio.TimeoutError:
                    self.proc.kill()
                    await self.proc.wait()
        if self._reader is not None:
            await asyncio.gather(self._reader, return_exceptions=True)


async def probe(codexHome=None, apiKey=None):
    """Signs in with an API key (stored in codexHome) or reads the login, and lists the models:
    {"account": {...} | None, "models": [{"id", "label", "description", "efforts", "default"}]}."""
    server = AppServer(codexHome)
    await server.start()
    try:
        if apiKey:
            await server.request("account/login/start", {"type": "apiKey", "apiKey": apiKey}, timeout=60)
        account = (await server.request("account/read", {}, timeout=60)).get("account")
        data, cursor = [], None
        while True:
            res = await server.request("model/list", {"cursor": cursor} if cursor else {}, timeout=60)
            data += res.get("data") or []
            cursor = res.get("nextCursor")
            if not cursor:
                break
    finally:
        await server.close()
    models = []
    for m in data:
        if m.get("hidden"):
            continue
        efforts = [e.get("reasoningEffort") for e in m.get("supportedReasoningEfforts") or []]
        models.append({"id": m["id"], "label": m.get("displayName") or m["id"], "description": m.get("description") or "",
                       "efforts": [e for e in EFFORTS if e in efforts], "default": bool(m.get("isDefault"))})
    return {"account": account, "models": models}


class CodexSession:
    """One conversation with Codex; the interface of ClaudeCodeAgent.ClaudeCodeSession."""

    def __init__(self, systemPrompt, tools, callTool, onEvent, workDir, model="", effort="", codexHome=None):
        self.systemPrompt = systemPrompt
        self.tools = tools
        self.callTool = callTool
        self.onEvent = onEvent
        self.workDir = workDir
        self.model = model
        self.effort = effort
        self.codexHome = codexHome
        self.server = None
        self.threadId = None
        self._turnId = None
        self._turn = None
        self._turnDone = None
        self._lastError = ""
        self._interrupted = False
        self._usage = {"inputTokens": 0, "outputTokens": 0}

    async def start(self):
        os.makedirs(self.workDir, exist_ok=True)
        self.server = AppServer(self.codexHome, self._onNotification, self._onRequest,
                                os.path.join(self.workDir, "codex.log"))
        try:
            await self.server.start()
            params = {
                "cwd": self.workDir, "sandbox": "read-only", "approvalPolicy": "never", "ephemeral": True,
                "dynamicTools": toolSpecs(self.tools), "config": {"web_search": "disabled"},
                "developerInstructions": self.systemPrompt,
            }
            if self.model:  # else Codex's default model
                params["model"] = self.model
            res = await self.server.request("thread/start", params, timeout=120)
        except BaseException:
            await self.close()
            raise
        self.threadId = res["thread"]["id"]

    async def send(self, text):
        """Sends a user message and streams the agent's work until its turn ends."""
        if self.server is not None and self.server.closed.is_set():
            await self.close()
            self.onEvent("error", "Codex had stopped and was restarted; the conversation starts fresh.")
        if self.server is None:
            await self.start()
        self._interrupted, self._lastError = False, ""
        self._turn, self._turnId, self._turnDone = None, None, asyncio.Event()
        usage0 = dict(self._usage)
        try:
            params = {"threadId": self.threadId, "input": [{"type": "text", "text": text, "text_elements": []}]}
            if self.effort:
                params["effort"] = self.effort
            res = await self.server.request("turn/start", params)
            self._turnId = self._turnId or (res.get("turn") or {}).get("id")
            done = asyncio.ensure_future(self._turnDone.wait())
            gone = asyncio.ensure_future(self.server.closed.wait())
            await asyncio.wait({done, gone}, return_when=asyncio.FIRST_COMPLETED)
            done.cancel()
            gone.cancel()
            if not self._turnDone.is_set():
                raise CodexError(f"codex app-server exited{self.server._logTail()}")
        except CodexError as e:
            self._turn = {"status": "failed", "error": {"message": str(e)}}
        turn = self._turn or {}
        status = turn.get("status")
        stopped = self._interrupted or status == "interrupted"
        error = (turn.get("error") or {}).get("message") or self._lastError
        isError = status != "completed" and not stopped
        if isError and error:
            self.onEvent("error", f"Codex: {error}")
        self.onEvent("done", {
            "inputTokens": self._usage["inputTokens"] - usage0["inputTokens"],
            "outputTokens": self._usage["outputTokens"] - usage0["outputTokens"],
            "costUsd": None,
            "stopped": stopped,
            "isError": isError,
        })

    def _onNotification(self, method, params):
        if params.get("threadId") not in (None, self.threadId):
            return
        if method == "thread/tokenUsage/updated":
            total = (params.get("tokenUsage") or {}).get("total") or {}
            self._usage = {"inputTokens": total.get("inputTokens") or 0, "outputTokens": total.get("outputTokens") or 0}
        elif method == "item/agentMessage/delta":
            if params.get("delta"):
                self.onEvent("delta", params["delta"])
        elif method == "item/completed":
            item = params.get("item") or {}
            if item.get("type") == "agentMessage" and (item.get("text") or "").strip():
                self.onEvent("text", item["text"])
        elif method == "turn/started":
            self._turnId = self._turnId or (params.get("turn") or {}).get("id")
        elif method == "turn/completed":
            turn = params.get("turn") or {}
            if self._turnDone is not None and self._turnId in (None, turn.get("id")):
                self._turn = turn
                self._turnDone.set()
        elif method == "error" and not params.get("willRetry"):
            self._lastError = (params.get("error") or {}).get("message", "")

    async def _onRequest(self, method, params):
        if method != "item/tool/call":
            return None
        result = await self.callTool(params.get("tool", ""), _args(params.get("arguments")))
        isError = isinstance(result, dict) and "error" in result
        return {"contentItems": [{"type": "inputText", "text": json.dumps(result)}], "success": not isError}

    async def interrupt(self):
        if self.server is not None and self.threadId and self._turnId:
            self._interrupted = True
            try:
                await self.server.request("turn/interrupt", {"threadId": self.threadId, "turnId": self._turnId},
                                          timeout=15)
            except (CodexError, asyncio.TimeoutError):
                pass

    async def close(self):
        if self.server is not None:
            server, self.server = self.server, None
            await server.close()


def _args(arguments):
    if isinstance(arguments, str):
        try:
            arguments = json.loads(arguments)
        except ValueError:
            return {}
    return dict(arguments) if isinstance(arguments, dict) else {}
