import html
import json
import logging
import queue
import threading

import ctk
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
                self._resultQueue.put(("claude_response", response))
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
            self._handleClaudeResponse(item[1])
        elif kind == "tool_result":
            _, blockId, result = item
            self._pendingResults[blockId] = result
            self._pendingAsyncCount -= 1
            self._emit("tool_result", (blockId, result))
            if self._pendingAsyncCount <= 0:
                self._finishToolBatch()

    def _handleClaudeResponse(self, response):
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
# Small QPlainTextEdit subclass so Enter sends the message and Shift+Enter inserts a newline.
# (PythonQt supports overriding virtual methods of native Qt classes from Python.)
#

class _ChatInputEdit(qt.QPlainTextEdit):
    def __init__(self, sendCallback, parent=None):
        qt.QPlainTextEdit.__init__(self, parent)
        self._sendCallback = sendCallback

    def keyPressEvent(self, event):
        if event.key() in (qt.Qt.Key_Return, qt.Qt.Key_Enter) and not (event.modifiers() & qt.Qt.ShiftModifier):
            self._sendCallback()
            return
        qt.QPlainTextEdit.keyPressEvent(self, event)


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

        self.logic.onEvent = self._onLogicEvent
        self.logic.confirmCallback = self._confirmToolCall

        self._buildConnectionSection()
        self._buildFoldersSection()
        self._buildExecutionSection()
        self._buildChatSection()

        self._updateConnectionStatus()
        self._refreshFoldersTable()

    def cleanup(self):
        if self._confirmLoop is not None:
            self._confirmLoop.quit()
        self.logic.cleanup()

    # ---------------------------------------------------------------- Connection panel

    def _buildConnectionSection(self):
        box = ctk.ctkCollapsibleButton()
        box.text = "Connection"
        self.layout.addWidget(box)
        form = qt.QFormLayout(box)

        self.connectionStatusLabel = qt.QLabel()
        form.addRow("Status:", self.connectionStatusLabel)

        self.connectButton = qt.QPushButton("Connect Claude account...")
        self.connectButton.clicked.connect(self.onConnectClicked)
        form.addRow(self.connectButton)

        self.apiKeyLineEdit = qt.QLineEdit()
        self.apiKeyLineEdit.setEchoMode(qt.QLineEdit.Password)
        self.apiKeyLineEdit.setPlaceholderText("Paste the API key you just created here")
        self.apiKeyLineEdit.visible = False
        form.addRow(self.apiKeyLineEdit)

        self.saveKeyButton = qt.QPushButton("Save key")
        self.saveKeyButton.visible = False
        self.saveKeyButton.clicked.connect(self.onSaveKeyClicked)
        form.addRow(self.saveKeyButton)

        self.disconnectButton = qt.QPushButton("Disconnect")
        self.disconnectButton.clicked.connect(self.onDisconnectClicked)
        form.addRow(self.disconnectButton)

        self.modelComboBox = qt.QComboBox()
        self.modelComboBox.setEditable(True)
        self.modelComboBox.addItems(Settings.MODEL_PRESETS)
        self.modelComboBox.setCurrentText(Settings.getModel())
        self.modelComboBox.currentTextChanged.connect(self.onModelChanged)
        form.addRow("Model:", self.modelComboBox)

    def onConnectClicked(self):
        qt.QDesktopServices.openUrl(qt.QUrl("https://console.anthropic.com/settings/keys"))
        self.apiKeyLineEdit.visible = True
        self.saveKeyButton.visible = True
        self.apiKeyLineEdit.setFocus()

    def onSaveKeyClicked(self):
        key = self.apiKeyLineEdit.text.strip()
        if not key:
            return
        self.saveKeyButton.enabled = False
        self.saveKeyButton.text = "Validating..."
        slicer.app.processEvents()
        try:
            ok, message = ClaudeClient.testApiKey(key)
        finally:
            self.saveKeyButton.enabled = True
            self.saveKeyButton.text = "Save key"
        if not ok:
            slicer.util.errorDisplay(f"Could not validate this API key:\n{message}")
            return
        Settings.setApiKey(key)
        self.logic.invalidateClient()
        self.apiKeyLineEdit.text = ""
        self.apiKeyLineEdit.visible = False
        self.saveKeyButton.visible = False
        self._updateConnectionStatus()

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
            self.connectionStatusLabel.text = "Connected" + suffix
        else:
            self.connectionStatusLabel.text = "Not connected"

    # ---------------------------------------------------------------- Shared folders panel

    def _buildFoldersSection(self):
        box = ctk.ctkCollapsibleButton()
        box.text = "Shared folders"
        self.layout.addWidget(box)
        layout = qt.QVBoxLayout(box)

        self.foldersTable = qt.QTableWidget(0, 3)
        self.foldersTable.setHorizontalHeaderLabels(["Folder", "Read-write", ""])
        self.foldersTable.horizontalHeader().setSectionResizeMode(0, qt.QHeaderView.Stretch)
        self.foldersTable.verticalHeader().visible = False
        self.foldersTable.setSelectionMode(qt.QAbstractItemView.NoSelection)
        layout.addWidget(self.foldersTable)

        addButton = qt.QPushButton("Add folder...")
        addButton.clicked.connect(self.onAddFolderClicked)
        layout.addWidget(addButton)

    def _refreshFoldersTable(self):
        folders = FolderAccess.listSharedFolders()
        self.foldersTable.setRowCount(len(folders))
        for row, folder in enumerate(folders):
            label = folder["path"] + ("" if folder["exists"] else "  [missing]")
            pathItem = qt.QTableWidgetItem(label)
            pathItem.setFlags(pathItem.flags() & ~qt.Qt.ItemIsEditable)
            self.foldersTable.setItem(row, 0, pathItem)

            writableCheck = qt.QCheckBox()
            writableCheck.checked = folder["writable"]
            writableCheck.toggled.connect(lambda checked, p=folder["path"]: self.onFolderWritableToggled(p, checked))
            cellWidget = qt.QWidget()
            cellLayout = qt.QHBoxLayout(cellWidget)
            cellLayout.setContentsMargins(0, 0, 0, 0)
            cellLayout.setAlignment(qt.Qt.AlignCenter)
            cellLayout.addWidget(writableCheck)
            self.foldersTable.setCellWidget(row, 1, cellWidget)

            removeButton = qt.QPushButton("Remove")
            removeButton.clicked.connect(lambda checked=False, p=folder["path"]: self.onRemoveFolderClicked(p))
            self.foldersTable.setCellWidget(row, 2, removeButton)

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

    def _buildExecutionSection(self):
        box = ctk.ctkCollapsibleButton()
        box.text = "Execution"
        self.layout.addWidget(box)
        layout = qt.QVBoxLayout(box)

        radioLayout = qt.QHBoxLayout()
        self.currentRadio = qt.QRadioButton("Run in current Slicer")
        self.newInstanceRadio = qt.QRadioButton("Run in separate Slicer instance")
        if Settings.getExecutionTarget() == "new_instance":
            self.newInstanceRadio.checked = True
        else:
            self.currentRadio.checked = True
        self.currentRadio.toggled.connect(self.onExecutionTargetChanged)
        radioLayout.addWidget(self.currentRadio)
        radioLayout.addWidget(self.newInstanceRadio)
        layout.addLayout(radioLayout)

        note = qt.QLabel(
            "Code execution is not restricted to the shared folders above - it has the same full "
            "access to this machine as Slicer's own Python console. Confirmation (see the "
            "auto-accept checkbox below the chat) is the only safeguard."
        )
        note.setWordWrap(True)
        note.setStyleSheet("color: gray; font-style: italic;")
        layout.addWidget(note)

        self.stopInstanceButton = qt.QPushButton("Stop sandbox instance")
        self.stopInstanceButton.clicked.connect(self.onStopInstanceClicked)
        layout.addWidget(self.stopInstanceButton)

    def onExecutionTargetChanged(self, checked):
        Settings.setExecutionTarget("current" if self.currentRadio.checked else "new_instance")

    def onStopInstanceClicked(self):
        PythonExecutor.stopCompanionInstance()

    # ---------------------------------------------------------------- Chat panel

    def _buildChatSection(self):
        self.chatView = qt.QTextBrowser()
        self.chatView.openExternalLinks = True
        self.layout.addWidget(self.chatView)

        # Inline confirmation panel, shown in place of a modal popup whenever a risky tool
        # call (running code / writing a file) needs the user's okay. Hidden the rest of the time.
        self.confirmPanel = qt.QWidget()
        confirmLayout = qt.QVBoxLayout(self.confirmPanel)
        confirmLayout.setContentsMargins(0, 4, 0, 4)

        self.confirmLabel = qt.QLabel()
        self.confirmLabel.setWordWrap(True)
        self.confirmLabel.setStyleSheet("font-weight: bold;")
        confirmLayout.addWidget(self.confirmLabel)

        self.confirmTextEdit = qt.QPlainTextEdit()
        self.confirmTextEdit.setReadOnly(True)
        self.confirmTextEdit.setMaximumHeight(120)
        self.confirmTextEdit.setFont(qt.QFont("Courier New"))
        confirmLayout.addWidget(self.confirmTextEdit)

        confirmButtonLayout = qt.QHBoxLayout()
        self.approveButton = qt.QPushButton("Approve")
        self.approveButton.setStyleSheet(_PRIMARY_BUTTON_STYLE)
        self.approveButton.setAutoDefault(True)
        self.approveButton.setDefault(True)
        self.approveButton.clicked.connect(self.onApproveClicked)
        confirmButtonLayout.addWidget(self.approveButton)
        self.rejectButton = qt.QPushButton("Reject")
        self.rejectButton.clicked.connect(self.onRejectClicked)
        confirmButtonLayout.addWidget(self.rejectButton)
        confirmButtonLayout.addStretch(1)
        confirmLayout.addLayout(confirmButtonLayout)

        self.confirmPanel.visible = False
        self.layout.addWidget(self.confirmPanel)

        self.autoAcceptCheckBox = qt.QCheckBox("Auto-accept actions (skip confirmation before running code or writing files)")
        self.autoAcceptCheckBox.checked = not Settings.getRequireConfirmation()
        self.autoAcceptCheckBox.toggled.connect(self.onAutoAcceptToggled)
        self.layout.addWidget(self.autoAcceptCheckBox)

        inputLayout = qt.QHBoxLayout()
        self.inputEdit = _ChatInputEdit(self.onSendClicked)
        self.inputEdit.setFixedHeight(60)
        inputLayout.addWidget(self.inputEdit)

        buttonLayout = qt.QVBoxLayout()
        self.sendButton = qt.QPushButton("Send")
        self.sendButton.setStyleSheet(_PRIMARY_BUTTON_STYLE)
        self.sendButton.setAutoDefault(True)
        self.sendButton.setDefault(True)
        self.sendButton.clicked.connect(self.onSendClicked)
        buttonLayout.addWidget(self.sendButton)
        self.stopButton = qt.QPushButton("Stop")
        self.stopButton.enabled = False
        self.stopButton.clicked.connect(self.onStopClicked)
        buttonLayout.addWidget(self.stopButton)
        self.clearButton = qt.QPushButton("Clear chat")
        self.clearButton.clicked.connect(self.onClearChatClicked)
        buttonLayout.addWidget(self.clearButton)
        inputLayout.addLayout(buttonLayout)

        self.layout.addLayout(inputLayout)

    def onAutoAcceptToggled(self, checked):
        Settings.setRequireConfirmation(not checked)

    def onSendClicked(self):
        if self.logic.isBusy():
            return
        text = self.inputEdit.plainText.strip()
        if not text:
            return
        if not Settings.getApiKey():
            slicer.util.errorDisplay("Connect your Claude account first (see the Connection panel above).")
            return
        self.inputEdit.plainText = ""
        self._appendUser(text)
        self.logic.sendUserMessage(text)

    def onStopClicked(self):
        self.logic.cancel()

    def onClearChatClicked(self):
        self.logic.resetConversation()
        self.chatView.clear()
        self._toolNames = {}

    # ---------------------------------------------------------------- Logic event handling

    def _onLogicEvent(self, eventType, payload):
        if eventType == "turn_started":
            self.sendButton.enabled = False
            self.stopButton.enabled = True
        elif eventType == "turn_finished":
            self.sendButton.enabled = True
            self.stopButton.enabled = False
        elif eventType == "assistant_text":
            self._appendAssistant(payload)
        elif eventType == "error":
            self._appendError(payload)
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

        self.confirmLabel.text = summary
        self.confirmTextEdit.plainText = detail
        self.confirmPanel.visible = True
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

        self.confirmPanel.visible = False
        self.inputEdit.setFocus()
        return self._confirmResult

    def _onConfirmPanelShown(self):
        self._scrollModulePanelToBottom()
        self.approveButton.setFocus()

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
        self.chatView.append(f'<div style="margin:6px 0;"><b>You:</b><br>{_escape(text)}</div>')

    def _appendAssistant(self, text):
        self.chatView.append(f'<div style="margin:6px 0;"><b>Slicey:</b><br>{_escape(text)}</div>')

    def _appendError(self, message):
        self.chatView.append(f'<div style="margin:6px 0; color:#b00020;"><b>Error:</b> {_escape(message)}</div>')

    def _appendToolStarted(self, blockId, name, toolInput):
        self._toolNames[blockId] = name
        detail = toolInput.get("code") or toolInput.get("content") or ""
        argsSummary = {k: v for k, v in toolInput.items() if k not in ("code", "content")}
        header = f"Running tool: {_escape(name)}"
        if argsSummary:
            header += f" {_escape(json.dumps(argsSummary))}"
        block = f'<pre style="background:#f0f0f0; padding:4px;">{_escape(detail)}</pre>' if detail else ""
        self.chatView.append(f'<div style="margin:6px 0; color:#555;"><b>{header}</b>{block}</div>')

    def _appendToolResult(self, blockId, result):
        name = self._toolNames.get(blockId, "tool")
        text = json.dumps(result, indent=2) if isinstance(result, (dict, list)) else str(result)
        if len(text) > 4000:
            text = text[:4000] + "\n... [truncated]"
        self.chatView.append(
            f'<div style="margin:6px 0 12px 0; color:#555;">Result of {_escape(name)}:'
            f'<pre style="background:#f7f7f7; padding:4px;">{_escape(text)}</pre></div>'
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
