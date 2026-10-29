import asyncio
import concurrent.futures
import datetime
import html
import json
import logging
import os
import queue
import threading
import time
import uuid

import qt

import slicer
from slicer.ScriptedLoadableModule import *

from SliceyLib import ClaudeClient, FolderAccess, PythonExecutor, Settings

logger = logging.getLogger(__name__)

# Style for the two primary call-to-action buttons (Send, Approve) so they're clearly
# distinguishable from secondary buttons (Stop, Clear, Reject) at a glance.
_PRIMARY_BUTTON_STYLE = (
    "QPushButton {"
    "  background-color: #2e7d32; color: white; font-weight: bold;"
    "  padding: 4px 14px; border-radius: 4px; border: 1px solid #1b5e20;"
    "}"
    "QPushButton:hover { background-color: #388e3c; }"
    "QPushButton:pressed { background-color: #1b5e20; }"
    "QPushButton:disabled { background-color: #9e9e9e; color: #eeeeee; border-color: #9e9e9e; }"
)
# Shown on the Send button while Slicey works.
_SPINNER = "◐◓◑◒"
# What Slicey is doing while a tool runs, shown above the prompt box.
_TOOL_ACTIVITY = {
    "run_python_in_slicer": "Running Python code",
    "list_shared_folders": "Listing the shared folders",
    "list_directory": "Listing files",
    "read_text_file": "Reading a file",
    "write_text_file": "Writing a file",
    "list_past_chats": "Looking through past chats",
    "read_past_chat": "Reading a past chat",
}

# The prompt box is framed in the Send button's color, so it is easy to find.
_PROMPT_STYLE = "QPlainTextEdit { border: 2px solid #2e7d32; border-radius: 4px; }"


# What the Connection panel's buttons do and say for each backend (Settings.BACKENDS).
_CONNECT_BUTTON_TEXT = {
    "claude-api": "Connect Claude account...",
    "claude": "Check Claude Code login",
    "codex": "Check Codex login",
    "codex-api": "Enter OpenAI API key...",
    "server": "Connect to server",
}
_USAGE_URLS = {
    "claude-api": "https://platform.claude.com/settings/keys",
    "claude": "https://claude.ai/settings/usage",
    "codex": "https://chatgpt.com/codex/settings/usage",
    "codex-api": "https://platform.openai.com/usage",
}
_CONNECTED_TEXT = {
    "claude": "Logged in (Claude subscription, no API token costs)",
    "codex": "Logged in (ChatGPT subscription, no API token costs)",
    "codex-api": "Connected (OpenAI API key, usage is billed by OpenAI)",
    "server": "Connected to {url}",
}


class _GilYielder:
    """While Slicey works in the background, lets its Python threads run.

    Slicer's main thread holds Python's global interpreter lock while it waits for events, so
    another Python thread gets it back after every system call (reading a pipe or socket,
    checking a file) only when the main thread happens to run Python: in an idle Slicer that
    made background threads ~1500x slower (importing the Claude Agent SDK took minutes). A
    timer that sleeps briefly on the main thread hands the lock over regularly (~40% of full
    speed for the background thread; the 5 ms pauses go unnoticed in the GUI)."""

    INTERVAL_MS = 10
    SLEEP_S = 0.005

    def __init__(self):
        self._users = 0
        self._timer = None

    def acquire(self):
        self._users += 1
        if self._timer is None:
            self._timer = qt.QTimer()
            self._timer.setInterval(self.INTERVAL_MS)
            self._timer.timeout.connect(lambda: time.sleep(self.SLEEP_S))
        if not self._timer.isActive():
            self._timer.start()

    def release(self):
        self._users = max(0, self._users - 1)
        if self._users == 0 and self._timer is not None:
            self._timer.stop()


_gilYielder = _GilYielder()
_backgroundTimers = set()  # keeps the poll timers of _runInBackground alive


def _runInBackground(work, onDone):
    """Runs work() on a worker thread and then onDone(result, error) on the main thread (error is
    None or the exception work raised), so Slicer stays usable while it waits."""
    future = concurrent.futures.Future()

    def worker():
        try:
            future.set_result(work())
        except Exception as e:
            future.set_exception(e)

    timer = qt.QTimer()
    timer.setInterval(100)

    def poll():
        if not future.done():
            return
        timer.stop()
        _backgroundTimers.discard(timer)
        _gilYielder.release()
        error = future.exception()
        onDone(None if error else future.result(), error)

    timer.timeout.connect(poll)
    _backgroundTimers.add(timer)
    _gilYielder.acquire()
    timer.start()
    threading.Thread(target=worker, daemon=True).start()


def _escape(text):
    return html.escape(str(text))


def _markdownFragment(text):
    """Markdown formatted by Qt (CommonMark and GitHub tables), for inserting in the chat view.
    (Qt's HTML export of it loses formatting, e.g. a list item that starts in bold is all bold.)"""
    document = qt.QTextDocument()
    document.setMarkdown(text)
    # Code gets the system's "fixed" font, which can be proportional (MS Shell Dlg 2 on Windows):
    # give code - the only text with an explicit font family - a monospace font.
    cursor = qt.QTextCursor(document)
    monospace = qt.QTextCharFormat()
    monospace.setFontFamily("Courier New")
    runStart = None
    for position in range(1, document.characterCount()):
        cursor.setPosition(position)
        if cursor.charFormat().fontFamily():
            if runStart is None:
                runStart = position - 1
        elif runStart is not None:
            _mergeFormat(cursor, runStart, position - 1, monospace)
            runStart = None
    if runStart is not None:
        _mergeFormat(cursor, runStart, document.characterCount() - 1, monospace)
    return qt.QTextDocumentFragment(document)


def _mergeFormat(cursor, start, end, charFormat):
    cursor.setPosition(start)
    cursor.setPosition(end, qt.QTextCursor.KeepAnchor)
    cursor.mergeCharFormat(charFormat)


def _escapeMultiline(text):
    """Escapes text for HTML and turns newlines into <br> so multi-line replies actually
    render as multiple lines instead of being collapsed onto one (HTML ignores raw \\n)."""
    return _escape(text).replace("\n", "<br>")


# Plain <pre> never wraps (white-space: pre disables wrapping entirely), which forces
# horizontal scrolling for long code/JSON lines. pre-wrap keeps formatting but allows
# wrapping, and word-break/overflow-wrap let it break even an unbroken long token if needed.
_PRE_WRAP_STYLE = "white-space: pre-wrap; word-break: break-all; overflow-wrap: anywhere;"


def _contentBlockToDict(block):
    """Converts an Anthropic SDK content block object into a plain JSON-serializable dict."""
    blockType = getattr(block, "type", None)
    if blockType == "text":
        return {"type": "text", "text": block.text}
    if blockType == "tool_use":
        return {"type": "tool_use", "id": block.id, "name": block.name, "input": block.input}
    if hasattr(block, "model_dump"):
        return block.model_dump()
    return {"type": blockType}


def _cancelledToolResults(toolBlocks):
    """Builds tool_result content blocks for tool_use blocks that are being skipped because
    the user clicked Stop, so the assistant message that contains them always gets a matching
    tool_result (Anthropic rejects any history where it doesn't)."""
    return [
        {
            "type": "tool_result",
            "tool_use_id": block["id"],
            "content": json.dumps({"error": "Cancelled by the user before this tool call ran."}),
            "is_error": True,
        }
        for block in toolBlocks
    ]


def _renderMarkdownTranscript(messages):
    """Renders the Anthropic message list (the same structures sent to/from the API) as a
    readable Markdown chat log, including tool calls and their results."""
    lines = []
    toolNames = {}
    for message in messages:
        role = message.get("role")
        content = message.get("content")

        if role == "user" and isinstance(content, str):
            lines.append("## You\n")
            lines.append(f"{content}\n")

        elif role == "assistant" and isinstance(content, list):
            textParts = [b["text"] for b in content if b.get("type") == "text"]
            if textParts:
                lines.append("## Slicey\n")
                lines.append("\n".join(textParts) + "\n")
            for block in content:
                if block.get("type") == "tool_use":
                    toolNames[block["id"]] = block["name"]
                    lines.append(f"### Tool call: {block['name']}\n")
                    lines.append("```json")
                    lines.append(json.dumps(block.get("input", {}), indent=2))
                    lines.append("```\n")

        elif role == "user" and isinstance(content, list):
            for block in content:
                if block.get("type") == "tool_result":
                    name = toolNames.get(block.get("tool_use_id"), "tool")
                    label = "Rejected" if block.get("is_error") else "Result"
                    lines.append(f"**{label} of {name}:**\n")
                    lines.append("```json")
                    lines.append(str(block.get("content", "")))
                    lines.append("```\n")

    return "\n".join(lines)


#
# Slicey
#

class Slicey(ScriptedLoadableModule):
    """Uses ScriptedLoadableModule base class, available at:
    https://github.com/Slicer/Slicer/blob/main/Base/Python/slicer/ScriptedLoadableModule.py
    """

    def __init__(self, parent):
        ScriptedLoadableModule.__init__(self, parent)
        self.parent.title = "Slicey"
        self.parent.categories = ["Developer Tools"]
        self.parent.dependencies = []
        self.parent.contributors = ["Andras Lasso (Queen's University)"]
        self.parent.helpText = """
An AI chat assistant embedded in Slicer that helps you develop and use Slicer extensions.
Share folders for it to read/write, and let it run Python code in this Slicer instance or in a
separate sandboxed Slicer instance. It can use the Claude API (API key), or a local agent:
Claude Code on your Claude subscription, Codex on your ChatGPT subscription or with an OpenAI
API key, or your own model on an Anthropic-compatible server (e.g. vLLM).
"""
        self.parent.helpText += self.getDefaultModuleDocumentationLink()
        self.parent.acknowledgementText = """
This module sends your messages and the contents of files you choose to share to the
chosen LLM provider (Anthropic, or OpenAI for Codex, or your own server). By default (Auto
approval mode) code execution and file writes that a check finds risky require confirmation.
"""


