"""Running Slicey with Claude Code (Claude subscription login, or an Anthropic-compatible server)
through the Claude Agent SDK, the same way as the nnInteractive Agent (nninteractive_agent.web.agent_sdk).

Slicey's tools (ClaudeClient.TOOLS) are served by an in-process SDK MCP server; Claude Code's own
tools (shell, file access, web, ...) are switched off, so the agent can do exactly what it could do
through the Anthropic API, and every tool call still goes through Slicey's confirmation. All methods
run on the asyncio loop of AgentBackends.AsyncRunner; no Slicer/Qt access happens here.
"""

import json
import os
import shutil
import subprocess

SERVER_NAME = "slicey"
# Variables that make Claude Code use something other than the subscription login.
ANTHROPIC_VARS = ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_BASE_URL")
# Tool results can be large (directory listings, file contents); the SDK's default 1 MB limit is too small.
MAX_BUFFER_SIZE = 64 * 1024 * 1024


def claudeExecutable():
    """The Claude Code CLI the SDK runs (its bundled one), or the one on PATH, or None."""
    try:
        import claude_agent_sdk

        name = "claude.exe" if os.name == "nt" else "claude"
        bundled = os.path.join(os.path.dirname(claude_agent_sdk.__file__), "_bundled", name)
        if os.path.isfile(bundled):
            return bundled
    except ImportError:
        pass
    return shutil.which("claude")


