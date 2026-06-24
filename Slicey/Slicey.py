import html
import json
import logging
import queue
import threading

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


def _escape(text):
    return html.escape(str(text))


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
An AI chat assistant (Claude) embedded in Slicer that helps you develop and use Slicer
extensions. Share folders for it to read/write, and let it run Python code in this Slicer
instance or in a separate sandboxed Slicer instance.
"""
        self.parent.helpText += self.getDefaultModuleDocumentationLink()
        self.parent.acknowledgementText = """
This module sends your messages and the contents of files you choose to share to the
Anthropic Claude API. Code execution and file writes require confirmation by default.
"""


#
# SliceyLogic
#

class SliceyLogic(ScriptedLoadableModuleLogic):
    """Owns the conversation state and the Claude tool-use loop. Network calls run on
    background threads; a QTimer polls for results on the main thread, where any tool
    execution that touches Slicer/Qt/MRML objects also happens.

    UI is driven through two hooks the widget sets:
      - onEvent(eventType, payload): notified of conversation events (see _emit calls below)
      - confirmCallback(name, toolInput) -> bool: asked to confirm risky tool calls
    """

    CONFIRMATION_REQUIRED_TOOLS = ("run_python_in_slicer", "write_text_file")

    def __init__(self):
        ScriptedLoadableModuleLogic.__init__(self)
        self.messages = []
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

    def cleanup(self):
        self._pollTimer.stop()
        PythonExecutor.stopCompanionInstance()

    def isBusy(self):
        return self._busy

    def resetConversation(self):
        self.messages = []

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
        self.messages.append({"role": "user", "content": text})
        self._cancelRequested = False
        self._busy = True
        self._emit("turn_started", None)
        self._startClaudeTurn()

    def _startClaudeTurn(self):
        try:
            client = self.getClient()
            model = Settings.getModel()
            systemPrompt = ClaudeClient.buildSystemPrompt()
            messagesSnapshot = list(self.messages)
        except Exception as e:
            self._emit("error", str(e))
            self._finishTurn()
            return

        def worker():
            try:
                response = ClaudeClient.sendMessage(client, model, messagesSnapshot, systemPrompt)
                self._resultQueue.put(("claude_response", response, model))
            except Exception as e:
                self._resultQueue.put(("claude_error", e))

        threading.Thread(target=worker, daemon=True).start()
        if not self._pollTimer.isActive():
            self._pollTimer.start()

    def _finishTurn(self):
        self._busy = False
        self._pollTimer.stop()
        self._emit("turn_finished", None)

    def _pollQueue(self):
        try:
            item = self._resultQueue.get_nowait()
        except queue.Empty:
            return

        kind = item[0]
        if kind == "claude_error":
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
        self.messages.append({"role": "assistant", "content": blocks})

        textParts = [b["text"] for b in blocks if b["type"] == "text"]
        if textParts:
            self._emit("assistant_text", "\n".join(textParts))

        toolBlocks = [b for b in blocks if b["type"] == "tool_use"]
        if not toolBlocks or self._cancelRequested:
            self._finishTurn()
            return

        self._pendingBlocks = toolBlocks
        self._pendingResults = {}
        self._pendingAsyncCount = 0

        for block in toolBlocks:
            blockId, name, toolInput = block["id"], block["name"], block["input"]
            self._emit("tool_started", (blockId, name, toolInput))

            if self._needsConfirmation(name) and self.confirmCallback and not self.confirmCallback(name, toolInput):
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
        costUnknown = cost is None
        cost = cost or 0.0

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

    def _needsConfirmation(self, name):
        if not Settings.getRequireConfirmation():
            return False
        return name in self.CONFIRMATION_REQUIRED_TOOLS

    def _dispatchToolAsync(self, blockId, name, toolInput):
        def worker():
            result = ClaudeClient.dispatchTool(name, toolInput)
            self._resultQueue.put(("tool_result", blockId, result))

        threading.Thread(target=worker, daemon=True).start()

    def _finishToolBatch(self):
        if self._cancelRequested:
            self._finishTurn()
            return
        content = [
            {
                "type": "tool_result",
                "tool_use_id": block["id"],
                "content": json.dumps(self._pendingResults.get(block["id"], {"error": "no result"})),
            }
            for block in self._pendingBlocks
        ]
        self.messages.append({"role": "user", "content": content})
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

    def setup(self):
        ScriptedLoadableModuleWidget.setup(self)

        uiWidget = slicer.util.loadUI(self.resourcePath('UI/Slicey.ui'))
        self.layout.addWidget(uiWidget)
        self.ui = slicer.util.childWidgetVariables(uiWidget)

        self.logic.onEvent = self._onLogicEvent
        self.logic.confirmCallback = self._confirmToolCall

        self._wireConnectionSection()
        self._wireFoldersSection()
        self._wireExecutionSection()
        self._wireChatSection()

        self._updateConnectionStatus()
        self._refreshFoldersTable()

    def cleanup(self):
        if self._confirmLoop is not None:
            self._confirmLoop.quit()
        self.logic.cleanup()

    # ---------------------------------------------------------------- Connection panel

    def _wireConnectionSection(self):
        self.ui.connectButton.clicked.connect(self.onConnectClicked)
        self.ui.disconnectButton.clicked.connect(self.onDisconnectClicked)
        self.ui.viewUsageButton.clicked.connect(self.onViewUsageClicked)
        self.ui.saveKeyButton.clicked.connect(self.onSaveKeyClicked)
        self.ui.resetSessionUsageButton.clicked.connect(self.onResetSessionUsageClicked)
        self.ui.resetTotalUsageButton.clicked.connect(self.onResetTotalUsageClicked)

        self.ui.modelComboBox.addItems(Settings.MODEL_PRESETS)
        self.ui.modelComboBox.setCurrentText(Settings.getModel())
        self.ui.modelComboBox.currentTextChanged.connect(self.onModelChanged)

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

    def onViewUsageClicked(self):
        qt.QDesktopServices.openUrl(qt.QUrl("https://platform.claude.com/settings/keys"))

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
        qt.QDesktopServices.openUrl(qt.QUrl("https://console.anthropic.com/settings/keys"))
        self.ui.apiKeyLineEdit.visible = True
        self.ui.saveKeyButton.visible = True
        self.ui.apiKeyLineEdit.setFocus()

    def onSaveKeyClicked(self):
        key = self.ui.apiKeyLineEdit.text.strip()
        if not key:
            return
        self.ui.saveKeyButton.enabled = False
        self.ui.saveKeyButton.text = "Validating..."
        slicer.app.processEvents()
        try:
            ok, message = ClaudeClient.testApiKey(key)
        finally:
            self.ui.saveKeyButton.enabled = True
            self.ui.saveKeyButton.text = "Save key"
        if not ok:
            slicer.util.errorDisplay(f"Could not validate this API key:\n{message}")
            return
        Settings.setApiKey(key)
        self.logic.invalidateClient()
        self.ui.apiKeyLineEdit.text = ""
        self.ui.apiKeyLineEdit.visible = False
        self.ui.saveKeyButton.visible = False
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
        Settings.clearApiKey()
        self.logic.invalidateClient()
        self._updateConnectionStatus()

    def onModelChanged(self, text):
        Settings.setModel(text)

    def _updateConnectionStatus(self):
        key = Settings.getApiKey()
        if key:
            secure = Settings.isApiKeyStoredSecurely()
            suffix = "" if secure else " (key stored without OS-level encryption on this system)"
            self.ui.connectionStatusLabel.text = "Connected" + suffix
        else:
            self.ui.connectionStatusLabel.text = "Not connected"

    def _updateSessionUsageLabel(self, session):
        text = (
            f"Session: {session['inputTokens']:,} in / {session['outputTokens']:,} out, "
            f"<b>~${session['costUsd']:.4f}</b>"
        )
        if session["costEstimateIncomplete"]:
            text += " (incl. unrecognized model)"
        self.ui.sessionUsageLabel.text = text

    def _updateTotalUsageLabel(self, allTime):
        text = (
            f"Total: {allTime['inputTokens']:,} in / {allTime['outputTokens']:,} out, "
            f"<b>~${allTime['costUsd']:.4f}</b>"
        )
        if allTime["costEstimateIncomplete"]:
            text += " (incl. unrecognized model)"
        self.ui.totalUsageLabel.text = text

    # ---------------------------------------------------------------- Shared folders panel

    def _wireFoldersSection(self):
        self.ui.foldersTable.horizontalHeader().setSectionResizeMode(0, qt.QHeaderView.Stretch)
        self.ui.foldersTable.verticalHeader().visible = False
        self.ui.addFolderButton.clicked.connect(self.onAddFolderClicked)

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

        self.ui.sendButton.setStyleSheet(_PRIMARY_BUTTON_STYLE)
        self.ui.sendButton.clicked.connect(self.onSendClicked)
        self.ui.stopButton.clicked.connect(self.onStopClicked)
        self.ui.clearButton.clicked.connect(self.onClearChatClicked)

        self.ui.approveButton.setStyleSheet(_PRIMARY_BUTTON_STYLE)
        self.ui.approveButton.clicked.connect(self.onApproveClicked)
        self.ui.rejectButton.clicked.connect(self.onRejectClicked)

        self.ui.autoAcceptCheckBox.checked = not Settings.getRequireConfirmation()
        self.ui.autoAcceptCheckBox.toggled.connect(self.onAutoAcceptToggled)

    def onAutoAcceptToggled(self, checked):
        Settings.setRequireConfirmation(not checked)

    def onSendClicked(self):
        if self.logic.isBusy():
            return
        text = self.ui.inputEdit.plainText.strip()
        if not text:
            return
        if not Settings.getApiKey():
            slicer.util.errorDisplay("Connect your Claude account first (see the Connection panel above).")
            return
        self.ui.inputEdit.plainText = ""
        self._appendUser(text)
        self.logic.sendUserMessage(text)

    def onStopClicked(self):
        self.logic.cancel()

    def onClearChatClicked(self):
        self.logic.resetConversation()
        self.logic.resetSessionUsage()
        self.ui.chatView.clear()
        self._toolNames = {}

    # ---------------------------------------------------------------- Logic event handling

    def _onLogicEvent(self, eventType, payload):
        if eventType == "turn_started":
            self.ui.sendButton.enabled = False
            self.ui.stopButton.enabled = True
        elif eventType == "turn_finished":
            self.ui.sendButton.enabled = True
            self.ui.stopButton.enabled = False
        elif eventType == "assistant_text":
            self._appendAssistant(payload)
        elif eventType == "error":
            self._appendError(payload)
        elif eventType == "usage_updated":
            self._updateSessionUsageLabel(payload["session"])
            self._updateTotalUsageLabel(payload["allTime"])
        elif eventType == "tool_started":
            blockId, name, toolInput = payload
            self._appendToolStarted(blockId, name, toolInput)
        elif eventType == "tool_result":
            blockId, result = payload
            self._appendToolResult(blockId, result)

    def onApproveClicked(self):
        self._confirmResult = True
        if self._confirmLoop is not None:
            self._confirmLoop.quit()

    def onRejectClicked(self):
        self._confirmResult = False
        if self._confirmLoop is not None:
            self._confirmLoop.quit()

    def _confirmToolCall(self, name, toolInput):
        if name == "run_python_in_slicer":
            detail = toolInput.get("code", "")
            summary = f"Slicey wants to run Python code in Slicer (target={toolInput.get('target', 'current')}). Approve?"
        else:
            detail = toolInput.get("content", "")
            summary = f"Slicey wants to write to this file: {toolInput.get('path', '')}. Approve?"

        self.ui.confirmLabel.text = summary
        self.ui.confirmTextEdit.plainText = detail
        self.ui.confirmPanel.visible = True
        # Deferred so it runs after the panel's geometry/layout has actually updated.
        qt.QTimer.singleShot(0, self._onConfirmPanelShown)

        # Pause the logic's result-queue poll timer while we block here, so it can't reenter
        # tool-call handling for the current response while this one is still pending.
        self.logic.pausePolling()
        self._confirmResult = False
        self._confirmLoop = qt.QEventLoop()
        self._confirmLoop.exec_()
        self._confirmLoop = None
        self.logic.resumePolling()

        self.ui.confirmPanel.visible = False
        self.ui.inputEdit.setFocus()
        return self._confirmResult

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

    def _appendAssistant(self, text):
        self.ui.chatView.append(f'<div style="margin:6px 0;"><b>Slicey:</b><br>{_escapeMultiline(text)}</div>')

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