#
# SliceyLogic
#

class SliceyLogic(ScriptedLoadableModuleLogic):
    """Owns the conversation state and the Claude tool-use loop. Network calls run on
    background threads; a QTimer polls for results on the main thread, where any tool
    execution that touches Slicer/Qt/MRML objects also happens.

    With a local-agent backend (Settings.getBackend() != "claude-api") the agent (Claude Code
    or Codex) runs the tool-use loop itself, on AgentBackends.AsyncRunner's thread; its tool
    calls come through the same result queue and are confirmed and dispatched here.

    UI is driven through two hooks the widget sets:
      - onEvent(eventType, payload): notified of conversation events (see _emit calls below)
      - confirmCallback(name, toolInput, reason) -> bool: asked to approve tool calls that the
        approval mode (Settings.getApprovalMode) does not let run on their own
    """

    CONFIRMATION_REQUIRED_TOOLS = ("run_python_in_slicer", "write_text_file")
    # Most of the earlier conversation passed to an agent session that starts mid-chat.
    MAX_HISTORY_CHARS = 200_000

    def __init__(self):
        ScriptedLoadableModuleLogic.__init__(self)
        self.messages = []
        self._preamble = ""
        self.chatLogPath = None
        self._chatStartedAt = None
        self.onEvent = None
        self.confirmCallback = None

        self._client = None
        self._busy = False
        self._cancelRequested = False

        # Session usage: resets when the user clears the chat.
        self.sessionInputTokens = 0
        self.sessionOutputTokens = 0
        self.sessionCostUsd = 0.0
        self.sessionCostEstimateIncomplete = False

        # All-time usage: persisted in Slicer settings, survives Slicer restarts,
        # only reset by the user explicitly clicking "Reset total".
        allTime = Settings.getAllTimeUsage()
        self.allTimeInputTokens = allTime.get("inputTokens", 0)
        self.allTimeOutputTokens = allTime.get("outputTokens", 0)
        self.allTimeCostUsd = allTime.get("costUsd", 0.0)
        self.allTimeCostEstimateIncomplete = allTime.get("costEstimateIncomplete", False)

        self._resultQueue = queue.Queue()
        self._pollTimer = qt.QTimer()
        self._pollTimer.setInterval(100)
        self._pollTimer.timeout.connect(self._pollQueue)

        self._pendingBlocks = []
        self._pendingResults = {}
        self._pendingAsyncCount = 0

        self._agentRunner = None  # AgentBackends.AsyncRunner, created on first use
        self._agentSession = None
        self._agentConfig = None  # (backend, model, effort) the session was started with
        self._agentContext = None  # ClaudeClient.buildContextText() the agent last got
        # Bumped whenever the session is replaced, so events of an old session are ignored.
        self._agentGeneration = 0

    def cleanup(self):
        self._pollTimer.stop()
        if self._agentSession is not None:
            try:
                self.agentRunner.submit(self._agentSession.close()).result(10)
            except Exception as e:
                logger.warning(f"Slicey: could not close the agent session: {e}")
            self._agentSession = None
        if self._agentRunner is not None:
            self._agentRunner.stop()
            self._agentRunner = None
        PythonExecutor.stopCompanionInstance()

    @property
    def agentRunner(self):
        if self._agentRunner is None:
            from SliceyLib import AgentBackends

            self._agentRunner = AgentBackends.AsyncRunner()
        return self._agentRunner

    def isBusy(self):
        return self._busy

    def resetConversation(self):
        self.messages = []
        self._preamble = ""
        # A new chat gets a new log file, named from the timestamp of its first message.
        self.chatLogPath = None
        self._setCurrentChat(None)
        if self._agentSession is not None:
            self.closeAgentSession()
            if self._busy:  # the old session's end of turn is ignored now
                self._finishTurn()

    def closeAgentSession(self):
        """Ends the local agent's conversation; the next message starts a new one."""
        self._agentGeneration += 1
        if self._agentSession is not None:
            session, self._agentSession = self._agentSession, None
            self.agentRunner.submit(session.close())

    def _appendMessage(self, message):
        """The single place messages are added to the conversation, so the on-disk chat log
        (Settings.getChatLogFolder()/Slicey-<timestamp>.md) is always kept in sync - updated
        immediately on every user message, assistant reply, and tool call/result, not just
        when a chat starts or ends."""
        self.messages.append(message)
        self._ensureChatLogPath()
        self._writeChatLog()

    def _ensureChatLogPath(self):
        if self.chatLogPath:
            return
        folder = Settings.getChatLogFolder()
        try:
            os.makedirs(folder, exist_ok=True)
        except OSError as e:
            logger.warning(f"Slicey: could not create chat log folder {folder}: {e}")
            return
        now = datetime.datetime.now()
        self._chatStartedAt = now
        self.chatLogPath = os.path.join(folder, f"Slicey-{now.strftime('%Y%m%d-%H%M%S')}.md")
        self._setCurrentChat(self.chatLogPath)

    def _writeChatLog(self):
        """Writes the transcript (.md) and, so that the chat can be continued, the message list (.json)."""
        if not self.chatLogPath:
            return
        from SliceyLib import ChatHistory

        title = f"# Slicey chat - {self._chatStartedAt.strftime('%Y-%m-%d %H:%M:%S')}\n"
        try:
            with open(self.chatLogPath, "w", encoding="utf-8") as f:
                f.write(title + "\n" + self._preamble + _renderMarkdownTranscript(self.messages))
            ChatHistory.saveMessages(self.chatLogPath, self.messages, self._preamble)
        except (OSError, TypeError, ValueError) as e:
            logger.warning(f"Slicey: could not write chat log to {self.chatLogPath}: {e}")

    def _setCurrentChat(self, path):
        from SliceyLib import ChatHistory

        ChatHistory.currentChatPath = path

    def loadChat(self, path):
        """Continues the saved chat at `path` (its .md transcript): restores its messages, or,
        for a chat saved without them, keeps its transcript as the start of the conversation.
        New messages are added to the same chat log."""
        from SliceyLib import ChatHistory

        self.resetConversation()
        messages = ChatHistory.loadMessages(path)
        if messages is None:
            transcript = ChatHistory.readTranscript(path)
            # Without its "# Slicey chat - <time>" title line, which _writeChatLog adds again.
            self._preamble = transcript.split("\n", 2)[2] if transcript.startswith("# ") else transcript
            if self._preamble and not self._preamble.endswith("\n"):
                self._preamble += "\n"
        else:
            self._preamble = ChatHistory.loadPreamble(path)
            self.messages = messages
        self.chatLogPath = path
        self._chatStartedAt = ChatHistory.startedAt(path) or datetime.datetime.now()
        self._setCurrentChat(path)

    @property
    def preamble(self):
        """Transcript of the start of a continued chat that was saved without its messages."""
        return self._preamble

    def _earlierConversationText(self):
        """The conversation before the latest user message, as a transcript, for an agent session
        that starts in the middle of a chat (continued chat, or changed model)."""
        text = self._preamble + _renderMarkdownTranscript(self.messages[:-1])
        if len(text) > self.MAX_HISTORY_CHARS:
            text = "[... the start of the conversation is left out ...]\n" + text[-self.MAX_HISTORY_CHARS:]
        return text.strip()

    def resetSessionUsage(self):
        self.sessionInputTokens = 0
        self.sessionOutputTokens = 0
        self.sessionCostUsd = 0.0
        self.sessionCostEstimateIncomplete = False
        self._emitUsage()

    def resetAllTimeUsage(self):
        self.allTimeInputTokens = 0
        self.allTimeOutputTokens = 0
        self.allTimeCostUsd = 0.0
        self.allTimeCostEstimateIncomplete = False
        self._persistAllTimeUsage()
        self._emitUsage()

    def _persistAllTimeUsage(self):
        Settings.setAllTimeUsage({
            "inputTokens": self.allTimeInputTokens,
            "outputTokens": self.allTimeOutputTokens,
            "costUsd": self.allTimeCostUsd,
            "costEstimateIncomplete": self.allTimeCostEstimateIncomplete,
        })

    def _emitUsage(self):
        self._emit("usage_updated", {
            "session": {
                "inputTokens": self.sessionInputTokens,
                "outputTokens": self.sessionOutputTokens,
                "costUsd": self.sessionCostUsd,
                "costEstimateIncomplete": self.sessionCostEstimateIncomplete,
            },
            "allTime": {
                "inputTokens": self.allTimeInputTokens,
                "outputTokens": self.allTimeOutputTokens,
                "costUsd": self.allTimeCostUsd,
                "costEstimateIncomplete": self.allTimeCostEstimateIncomplete,
            },
        })

    def cancel(self):
        self._cancelRequested = True
        if self._busy and self._agentSession is not None:
            self.agentRunner.submit(self._agentSession.interrupt())

    def pausePolling(self):
        """Stops the result-queue poll timer while a (blocking) confirmation prompt is shown,
        so it can't reenter _pollQueue while we're already in the middle of processing tool
        calls for the current response."""
        self._pollTimer.stop()

    def resumePolling(self):
        if self._busy and not self._pollTimer.isActive():
            self._pollTimer.start()

    def invalidateClient(self):
        self._client = None

    def getClient(self):
        apiKey = Settings.getApiKey()
        if not apiKey:
            raise RuntimeError("No Claude API key configured yet. Use the Connection panel above.")
        if self._client is None:
            self._client = ClaudeClient.createClient(apiKey)
        return self._client

    def sendUserMessage(self, text):
        if self._busy:
            return
        PythonExecutor.markNewPrompt()
        self._appendMessage({"role": "user", "content": text})
        self._cancelRequested = False
        self._busy = True
        _gilYielder.acquire()  # the request, the agent and streaming run on Python threads
        self._emit("turn_started", None)
        if Settings.getBackend() == "claude-api":
            self._startClaudeTurn()
        else:
            self._startAgentTurn(text)

    def _startClaudeTurn(self):
        self._repairDanglingToolUse()
        try:
            client = self.getClient()
            model = Settings.getModel()
            systemPrompt = ClaudeClient.buildSystemPrompt()
            tools = ClaudeClient.activeTools()
            messagesSnapshot = list(self.messages)
            if self._preamble:
                # A continued chat saved without its messages: its transcript starts the first user message.
                first = next(i for i, m in enumerate(messagesSnapshot)
                             if m["role"] == "user" and isinstance(m["content"], str))
                messagesSnapshot[first] = {"role": "user", "content": (
                    f"[Earlier part of this conversation (Slicey chat transcript):]\n{self._preamble}\n"
                    f"[The conversation continues:]\n{messagesSnapshot[first]['content']}")}
        except Exception as e:
            self._emit("error", str(e))
            self._finishTurn()
            return

        def worker():
            try:
                response = ClaudeClient.sendMessage(client, model, messagesSnapshot, systemPrompt, tools,
                                                    onDelta=lambda text: self._resultQueue.put(("claude_delta", text)))
                self._resultQueue.put(("claude_response", response, model))
            except Exception as e:
                self._resultQueue.put(("claude_error", e))

        threading.Thread(target=worker, daemon=True).start()
        if not self._pollTimer.isActive():
            self._pollTimer.start()

    def _startAgentTurn(self, text):
        backend = Settings.getBackend()
        config = (backend, Settings.getBackendModel(backend), Settings.getEffort(), Settings.getPastChatsAccess())
        context = ClaudeClient.buildContextText()
        message = text
        try:
            if self._agentSession is not None and self._agentConfig != config:
                self.closeAgentSession()
                self._emit("notice", "Started a new agent session for the changed agent settings; "
                                     "the earlier messages of this chat are passed to it.")
            if self._agentSession is None:
                earlier = self._earlierConversationText()
                if earlier:
                    message = (f"[Earlier part of this conversation (Slicey chat transcript):]\n{earlier}\n\n"
                               f"[The conversation continues:]\n{text}")
                generation = self._agentGeneration

                def onEvent(kind, payload):  # agent thread
                    self._resultQueue.put(("agent_event", generation, kind, payload))

                async def callTool(name, toolInput):  # agent thread
                    future = concurrent.futures.Future()
                    self._resultQueue.put(("agent_tool_call", generation, name, toolInput, future))
                    return await asyncio.wrap_future(future)

                from SliceyLib import AgentBackends

                self._agentSession = AgentBackends.createSession(
                    backend, ClaudeClient.buildSystemPrompt(), ClaudeClient.activeTools(), callTool, onEvent)
                self._agentConfig = config
            elif context != self._agentContext:
                # The agent keeps the system prompt it started with: tell it what changed.
                message = f"[Slicey's settings have changed. Current context:\n{context}]\n\n{text}"
            self._agentContext = context
        except Exception as e:
            logger.exception("Slicey: could not start the agent")
            self._emit("error", str(e))
            self._finishTurn()
            return

        session, generation = self._agentSession, self._agentGeneration

        async def run():
            try:
                await session.send(message)
            except Exception as e:
                logger.exception("Slicey: agent request failed")
                self._resultQueue.put(("agent_event", generation, "error", f"{type(e).__name__}: {e}"))
                self._resultQueue.put(("agent_event", generation, "done", {"isError": True}))

        self.agentRunner.submit(run())
        if not self._pollTimer.isActive():
            self._pollTimer.start()

    def _handleAgentToolCall(self, generation, name, toolInput, future):
        if generation != self._agentGeneration or self._cancelRequested:
            future.set_result({"error": "Cancelled by the user before this tool call ran."})
            return
        # The agent has its own ids; this one links the call and its result in the chat and log.
        blockId = "agent_" + uuid.uuid4().hex
        self._appendMessage({"role": "assistant", "content": [
            {"type": "tool_use", "id": blockId, "name": name, "input": toolInput}]})
        self._emit("tool_started", (blockId, name, toolInput))

        if not self._isApproved(name, toolInput):
            self._finishAgentToolCall(blockId, {"error": "The user rejected this action; it was not executed."}, future)
            return

        if ClaudeClient.requiresMainThread(name, toolInput):
            self._finishAgentToolCall(blockId, ClaudeClient.dispatchTool(name, toolInput), future)
        else:
            def worker():
                result = ClaudeClient.dispatchTool(name, toolInput)
                self._resultQueue.put(("agent_tool_result", blockId, result, future))

            threading.Thread(target=worker, daemon=True).start()

    def _finishAgentToolCall(self, blockId, result, future):
        self._appendMessage({"role": "user", "content": [
            {"type": "tool_result", "tool_use_id": blockId, "content": json.dumps(result)}]})
        self._emit("tool_result", (blockId, result))
        if not future.done():
            future.set_result(result)

    def _handleAgentEvent(self, kind, payload):
        if kind == "text":
            self._appendMessage({"role": "assistant", "content": [{"type": "text", "text": payload}]})
            self._emit("assistant_text", payload)
        elif kind == "error":
            self._emit("error", payload)
        elif kind == "done":
            self._recordAgentUsage(payload)
            self._finishTurn()

    def _repairDanglingToolUse(self):
        """Defensive self-heal: if the conversation history ends with an assistant message
        containing tool_use blocks with no matching tool_result - a bug, or a turn that got
        interrupted in a previous session - every future request 400s on that history
        forever. Patch it up automatically instead of leaving the conversation permanently
        stuck (the user would otherwise have to notice and click Clear chat)."""
        if not self.messages:
            return
        last = self.messages[-1]
        if last.get("role") != "assistant" or not isinstance(last.get("content"), list):
            return
        toolBlocks = [b for b in last["content"] if isinstance(b, dict) and b.get("type") == "tool_use"]
        if not toolBlocks:
            return
        self._appendMessage({
            "role": "user",
            "content": [
                {
                    "type": "tool_result",
                    "tool_use_id": block["id"],
                    "content": json.dumps({"error": "No result was recorded for this tool call; treat it as failed."}),
                    "is_error": True,
                }
                for block in toolBlocks
            ],
        })

    def _finishTurn(self):
        if self._busy:
            _gilYielder.release()
        self._busy = False
        self._pollTimer.stop()
        self._emit("turn_finished", None)

    def _pollQueue(self):
        # All pieces of streamed reply text waiting are shown at once; other items one per call.
        deltas = []
        item = None
        while item is None:
            try:
                queued = self._resultQueue.get_nowait()
            except queue.Empty:
                break
            if queued[0] == "claude_delta":
                deltas.append(queued[1])
            elif queued[0] == "agent_event" and queued[2] == "delta":
                if queued[1] == self._agentGeneration:
                    deltas.append(queued[3])
            else:
                item = queued
        if deltas and not self._cancelRequested:
            self._emit("assistant_delta", "".join(deltas))
        if item is None:
            return

        kind = item[0]
        if kind == "agent_event":
            _, generation, eventKind, payload = item
            if generation == self._agentGeneration:
                self._handleAgentEvent(eventKind, payload)
        elif kind == "agent_tool_call":
            self._handleAgentToolCall(*item[1:])
        elif kind == "agent_tool_result":
            self._finishAgentToolCall(*item[1:])
        elif kind == "claude_error":
            self._emit("error", str(item[1]))
            self._finishTurn()
        elif kind == "claude_response":
            self._handleClaudeResponse(item[1], item[2])
        elif kind == "tool_result":
            _, blockId, result = item
            self._pendingResults[blockId] = result
            self._pendingAsyncCount -= 1
            self._emit("tool_result", (blockId, result))
            if self._pendingAsyncCount <= 0:
                self._finishToolBatch()

    def _handleClaudeResponse(self, response, model):
        self._recordUsage(response, model)

        blocks = [_contentBlockToDict(b) for b in response.content]
        self._appendMessage({"role": "assistant", "content": blocks})

        textParts = [b["text"] for b in blocks if b["type"] == "text"]
        if textParts:
            self._emit("assistant_text", "\n".join(textParts))

        toolBlocks = [b for b in blocks if b["type"] == "tool_use"]
        if not toolBlocks:
            self._finishTurn()
            return

        if self._cancelRequested:
            # The assistant message with these tool_use blocks is already in self.messages
            # (appended above). Anthropic requires a matching tool_result for every tool_use
            # in the *next* message no matter what, even though we're not going to run these
            # or continue the loop - otherwise every future request 400s on this history.
            self._appendMessage({"role": "user", "content": _cancelledToolResults(toolBlocks)})
            self._finishTurn()
            return

        self._pendingBlocks = toolBlocks
        self._pendingResults = {}
        self._pendingAsyncCount = 0

        for block in toolBlocks:
            blockId, name, toolInput = block["id"], block["name"], block["input"]
            self._emit("tool_started", (blockId, name, toolInput))

            if not self._isApproved(name, toolInput):
                result = {"error": "The user rejected this action; it was not executed."}
                self._pendingResults[blockId] = result
                self._emit("tool_result", (blockId, result))
                continue

            if ClaudeClient.requiresMainThread(name, toolInput):
                result = ClaudeClient.dispatchTool(name, toolInput)
                self._pendingResults[blockId] = result
                self._emit("tool_result", (blockId, result))
            else:
                self._pendingAsyncCount += 1
                self._dispatchToolAsync(blockId, name, toolInput)

        if self._pendingAsyncCount <= 0:
            self._finishToolBatch()

    def _recordUsage(self, response, model):
        """Reads the per-call token usage Anthropic returns with every Messages API response
        (no extra network call needed) and accumulates it, and an estimated USD cost, into
        both the session counter (resets on Clear chat) and the persisted all-time counter
        (resets only via "Reset total"). Cost is computed per-turn using the model active
        for that turn, so it stays accurate even if the user switches models mid-session."""
        usage = getattr(response, "usage", None)
        if usage is None:
            return
        inputTokens = getattr(usage, "input_tokens", 0) or 0
        outputTokens = getattr(usage, "output_tokens", 0) or 0

        cost = Settings.estimateCostUsd(model, inputTokens, outputTokens)
        self._addUsage(inputTokens, outputTokens, cost or 0.0, cost is None)

    def _recordAgentUsage(self, info):
        """Token counts of a local agent's request. A subscription or an own server is not
        billed per token; Codex with an OpenAI API key is, but Slicey has no price list for it."""
        costUnknown = Settings.getBackend() == "codex-api"
        self._addUsage(info.get("inputTokens") or 0, info.get("outputTokens") or 0, 0.0, costUnknown)

    def _addUsage(self, inputTokens, outputTokens, cost, costUnknown):
        self.sessionInputTokens += inputTokens
        self.sessionOutputTokens += outputTokens
        self.sessionCostUsd += cost
        self.allTimeInputTokens += inputTokens
        self.allTimeOutputTokens += outputTokens
        self.allTimeCostUsd += cost
        if costUnknown:
            self.sessionCostEstimateIncomplete = True
            self.allTimeCostEstimateIncomplete = True

        self._persistAllTimeUsage()
        self._emitUsage()

    def _isApproved(self, name, toolInput):
        """Asks the user (confirmCallback) if the approval mode requires it for this tool call."""
        reason = self.approvalReason(name, toolInput)
        if reason is None or self.confirmCallback is None:
            return True
        return self.confirmCallback(name, toolInput, reason)

    def approvalReason(self, name, toolInput):
        """None if the tool call may run without asking, else why the user is asked ("" in the
        "ask" mode, which needs no reason)."""
        if name not in self.CONFIRMATION_REQUIRED_TOOLS:
            return None
        mode = Settings.getApprovalMode()
        if mode == "accept":
            return None
        if mode == "auto":
            from SliceyLib import RiskCheck

            return RiskCheck.assess(name, toolInput)
        return ""

    def _dispatchToolAsync(self, blockId, name, toolInput):
        def worker():
            result = ClaudeClient.dispatchTool(name, toolInput)
            self._resultQueue.put(("tool_result", blockId, result))

        threading.Thread(target=worker, daemon=True).start()

    def _finishToolBatch(self):
        # Always append a tool_result for every pending block first - the assistant message
        # with these tool_use blocks is already in self.messages, so Anthropic requires a
        # matching tool_result regardless of whether we're about to stop here (cancelled) or
        # continue the loop.
        content = [
            {
                "type": "tool_result",
                "tool_use_id": block["id"],
                "content": json.dumps(self._pendingResults.get(block["id"], {"error": "no result"})),
            }
            for block in self._pendingBlocks
        ]
        self._appendMessage({"role": "user", "content": content})

        if self._cancelRequested:
            self._finishTurn()
            return
        self._startClaudeTurn()

    def _emit(self, eventType, payload):
        if self.onEvent:
            self.onEvent(eventType, payload)