def checkLogin():
    """(ok, message) of the Claude subscription login. Blocking (runs `claude auth status`)."""
    exe = claudeExecutable()
    if exe is None:
        return False, "Claude Code is not installed."
    env = {k: v for k, v in os.environ.items() if k not in ANTHROPIC_VARS}
    kwargs = {"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {}
    try:
        out = subprocess.run([exe, "auth", "status", "--json"], capture_output=True, text=True, timeout=60,
                             env=env, check=False, **kwargs)
        status = json.loads(out.stdout)
    except (OSError, subprocess.SubprocessError, ValueError) as e:
        return False, f"Could not check the Claude Code login: {e}"
    if not status.get("loggedIn"):
        return False, (
            "Claude Code is not logged in. Open a terminal, run\n\n"
            f"  \"{exe}\"\n\n"
            "and log in with your Claude subscription account (Pro or Max), then check again."
        )
    who = status.get("email") or status.get("account", {}).get("email") or ""
    return True, f"Logged in{' as ' + who if who else ''}."


async def listModels(workDir, unsetVars=ANTHROPIC_VARS):
    """The models Claude Code offers to this login, as {"id", "label", "description"} dicts; its
    default model has the id "" (Slicey then passes no model)."""
    from claude_agent_sdk import ClaudeAgentOptions, ClaudeSDKClient

    for var in unsetVars:
        os.environ.pop(var, None)
    os.makedirs(workDir, exist_ok=True)
    options = ClaudeAgentOptions(tools=[], strict_mcp_config=True, setting_sources=[], permission_mode="dontAsk",
                                 cwd=workDir)
    async with ClaudeSDKClient(options) as client:
        info = await client.get_server_info() or {}
    listed = info.get("models") or []
    names = {m.get("resolvedModel"): m.get("displayName") for m in listed if m.get("value") != "default"}
    models = []
    for m in listed:
        modelId = "" if m.get("value") == "default" else m.get("value", "")
        label = m.get("displayName") or modelId
        if modelId == "":
            label = f"Default ({names.get(m.get('resolvedModel')) or m.get('resolvedModel')})"
        models.append({"id": modelId, "label": label, "description": m.get("description", "")})
    return models


class ClaudeCodeSession:
    """One conversation with Claude Code.

    callTool(name, toolInput) is a coroutine returning the tool's result dict (it runs the tool in
    Slicer, after the user's confirmation if needed). onEvent(kind, payload) receives "delta" (str,
    the next piece of the reply text while it is generated), "text" (str, a complete text block),
    "error" (str) and, at the end of each request, "done" (dict: inputTokens, outputTokens,
    costUsd, stopped, isError).
    """

    def __init__(self, systemPrompt, tools, callTool, onEvent, workDir, model="", effort="", env=None,
                 unsetVars=()):
        self.systemPrompt = systemPrompt
        self.workDir = workDir
        self.tools = tools
        self.callTool = callTool
        self.onEvent = onEvent
        self.model = model
        self.effort = effort
        self.env = dict(env or {})  # for the Claude Code process, on top of this process's environment
        self.unsetVars = unsetVars
        self.client = None
        self._interrupted = False

    def _handler(self, name):
        async def handler(args):
            result = await self.callTool(name, dict(args))
            isError = isinstance(result, dict) and "error" in result
            return {"content": [{"type": "text", "text": json.dumps(result)}], "is_error": isError}

        return handler

    def _options(self):
        from claude_agent_sdk import ClaudeAgentOptions, SdkMcpTool, create_sdk_mcp_server

        server = create_sdk_mcp_server(SERVER_NAME, tools=[
            SdkMcpTool(name=t["name"], description=t["description"], input_schema=t["input_schema"],
                       handler=self._handler(t["name"]))
            for t in self.tools
        ])
        os.makedirs(self.workDir, exist_ok=True)
        return ClaudeAgentOptions(
            mcp_servers={SERVER_NAME: server},
            strict_mcp_config=True,  # only Slicey's tools, not the user's other MCP servers/connectors
            tools=[],  # no built-in tools: files only through the shared folders, code only through Slicer
            allowed_tools=[f"mcp__{SERVER_NAME}__*"],  # Slicey asks for confirmation itself
            permission_mode="dontAsk",
            setting_sources=[],  # do not load the user's Claude Code settings / CLAUDE.md
            system_prompt=self.systemPrompt,
            model=self.model or None,
            effort=self.effort or None,
            cwd=self.workDir,
            max_buffer_size=MAX_BUFFER_SIZE,
            env=self.env,
            include_partial_messages=True,  # stream the reply text
        )

    async def start(self):
        from claude_agent_sdk import ClaudeSDKClient

        # The SDK passes this process's environment on to Claude Code: an API key there would be
        # used (and billed) instead of the subscription login.
        for var in self.unsetVars:
            os.environ.pop(var, None)
        self.client = ClaudeSDKClient(self._options())
        await self.client.connect()

    async def send(self, text):
        """Sends a user message and streams the agent's work until its reply is complete."""
        from claude_agent_sdk import AssistantMessage, ResultMessage, StreamEvent, TextBlock

        if self.client is None:
            await self.start()
        self._interrupted = False
        await self.client.query(text)
        result = None
        async for msg in self.client.receive_response():
            if isinstance(msg, StreamEvent) and msg.parent_tool_use_id is None:
                delta = (msg.event.get("delta") or {}) if msg.event.get("type") == "content_block_delta" else {}
                if delta.get("type") == "text_delta" and delta.get("text"):
                    self.onEvent("delta", delta["text"])
            elif isinstance(msg, AssistantMessage) and msg.parent_tool_use_id is None:
                for block in msg.content:
                    if isinstance(block, TextBlock) and block.text.strip():
                        self.onEvent("text", block.text)
            elif isinstance(msg, ResultMessage):
                result = msg
        stopped = self._interrupted  # Claude Code reports a stop as "error_during_execution"
        isError = bool(result and result.is_error and not stopped)
        if isError:
            detail = "; ".join(result.errors or []) or result.result or result.subtype
            self.onEvent("error", f"Claude Code: {detail}")
        usage = (result.usage or {}) if result else {}
        inputTokens = sum(usage.get(k) or 0 for k in ("input_tokens", "cache_read_input_tokens",
                                                       "cache_creation_input_tokens"))
        self.onEvent("done", {
            "inputTokens": inputTokens,
            "outputTokens": usage.get("output_tokens") or 0,
            "costUsd": result.total_cost_usd if result else None,
            "stopped": stopped,
            "isError": isError,
        })

    async def interrupt(self):
        if self.client is not None:
            self._interrupted = True
            await self.client.interrupt()

    async def close(self):
        if self.client is not None:
            client, self.client = self.client, None
            await client.disconnect()