#
# Event filter so Enter sends the chat message and Shift+Enter inserts a newline. Used
# instead of subclassing QPlainTextEdit because the input box now comes from the .ui file
# as a plain QPlainTextEdit, which can't be promoted to a Python subclass at load time.
# (PythonQt does support subclassing QObject and overriding eventFilter, the same way it
# supports subclassing QWidget classes and overriding keyPressEvent.)
#

class _EnterKeySendFilter(qt.QObject):
    def __init__(self, sendCallback, parent=None):
        qt.QObject.__init__(self, parent)
        self._sendCallback = sendCallback

    def eventFilter(self, obj, event):
        if event.type() == qt.QEvent.KeyPress:
            if event.key() in (qt.Qt.Key_Return, qt.Qt.Key_Enter) and not (event.modifiers() & qt.Qt.ShiftModifier):
                self._sendCallback()
                return True
        return False


#
# SliceyWidget
#

class SliceyWidget(ScriptedLoadableModuleWidget):
    """Uses ScriptedLoadableModuleWidget base class, available at:
    https://github.com/Slicer/Slicer/blob/main/Base/Python/slicer/ScriptedLoadableModule.py
    """

    def __init__(self, parent=None):
        ScriptedLoadableModuleWidget.__init__(self, parent)
        self.logic = SliceyLogic()
        self._toolNames = {}
        self._confirmLoop = None
        self._confirmResult = False
        self._confirmPending = None  # (name, toolInput) of the action waiting for approval
        self._listingApiModels = False
        self._statusWidget = None  # in the status bar while Slicey works and another module is shown
        self._isEntered = False
        # While Slicey works: a spinner and the elapsed time on the Send button, and what it is
        # doing above the prompt box.
        self._activity = ""
        self._turnStartedAt = None
        self._spinnerFrame = 0
        self._busyTimer = qt.QTimer()
        self._busyTimer.setInterval(250)
        self._busyTimer.timeout.connect(self._updateBusyIndicator)
        # The reply text streaming in: where it starts in the chat view (None: not streaming).
        self._streamStart = None
        self._streamBlockStart = None
        self._streamText = ""

    def setup(self):
        ScriptedLoadableModuleWidget.setup(self)

        uiWidget = slicer.util.loadUI(self.resourcePath('UI/Slicey.ui'))
        self.layout.addWidget(uiWidget)
        self.ui = slicer.util.childWidgetVariables(uiWidget)

        self.logic.onEvent = self._onLogicEvent
        self.logic.confirmCallback = self._confirmToolCall

        self._wireConnectionSection()
        self._wireSettingsSection()
        self._wireExecutionSection()
        self._wireChatSection()

        self._updateConnectionStatus()
        self._refreshFoldersTable()

        # If Slicey is already connected when the user first opens the module, there's
        # nothing to set up - start with the Connection section out of the way.
        if self._isConnected():
            self.ui.connectionCollapsibleButton.collapsed = True
        self._updateConnectionSectionTitle()

    def cleanup(self):
        if self._confirmLoop is not None:
            self._confirmLoop.quit()
        self._busyTimer.stop()
        self._removeStatusWidget()
        self.logic.cleanup()

    def enter(self):
        self._isEntered = True
        self._removeStatusWidget()

    def exit(self):
        self._isEntered = False
        if self.logic.isBusy():
            self._showStatus()

    # ---------------------------------------------------------------- Status bar (while away)

    def _showStatus(self):
        """Shows in the status bar what Slicey is doing, while another module is shown."""
        if self._isEntered:
            return
        if self._confirmLoop is not None:
            text = "Slicey: waiting for your approval"
        elif self.logic.isBusy():
            text = "Slicey: working..."
        else:
            text = "Slicey: done"
        if self._statusWidget is None:
            mainWindow = slicer.util.mainWindow()
            if mainWindow is None:
                return
            self._statusWidget = qt.QWidget()
            layout = qt.QHBoxLayout(self._statusWidget)
            layout.setContentsMargins(0, 0, 0, 0)
            self._statusLabel = qt.QLabel()
            layout.addWidget(self._statusLabel)
            button = qt.QToolButton()
            button.text = "Go to Slicey"
            button.clicked.connect(lambda: slicer.util.selectModule("Slicey"))
            layout.addWidget(button)
            # Before Slicer's own permanent widgets: left of the error log button.
            mainWindow.statusBar().insertPermanentWidget(0, self._statusWidget)
        self._statusLabel.text = text
        self._statusLabel.styleSheet = "font-weight: bold;" if self._confirmLoop is not None else ""

    def _removeStatusWidget(self):
        if self._statusWidget is None:
            return
        mainWindow = slicer.util.mainWindow()
        if mainWindow is not None:
            mainWindow.statusBar().removeWidget(self._statusWidget)
        self._statusWidget.deleteLater()
        self._statusWidget = None

    # ---------------------------------------------------------------- Connection panel

    def _wireConnectionSection(self):
        self.ui.connectButton.clicked.connect(self.onConnectClicked)
        self.ui.disconnectButton.clicked.connect(self.onDisconnectClicked)
        self.ui.viewUsageButton.clicked.connect(self.onViewUsageClicked)
        self.ui.saveKeyButton.clicked.connect(self.onSaveKeyClicked)
        self.ui.resetSessionUsageButton.clicked.connect(self.onResetSessionUsageClicked)
        self.ui.resetTotalUsageButton.clicked.connect(self.onResetTotalUsageClicked)
        # Collapsing/expanding the section changes whether its title should carry the
        # compact status/usage summary - see _updateConnectionSectionTitle().
        self.ui.connectionCollapsibleButton.clicked.connect(self.onConnectionSectionToggled)

        for name, label in Settings.BACKENDS:
            self.ui.backendComboBox.addItem(label, name)
        self.ui.backendComboBox.currentIndex = max(0, self.ui.backendComboBox.findData(Settings.getBackend()))
        self.ui.backendComboBox.currentIndexChanged.connect(self.onBackendChanged)

        self.ui.llmServerUrlLineEdit.text = Settings.getLlmServerUrl()
        self.ui.llmServerUrlLineEdit.editingFinished.connect(self.onLlmServerUrlChanged)

        self._populateModels()
        self.ui.modelComboBox.currentIndexChanged.connect(self.onModelChanged)

        for effort in Settings.EFFORTS:
            self.ui.effortComboBox.addItem(effort or "(auto)", effort)
        self.ui.effortComboBox.currentIndex = max(0, self.ui.effortComboBox.findData(Settings.getEffort()))
        self.ui.effortComboBox.currentIndexChanged.connect(self.onEffortChanged)

        self._updateSessionUsageLabel({
            "inputTokens": self.logic.sessionInputTokens,
            "outputTokens": self.logic.sessionOutputTokens,
            "costUsd": self.logic.sessionCostUsd,
            "costEstimateIncomplete": self.logic.sessionCostEstimateIncomplete,
        })
        self._updateTotalUsageLabel({
            "inputTokens": self.logic.allTimeInputTokens,
            "outputTokens": self.logic.allTimeOutputTokens,
            "costUsd": self.logic.allTimeCostUsd,
            "costEstimateIncomplete": self.logic.allTimeCostEstimateIncomplete,
        })

    def onConnectionSectionToggled(self):
        self._updateConnectionSectionTitle()

    def onViewUsageClicked(self):
        qt.QDesktopServices.openUrl(qt.QUrl(_USAGE_URLS[Settings.getBackend()]))

    def onResetSessionUsageClicked(self):
        self.logic.resetSessionUsage()

    def onResetTotalUsageClicked(self):
        if not slicer.util.confirmYesNoDisplay(
            "Reset the all-time total usage counter? This cannot be undone.",
            windowTitle="Slicey",
        ):
            return
        self.logic.resetAllTimeUsage()

    def onConnectClicked(self):
        backend = Settings.getBackend()
        if backend in ("claude-api", "codex-api"):
            url = "https://console.anthropic.com/settings/keys" if backend == "claude-api" else \
                "https://platform.openai.com/api-keys"
            qt.QDesktopServices.openUrl(qt.QUrl(url))
            self.ui.apiKeyLineEdit.visible = True
            self.ui.saveKeyButton.visible = True
            self.ui.apiKeyLineEdit.setFocus()
        else:
            self._checkBackend()

    def onSaveKeyClicked(self):
        key = self.ui.apiKeyLineEdit.text.strip()
        if not key:
            return
        if Settings.getBackend() == "codex-api":
            def onChecked(ok):
                if ok:
                    Settings.setApiKey(key, Settings.OPENAI_KEYRING_USERNAME)
                    self.ui.apiKeyLineEdit.text = ""
                    self.ui.apiKeyLineEdit.visible = False
                    self.ui.saveKeyButton.visible = False
                    self._updateConnectionStatus()

            self._checkBackend(key, self.ui.saveKeyButton, onChecked)
            return
        ClaudeClient.ensureAnthropicPackage()
        self.ui.saveKeyButton.enabled = False
        self.ui.saveKeyButton.text = "Validating..."
        _runInBackground(lambda: ClaudeClient.listModels(key), lambda models, error: self._onApiKeyChecked(key, models, error))

    def _onApiKeyChecked(self, key, models, error):
        self.ui.saveKeyButton.enabled = True
        self.ui.saveKeyButton.text = "Save key"
        if error is not None:
            slicer.util.errorDisplay(f"Could not validate this API key:\n{error}")
            return
        ClaudeClient.storeModels(models)
        Settings.setApiKey(key)
        self.logic.invalidateClient()
        self.ui.apiKeyLineEdit.text = ""
        self.ui.apiKeyLineEdit.visible = False
        self.ui.saveKeyButton.visible = False
        self._populateModels()
        self._updateConnectionStatus()
        slicer.util.infoDisplay(
            "Connected to Claude.\n\n"
            "Every message you send, and every tool call Slicey makes on its behalf "
            "(reading/writing files, running Python), uses the Claude API and incurs "
            "usage costs on your Anthropic account. Use the \"View usage / manage keys\" "
            "button below the model selector to monitor your usage.",
            windowTitle="Slicey",
        )

    def onDisconnectClicked(self):
        backend = Settings.getBackend()
        if backend == "claude-api":
            Settings.clearApiKey()
            self.logic.invalidateClient()
        elif backend == "codex-api":
            Settings.clearApiKey(Settings.OPENAI_KEYRING_USERNAME)
            try:  # Codex's copy of the key
                os.remove(os.path.join(Settings.CODEX_API_HOME, "auth.json"))
            except OSError:
                pass
        elif backend == "server":
            Settings.clearApiKey(Settings.LLM_SERVER_KEYRING_USERNAME)
        Settings.setBackendChecked(backend, False)
        if not self.logic.isBusy():
            self.logic.closeAgentSession()
        self._updateConnectionStatus()

    def onBackendChanged(self, index):
        backend = self.ui.backendComboBox.itemData(index)
        if backend == Settings.getBackend():
            return
        Settings.setBackend(backend)
        self.ui.apiKeyLineEdit.text = ""
        self.ui.apiKeyLineEdit.visible = False
        self.ui.saveKeyButton.visible = False
        self._populateModels()
        self._updateConnectionStatus()
        # The conversation history belongs to the previous LLM: start a new chat.
        if self.logic.messages:
            self._appendNotice(f"Switched to {self.ui.backendComboBox.currentText}; a new chat starts.")
        self.logic.resetConversation()
        self.logic.resetSessionUsage()

    def onLlmServerUrlChanged(self):
        url = self.ui.llmServerUrlLineEdit.text.strip() or Settings.DEFAULT_LLM_SERVER_URL
        if url != Settings.getLlmServerUrl():
            Settings.setLlmServerUrl(url)
            Settings.setBackendChecked("server", False)
            self._updateConnectionStatus()

    def onModelChanged(self, index):
        if index >= 0:
            Settings.setBackendModel(Settings.getBackend(), self.ui.modelComboBox.itemData(index))

    def onEffortChanged(self, index):
        Settings.setEffort(self.ui.effortComboBox.itemData(index))

    def _populateModels(self):
        backend = Settings.getBackend()
        if backend == "claude-api" and not Settings.hasListedModels(backend) and Settings.getApiKey():
            # Saved before the API key check listed the models: list them in the background.
            self._listApiModels()
        combo = self.ui.modelComboBox
        wasBlocked = combo.blockSignals(True)
        combo.clear()
        for model in Settings.getBackendModels(backend):
            combo.addItem(model["label"], model["id"])
            if model["description"]:
                combo.setItemData(combo.count - 1, model["description"], qt.Qt.ToolTipRole)
        current = combo.findData(Settings.getBackendModel(backend))
        if current < 0 and combo.count:
            current = 0
            Settings.setBackendModel(backend, combo.itemData(0))
        combo.currentIndex = current
        combo.enabled = combo.count > 0
        combo.blockSignals(wasBlocked)

    def _listApiModels(self):
        if self._listingApiModels:
            return
        self._listingApiModels = True
        key = Settings.getApiKey()

        def onDone(models, error):
            self._listingApiModels = False
            if error is None:
                ClaudeClient.storeModels(models)
                if Settings.getBackend() == "claude-api":
                    self._populateModels()
            else:
                logger.warning(f"Slicey: could not list the models of the API key: {error}")

        try:
            ClaudeClient.ensureAnthropicPackage()
        except Exception as e:
            onDone(None, e)
            return
        _runInBackground(lambda: ClaudeClient.listModels(key), onDone)

    def _isConnected(self):
        backend = Settings.getBackend()
        if backend == "claude-api":
            return bool(Settings.getApiKey())
        if backend == "codex-api" and not Settings.getApiKey(Settings.OPENAI_KEYRING_USERNAME):
            return False
        return Settings.isBackendChecked(backend)

    def _checkBackend(self, apiKey=None, button=None, onDone=None, quiet=False):
        """Checks the login/key/server of a local-agent backend (installing the Claude Agent SDK
        if needed) in the background and reports the result; then calls onDone(ok). With quiet,
        only a failure is reported."""
        from SliceyLib import AgentBackends

        backend = Settings.getBackend()
        serverUrl = None
        if backend == "server":
            self.onLlmServerUrlChanged()
            serverUrl = Settings.getLlmServerUrl()
            apiKey = self.ui.llmServerKeyLineEdit.text.strip() or \
                Settings.getApiKey(Settings.LLM_SERVER_KEYRING_USERNAME)
        try:
            AgentBackends.prepareCheck(backend)
        except Exception as e:
            slicer.util.errorDisplay(str(e), windowTitle="Slicey")
            if onDone:
                onDone(False)
            return
        button = button or self.ui.connectButton
        text = button.text
        button.enabled = False
        button.text = "Checking..."
        self.ui.backendComboBox.enabled = False
        runner = self.logic.agentRunner

        def finished(result, error):
            button.enabled = True
            button.text = text
            self.ui.backendComboBox.enabled = not self.logic.isBusy()
            ok, message, models = result if error is None else (False, f"{type(error).__name__}: {error}", None)
            Settings.setBackendChecked(backend, ok)
            if models:
                AgentBackends.storeModels(backend, models)
            if ok and backend == "server" and self.ui.llmServerKeyLineEdit.text.strip():
                Settings.setApiKey(apiKey, Settings.LLM_SERVER_KEYRING_USERNAME)
                self.ui.llmServerKeyLineEdit.text = ""
            if backend == Settings.getBackend():
                self._populateModels()
                self._updateConnectionStatus()
            if not ok:
                slicer.util.errorDisplay(message, windowTitle="Slicey")
            elif quiet:
                pass
            elif backend == "codex-api":
                slicer.util.infoDisplay(
                    f"{message}\n\nEvery message you send, and every tool call Slicey makes on its behalf, "
                    "uses the OpenAI API and incurs usage costs on your OpenAI account.", windowTitle="Slicey")
            else:
                slicer.util.infoDisplay(message, windowTitle="Slicey")
            if onDone:
                onDone(ok)

        _runInBackground(lambda: AgentBackends.checkBackend(backend, runner, apiKey, serverUrl), finished)

    def _updateConnectionStatus(self):
        backend = Settings.getBackend()
        if backend == "claude-api":
            key = Settings.getApiKey()
            if key:
                secure = Settings.isApiKeyStoredSecurely()
                suffix = "" if secure else " (key stored without OS-level encryption on this system)"
                self.ui.connectionStatusLabel.text = "Connected" + suffix
            else:
                self.ui.connectionStatusLabel.text = "Not connected"
        elif self._isConnected():
            self.ui.connectionStatusLabel.text = _CONNECTED_TEXT[backend].format(url=Settings.getLlmServerUrl())
        else:
            self.ui.connectionStatusLabel.text = f"Not connected - click \"{_CONNECT_BUTTON_TEXT[backend]}\""

        isServer = backend == "server"
        self.ui.llmServerUrlLabel.visible = isServer
        self.ui.llmServerUrlLineEdit.visible = isServer
        self.ui.llmServerKeyLineEdit.visible = isServer
        self.ui.effortLabel.visible = backend != "claude-api"
        self.ui.effortComboBox.visible = backend != "claude-api"
        self.ui.connectButton.text = _CONNECT_BUTTON_TEXT[backend]
        # Subscriptions are logged in and out with the claude/codex command-line tools.
        self.ui.disconnectButton.visible = backend not in Settings.SUBSCRIPTION_BACKENDS
        self.ui.viewUsageButton.visible = backend in _USAGE_URLS
        self.ui.viewUsageButton.text = "View usage / manage keys..." if backend == "claude-api" else "View usage..."
        self.ui.modelComboBox.toolTip = "" if Settings.hasListedModels(backend) else {
            "claude-api": "Save the API key to list the models it can use",
            "claude": "Click \"Check Claude Code login\" to list the models of your Claude plan",
            "codex": "Click \"Check Codex login\" to list the models of your ChatGPT plan",
            "codex-api": "Save the OpenAI API key to list the models",
            "server": "Click \"Connect to server\" to list the server's models",
        }.get(backend, "")
        self._updateConnectionSectionTitle()

    def _updateConnectionSectionTitle(self):
        """While the Connection section is collapsed, its title carries a compact summary
        (status + usage) so that information stays visible without expanding it."""
        box = self.ui.connectionCollapsibleButton
        if not box.collapsed:
            box.text = "Connection"
            return
        backend = Settings.getBackend()
        status = "Connected" if self._isConnected() else "Not connected"
        if backend in Settings.COST_TRACKED_BACKENDS:
            usage = f"~${self.logic.sessionCostUsd:.4f} session, ~${self.logic.allTimeCostUsd:.4f} total"
        else:
            usage = f"{self.logic.sessionInputTokens + self.logic.sessionOutputTokens:,} tokens session"
        box.text = f"Connection: {self.ui.backendComboBox.currentText}, {status.lower()}. Usage: {usage}."

    def _updateSessionUsageLabel(self, session):
        backend = Settings.getBackend()
        text = f"Session: {session['inputTokens']:,} in / {session['outputTokens']:,} out"
        if backend in Settings.COST_TRACKED_BACKENDS:
            text += f", <b>~${session['costUsd']:.4f}</b>"
            if session["costEstimateIncomplete"]:
                text += " (incl. unrecognized model)"
        elif backend == "codex-api":
            text += " (cost not estimated; see the OpenAI usage page)"
        else:
            text += " (no per-token charges)"
        self.ui.sessionUsageLabel.text = text

    def _updateTotalUsageLabel(self, allTime):
        text = (
            f"Total: {allTime['inputTokens']:,} in / {allTime['outputTokens']:,} out, "
            f"<b>~${allTime['costUsd']:.4f}</b>"
        )
        if allTime["costEstimateIncomplete"]:
            text += " (incl. unrecognized model)"
        self.ui.totalUsageLabel.text = text

    # ---------------------------------------------------------------- Settings panel

    def _wireSettingsSection(self):
        self.ui.foldersTable.horizontalHeader().setSectionResizeMode(0, qt.QHeaderView.Stretch)
        self.ui.foldersTable.verticalHeader().visible = False
        self.ui.addFolderButton.clicked.connect(self.onAddFolderClicked)

        self.ui.customInstructionsTextEdit.plainText = Settings.getCustomSystemPromptText()
        self.ui.customInstructionsTextEdit.textChanged.connect(self.onCustomInstructionsChanged)

        self.ui.chatLogFolderPathLineEdit.currentPath = Settings.getChatLogFolder()
        self.ui.chatLogFolderPathLineEdit.currentPathChanged.connect(self.onChatLogFolderChanged)

        self.ui.pastChatsAccessCheckBox.checked = Settings.getPastChatsAccess()
        self.ui.pastChatsAccessCheckBox.toggled.connect(Settings.setPastChatsAccess)

    def onCustomInstructionsChanged(self):
        Settings.setCustomSystemPromptText(self.ui.customInstructionsTextEdit.plainText)

    def onChatLogFolderChanged(self, path):
        Settings.setChatLogFolder(path)
        self._refreshPastChats()

    def _refreshFoldersTable(self):
        folders = FolderAccess.listSharedFolders()
        self.ui.foldersTable.setRowCount(len(folders))
        for row, folder in enumerate(folders):
            label = folder["path"] + ("" if folder["exists"] else "  [missing]")
            pathItem = qt.QTableWidgetItem(label)
            pathItem.setFlags(pathItem.flags() & ~qt.Qt.ItemIsEditable)
            self.ui.foldersTable.setItem(row, 0, pathItem)

            writableCheck = qt.QCheckBox()
            writableCheck.checked = folder["writable"]
            writableCheck.toggled.connect(lambda checked, p=folder["path"]: self.onFolderWritableToggled(p, checked))
            cellWidget = qt.QWidget()
            cellLayout = qt.QHBoxLayout(cellWidget)
            cellLayout.setContentsMargins(0, 0, 0, 0)
            cellLayout.setAlignment(qt.Qt.AlignCenter)
            cellLayout.addWidget(writableCheck)
            self.ui.foldersTable.setCellWidget(row, 1, cellWidget)

            removeButton = qt.QPushButton("Remove")
            removeButton.clicked.connect(lambda checked=False, p=folder["path"]: self.onRemoveFolderClicked(p))
            self.ui.foldersTable.setCellWidget(row, 2, removeButton)

    def onAddFolderClicked(self):
        directory = qt.QFileDialog.getExistingDirectory(self.parent, "Select folder to share with Slicey")
        if not directory:
            return
        FolderAccess.addSharedFolder(directory, writable=False)
        self._refreshFoldersTable()

    def onFolderWritableToggled(self, path, checked):
        FolderAccess.addSharedFolder(path, writable=checked)
        self._refreshFoldersTable()

    def onRemoveFolderClicked(self, path):
        FolderAccess.removeSharedFolder(path)
        self._refreshFoldersTable()

    # ---------------------------------------------------------------- Execution panel

    def _wireExecutionSection(self):
        if Settings.getExecutionTarget() == "new_instance":
            self.ui.newInstanceRadio.checked = True
        else:
            self.ui.currentRadio.checked = True
        self.ui.currentRadio.toggled.connect(self.onExecutionTargetChanged)
        self.ui.stopInstanceButton.clicked.connect(self.onStopInstanceClicked)

    def onExecutionTargetChanged(self, checked):
        Settings.setExecutionTarget("current" if self.ui.currentRadio.checked else "new_instance")

    def onStopInstanceClicked(self):
        PythonExecutor.stopCompanionInstance()

    # ---------------------------------------------------------------- Chat panel

    def _wireChatSection(self):
        # Wrap at the widget width, breaking even long unbroken tokens (paths, hashes, ...)
        # if needed, so nothing ever forces horizontal scrolling. (lineWrapMode/wordWrapMode
        # and the Enter-to-send filter aren't expressible as static .ui properties tied to
        # a Python callback, so they're wired up here instead.)
        self._enterKeySendFilter = _EnterKeySendFilter(self.onSendClicked, self.ui.inputEdit)
        self.ui.inputEdit.installEventFilter(self._enterKeySendFilter)

        self.ui.inputEdit.setStyleSheet(_PROMPT_STYLE)
        self.ui.sendButton.setStyleSheet(_PRIMARY_BUTTON_STYLE)
        self.ui.sendButton.clicked.connect(self.onSendClicked)
        self.ui.stopButton.clicked.connect(self.onStopClicked)
        self.ui.clearButton.clicked.connect(self.onNewChatClicked)
        self._wirePastChatsSection()

        self.ui.approveButton.setStyleSheet(_PRIMARY_BUTTON_STYLE)
        self.ui.approveButton.clicked.connect(self.onApproveClicked)
        self.ui.rejectButton.clicked.connect(self.onRejectClicked)

        self.ui.switchToAutoButton.clicked.connect(self.onSwitchToAutoClicked)

        for mode, label in Settings.APPROVAL_MODES:
            self.ui.approvalModeComboBox.addItem(label, mode)
        self.ui.approvalModeComboBox.currentIndex = self.ui.approvalModeComboBox.findData(Settings.getApprovalMode())
        self.ui.approvalModeComboBox.currentIndexChanged.connect(self.onApprovalModeChanged)

        self.ui.renderMarkdownCheckBox.checked = Settings.getRenderMarkdown()
        self.ui.renderMarkdownCheckBox.toggled.connect(self.onRenderMarkdownToggled)

    def onRenderMarkdownToggled(self, checked):
        Settings.setRenderMarkdown(checked)
        if not self.logic.isBusy():
            self._rerenderChat()

    def _rerenderChat(self):
        """Shows the conversation again (e.g. with or without formatting). Notices and errors,
        which are not part of the conversation, are not shown again."""
        self.ui.chatView.clear()
        self._streamStart = None
        self._toolNames = {}
        if self.logic.preamble:
            self.ui.chatView.append(
                f'<div style="margin:6px 0; color:#555;"><i>Earlier part of this chat (saved transcript):</i>'
                f'<pre style="background:#f7f7f7; padding:4px; {_PRE_WRAP_STYLE}">{_escape(self.logic.preamble)}</pre></div>')
        self._renderMessages(self.logic.messages)

    def onApprovalModeChanged(self, index):
        Settings.setApprovalMode(self.ui.approvalModeComboBox.itemData(index))

    def onSendClicked(self):
        if self.logic.isBusy():
            return
        text = self.ui.inputEdit.plainText.strip()
        if not text:
            return
        if not self._isConnected():
            if Settings.getBackend() in ("claude-api", "codex-api"):
                slicer.util.errorDisplay("Connect first (see the Connection panel above).")
                return
            # A login or server that has not been checked yet: check it now, then send.
            self.ui.sendButton.enabled = False

            def onChecked(ok):
                self.ui.sendButton.enabled = not self.logic.isBusy()
                if ok:
                    self.onSendClicked()

            self._checkBackend(onDone=onChecked, quiet=True)
            return
        self.ui.inputEdit.plainText = ""
        self._appendUser(text)
        self.logic.sendUserMessage(text)

    def onStopClicked(self):
        self.logic.cancel()

    def onNewChatClicked(self):
        self.logic.resetConversation()
        self.logic.resetSessionUsage()
        self.ui.chatView.clear()
        self._streamStart = None
        self._toolNames = {}
        self._refreshPastChats()

    # ---------------------------------------------------------------- Past chats section

    def _wirePastChatsSection(self):
        self._pastChats = []
        self.ui.pastChatsCollapsibleButton.contentsCollapsed.connect(self.onPastChatsToggled)
        self.ui.pastChatsList.currentRowChanged.connect(lambda row: self._updatePastChatsButtons())
        self.ui.pastChatsList.itemDoubleClicked.connect(lambda item: self.onContinueChatClicked())
        self.ui.continueChatButton.clicked.connect(self.onContinueChatClicked)
        self.ui.openTranscriptButton.clicked.connect(self.onOpenTranscriptClicked)
        self._updatePastChatsButtons()

    def onPastChatsToggled(self, collapsed):
        if not collapsed:
            self._refreshPastChats()

    def _refreshPastChats(self):
        """Lists the saved chats (newest first), if the Past chats section is open."""
        if self.ui.pastChatsCollapsibleButton.collapsed:
            return
        from SliceyLib import ChatHistory

        selected = self._selectedPastChat()
        self._pastChats = ChatHistory.listChats()
        chatList = self.ui.pastChatsList
        chatList.clear()
        for chat in self._pastChats:
            current = " (this chat)" if chat["path"] == self.logic.chatLogPath else ""
            item = qt.QListWidgetItem(f"{chat['startedAt']:%Y-%m-%d %H:%M}{current}   {chat['title'] or '(empty)'}")
            item.setToolTip(chat["path"])
            chatList.addItem(item)
        if not self._pastChats:
            chatList.addItem(f"No saved chats in {Settings.getChatLogFolder()}")
        paths = [c["path"] for c in self._pastChats]
        chatList.currentRow = paths.index(selected["path"]) if selected and selected["path"] in paths else -1
        self._updatePastChatsButtons()

    def _selectedPastChat(self):
        row = self.ui.pastChatsList.currentRow
        return self._pastChats[row] if 0 <= row < len(self._pastChats) else None

    def _updatePastChatsButtons(self):
        chat = self._selectedPastChat()
        isCurrent = chat is not None and chat["path"] == self.logic.chatLogPath
        self.ui.continueChatButton.enabled = chat is not None and not isCurrent and not self.logic.isBusy()
        self.ui.continueChatButton.toolTip = "Wait for the current request to finish" if self.logic.isBusy() else ""
        self.ui.openTranscriptButton.enabled = chat is not None

    def onContinueChatClicked(self):
        chat = self._selectedPastChat()
        if chat is None or chat["path"] == self.logic.chatLogPath or self.logic.isBusy():
            return
        self._continueChat(chat)
        self.ui.pastChatsCollapsibleButton.collapsed = True

    def onOpenTranscriptClicked(self):
        chat = self._selectedPastChat()
        if chat is not None:
            qt.QDesktopServices.openUrl(qt.QUrl.fromLocalFile(chat["path"]))

    def _continueChat(self, chat):
        try:
            self.logic.loadChat(chat["path"])
        except (OSError, ValueError) as e:
            slicer.util.errorDisplay(f"Could not open the chat:\n{e}", windowTitle="Slicey")
            return
        self.logic.resetSessionUsage()
        self._rerenderChat()
        self._appendNotice(f"Continuing the chat of {chat['startedAt']:%Y-%m-%d %H:%M}.")
        self.ui.inputEdit.setFocus()

    def _renderMessages(self, messages):
        """Shows a restored conversation the way it was shown while it happened."""
        for message in messages:
            content = message.get("content")
            if isinstance(content, str):
                self._appendUser(content)
                continue
            for block in content or []:
                blockType = block.get("type")
                if blockType == "text" and block.get("text", "").strip():
                    self._appendAssistant(block["text"])
                elif blockType == "tool_use":
                    self._appendToolStarted(block["id"], block["name"], block.get("input") or {})
                elif blockType == "tool_result":
                    try:
                        result = json.loads(block.get("content") or "null")
                    except (TypeError, ValueError):
                        result = block.get("content")
                    self._appendToolResult(block.get("tool_use_id"), result)

    # ---------------------------------------------------------------- Logic event handling

    def _onLogicEvent(self, eventType, payload):
        if eventType == "turn_started":
            self.ui.sendButton.enabled = False
            self.ui.stopButton.enabled = True
            self.ui.backendComboBox.enabled = False
            self._refreshPastChats()  # a new chat is listed from its first message on
            self._turnStartedAt = time.time()
            self._setActivity("Thinking")
            self._busyTimer.start()
        elif eventType == "turn_finished":
            self._streamStart = None  # a reply cut short (Stop, error) stays as it streamed in
            self._busyTimer.stop()
            self._turnStartedAt = None
            self.ui.sendButton.text = "Send"
            self.ui.activityLabel.visible = False
            self.ui.sendButton.enabled = True
            self.ui.stopButton.enabled = False
            self.ui.backendComboBox.enabled = True
            self._updatePastChatsButtons()
            if self._statusWidget is not None:
                self._showStatus()
        elif eventType == "assistant_delta":
            self._appendAssistantDelta(payload)
            self._setActivity("Writing")
        elif eventType == "assistant_text":
            self._appendAssistant(payload)
        elif eventType == "error":
            self._appendError(payload)
        elif eventType == "notice":
            self._appendNotice(payload)
        elif eventType == "usage_updated":
            self._updateSessionUsageLabel(payload["session"])
            self._updateTotalUsageLabel(payload["allTime"])
            self._updateConnectionSectionTitle()
        elif eventType == "tool_started":
            blockId, name, toolInput = payload
            self._appendToolStarted(blockId, name, toolInput)
            self._setActivity(_TOOL_ACTIVITY.get(name, f"Running {name}"))
        elif eventType == "tool_result":
            blockId, result = payload
            self._appendToolResult(blockId, result)
            self._setActivity("Thinking")

    def _setActivity(self, activity):
        if self._turnStartedAt is None:
            return
        self._activity = activity
        self._updateBusyIndicator()
        # Python code run in this Slicer blocks the main thread right after this: show it now.
        self.ui.activityLabel.repaint()
        self.ui.sendButton.repaint()

    def _updateBusyIndicator(self):
        if self._turnStartedAt is None:
            return
        self._spinnerFrame = (self._spinnerFrame + 1) % len(_SPINNER)
        elapsed = int(time.time() - self._turnStartedAt)
        self.ui.sendButton.text = f"{_SPINNER[self._spinnerFrame]} {elapsed} s"
        activity = "Waiting for your approval" if self._confirmLoop is not None else self._activity
        self.ui.activityLabel.text = f"Slicey: {activity}..."
        self.ui.activityLabel.visible = True

    def onApproveClicked(self):
        self._confirmResult = True
        if self._confirmLoop is not None:
            self._confirmLoop.quit()

    def onRejectClicked(self):
        self._confirmResult = False
        if self._confirmLoop is not None:
            self._confirmLoop.quit()

    def onSwitchToAutoClicked(self):
        """Auto mode from now on; the pending action runs if it is not risky, otherwise it stays
        here for approval, with the reason."""
        self.ui.approvalModeComboBox.currentIndex = self.ui.approvalModeComboBox.findData("auto")
        name, toolInput = self._confirmPending
        reason = self.logic.approvalReason(name, toolInput)
        if reason is None:
            self.onApproveClicked()
            return
        self._showConfirmation(name, toolInput, reason)

    def _confirmToolCall(self, name, toolInput, reason):
        self._confirmPending = (name, toolInput)
        self._showConfirmation(name, toolInput, reason)
        self.ui.confirmPanel.visible = True
        # Deferred so it runs after the panel's geometry/layout has actually updated.
        qt.QTimer.singleShot(0, self._onConfirmPanelShown)

        # Pause the logic's result-queue poll timer while we block here, so it can't reenter
        # tool-call handling for the current response while this one is still pending.
        self.logic.pausePolling()
        self._confirmResult = False
        self._confirmLoop = qt.QEventLoop()
        self._showStatus()  # if another module is shown
        self._confirmLoop.exec_()
        self._confirmLoop = None
        self.logic.resumePolling()
        if self._statusWidget is not None:
            self._showStatus()

        self.ui.confirmPanel.visible = False
        self._confirmPending = None
        self.ui.inputEdit.setFocus()
        return self._confirmResult

    def _showConfirmation(self, name, toolInput, reason):
        if name == "run_python_in_slicer":
            detail = toolInput.get("code", "")
            summary = f"Slicey wants to run Python code in Slicer (target={Settings.getExecutionTarget()})."
        else:
            detail = toolInput.get("content", "")
            summary = f"Slicey wants to write to this file: {toolInput.get('path', '')}."
        if reason:
            summary += f" {reason}"
        self.ui.confirmLabel.text = summary + " Approve?"
        self.ui.confirmTextEdit.plainText = detail
        # Already in auto mode: switching would change nothing.
        self.ui.switchToAutoButton.visible = Settings.getApprovalMode() != "auto"

    def _onConfirmPanelShown(self):
        self._scrollModulePanelToBottom()
        self.ui.approveButton.setFocus()

    def _scrollModulePanelToBottom(self):
        """Scrolls the module panel's containing scroll area all the way down so the chat
        transcript and the confirmation panel below it are fully visible."""
        widget = self.parent
        while widget is not None:
            if isinstance(widget, qt.QScrollArea):
                scrollBar = widget.verticalScrollBar()
                scrollBar.setValue(scrollBar.maximum)
                return
            widget = widget.parentWidget()

    # ---------------------------------------------------------------- Chat rendering

    def _appendUser(self, text):
        self.ui.chatView.append(f'<div style="margin:6px 0;"><b>You:</b><br>{_escapeMultiline(text)}</div>')

    def _appendAssistantDelta(self, text):
        """Shows the reply text while it streams in, as plain text; _appendAssistant replaces it
        with the complete text block."""
        chatView = self.ui.chatView
        if self._streamStart is None:
            chatView.append('<div style="margin:6px 0 0 0;"><b>Slicey:</b></div>')
            self._streamBlockStart = chatView.document.lastBlock().position()
            cursor = chatView.textCursor()
            cursor.movePosition(qt.QTextCursor.End)
            # New blocks take over the format of the block before (e.g. a tool result's background).
            cursor.setBlockFormat(qt.QTextBlockFormat())
            cursor.insertBlock(qt.QTextBlockFormat(), qt.QTextCharFormat())
            self._streamStart = cursor.position()
            self._streamText = ""
        self._streamText += text
        cursor = chatView.textCursor()
        cursor.setPosition(self._streamStart)
        cursor.movePosition(qt.QTextCursor.End, qt.QTextCursor.KeepAnchor)
        cursor.setCharFormat(qt.QTextCharFormat())  # not the bold of "Slicey:"
        cursor.insertText(self._streamText)
        scrollBar = chatView.verticalScrollBar()
        scrollBar.setValue(scrollBar.maximum)

    def _removeStreamedText(self):
        if self._streamStart is None:
            return
        cursor = self.ui.chatView.textCursor()
        cursor.setPosition(max(0, self._streamBlockStart - 1))  # with the line break before it
        cursor.movePosition(qt.QTextCursor.End, qt.QTextCursor.KeepAnchor)
        cursor.removeSelectedText()
        self._streamStart = None

    def _appendAssistant(self, text):
        self._removeStreamedText()
        if not Settings.getRenderMarkdown():
            self.ui.chatView.append(f'<div style="margin:6px 0;"><b>Slicey:</b><br>{_escapeMultiline(text)}</div>')
            return
        self.ui.chatView.append('<div style="margin:6px 0 0 0;"><b>Slicey:</b></div>')
        cursor = self.ui.chatView.textCursor()
        cursor.movePosition(qt.QTextCursor.End)
        cursor.insertBlock()
        cursor.insertFragment(_markdownFragment(text))
        scrollBar = self.ui.chatView.verticalScrollBar()
        scrollBar.setValue(scrollBar.maximum)

    def _appendNotice(self, message):
        self.ui.chatView.append(f'<div style="margin:6px 0; color:#555;"><i>{_escapeMultiline(message)}</i></div>')

    def _appendError(self, message):
        self.ui.chatView.append(f'<div style="margin:6px 0; color:#b00020;"><b>Error:</b> {_escapeMultiline(message)}</div>')

    def _appendToolStarted(self, blockId, name, toolInput):
        self._toolNames[blockId] = name
        detail = toolInput.get("code") or toolInput.get("content") or ""
        argsSummary = {k: v for k, v in toolInput.items() if k not in ("code", "content")}
        header = f"Running tool: {_escape(name)}"
        if argsSummary:
            header += f" {_escape(json.dumps(argsSummary))}"
        block = f'<pre style="background:#f0f0f0; padding:4px; {_PRE_WRAP_STYLE}">{_escape(detail)}</pre>' if detail else ""
        self.ui.chatView.append(f'<div style="margin:6px 0; color:#555;"><b>{header}</b>{block}</div>')

    def _appendToolResult(self, blockId, result):
        name = self._toolNames.get(blockId, "tool")
        text = json.dumps(result, indent=2) if isinstance(result, (dict, list)) else str(result)
        if len(text) > 4000:
            text = text[:4000] + "\n... [truncated]"
        self.ui.chatView.append(
            f'<div style="margin:6px 0 12px 0; color:#555;">Result of {_escape(name)}:'
            f'<pre style="background:#f7f7f7; padding:4px; {_PRE_WRAP_STYLE}">{_escape(text)}</pre></div>'
        )


#
# SliceyTest
#

class SliceyTest(ScriptedLoadableModuleTest):
    """Uses ScriptedLoadableModuleTest base class, available at:
    https://github.com/Slicer/Slicer/blob/main/Base/Python/slicer/ScriptedLoadableModule.py
    """

    def setUp(self):
        ScriptedLoadableModuleTest.setUp(self)
        self._savedFolders = Settings.getSharedFolders()

    def tearDown(self):
        Settings.setSharedFolders(self._savedFolders)

    def runTest(self):
        self.setUp()
        self.test_FolderAccessSandboxing()
        self.tearDown()

    def test_FolderAccessSandboxing(self):
        import os
        import shutil
        import tempfile

        tempRoot = tempfile.mkdtemp(prefix="SliceyTest_")
        try:
            Settings.setSharedFolders([{"path": tempRoot, "writable": False}])

            sampleFile = os.path.join(tempRoot, "sample.txt")
            with open(sampleFile, "w") as f:
                f.write("hello")

            result = FolderAccess.readTextFile(sampleFile)
            self.assertEqual(result.get("content"), "hello")

            # Read-only folder: writes must be rejected.
            result = FolderAccess.writeTextFile(sampleFile, "nope")
            self.assertIn("error", result)
            self.assertEqual(open(sampleFile).read(), "hello")

            # Paths outside any shared folder must be rejected.
            outsidePath = os.path.join(tempfile.gettempdir(), "SliceyTestOutsideFile.txt")
            result = FolderAccess.readTextFile(outsidePath)
            self.assertIn("error", result)

            # Marking the folder writable allows writes inside it.
            Settings.setSharedFolders([{"path": tempRoot, "writable": True}])
            result = FolderAccess.writeTextFile(sampleFile, "updated")
            self.assertNotIn("error", result)
            self.assertEqual(open(sampleFile).read(), "updated")

            # Traversal outside the shared root must still be rejected even when writable.
            escapedPath = os.path.join(tempRoot, "..", "SliceyTestEscape.txt")
            result = FolderAccess.writeTextFile(escapedPath, "should not be written")
            self.assertIn("error", result)
            self.assertFalse(os.path.exists(os.path.join(tempfile.gettempdir(), "SliceyTestEscape.txt")))

            self.delayDisplay("FolderAccess sandboxing test passed")
        finally:
            shutil.rmtree(tempRoot, ignore_errors=True)
