import json
import logging
import os

import slicer

logger = logging.getLogger(__name__)

SETTINGS_PREFIX = "Slicey/"

KEYRING_SERVICE_NAME = "Slicey"
KEYRING_USERNAME = "anthropic_api_key"
OPENAI_KEYRING_USERNAME = "openai_api_key"
LLM_SERVER_KEYRING_USERNAME = "llm_server_api_key"

# Which LLM drives Slicey and how it signs in - the same choices as the nnInteractive Agent
# module (nninteractive_agent.web.llm.BACKENDS). "claude-api" calls the Anthropic Messages API
# directly; the others run a local coding agent (Claude Code or Codex) that only gets Slicey's
# own tools, so the subscription backends cost no API tokens.
BACKENDS = (
    ("claude-api", "Claude, Anthropic API key"),
    ("claude", "Claude subscription (Claude Code login)"),
    ("codex", "ChatGPT subscription (Codex login)"),
    ("codex-api", "Codex, OpenAI API key"),
    ("server", "Own model on an Anthropic-compatible server (e.g. vLLM)"),
)
DEFAULT_BACKEND = "claude-api"
# Backends whose cost Slicey can estimate from token counts (MODEL_PRICING_USD_PER_MTOK).
COST_TRACKED_BACKENDS = ("claude-api",)
SUBSCRIPTION_BACKENDS = ("claude", "codex")
# Offered for Claude Code until the login check lists the models of the subscription.
CLAUDE_CODE_MODELS = ["opus", "sonnet", "haiku"]
# "" (shown as "(auto)") leaves the effort to the agent's default for the model.
EFFORTS = ["", "low", "medium", "high", "xhigh", "max"]
DEFAULT_LLM_SERVER_URL = "http://localhost:8000"  # vLLM's default port
# Working folder of the local agents (Claude Code and Codex need one; they get no file tools).
AGENT_WORK_DIR = os.path.join(os.path.expanduser("~"), ".Slicey", "agent")
# Codex keeps the API key of codex-api here, away from the ChatGPT login in ~/.codex.
CODEX_API_HOME = os.path.join(os.path.expanduser("~"), ".Slicey", "codex-api")

DEFAULT_MODEL = "claude-sonnet-4-6"
# Offered for the Anthropic API until the API key is checked, which lists the available models.
MODEL_PRESETS = [
    "claude-sonnet-4-6",
    "claude-opus-4-8",
    "claude-haiku-4-5-20251001",
    "claude-fable-5",
]

# USD per 1,000,000 tokens (input, output). Update if Anthropic changes pricing.
MODEL_PRICING_USD_PER_MTOK = {
    "claude-sonnet-4-6": (3.00, 15.00),
    "claude-opus-4-8": (5.00, 25.00),
    "claude-haiku-4-5-20251001": (1.00, 5.00),
    "claude-haiku-4-5": (1.00, 5.00),
    "claude-fable-5": (10.00, 50.00),
}


def estimateCostUsd(model, inputTokens, outputTokens):
    """Returns an estimated USD cost for the given token counts on `model`, or None if
    the model isn't in the pricing table (e.g. a custom/unrecognized model string)."""
    pricing = MODEL_PRICING_USD_PER_MTOK.get(model)
    if pricing is None:
        return None
    inputPrice, outputPrice = pricing
    return (inputTokens * inputPrice + outputTokens * outputPrice) / 1_000_000


def _settings():
    return slicer.app.userSettings()


def getJson(key, default):
    raw = _settings().value(SETTINGS_PREFIX + key)
    if not raw:
        return default
    try:
        return json.loads(raw)
    except (TypeError, ValueError):
        return default


def setJson(key, value):
    _settings().setValue(SETTINGS_PREFIX + key, json.dumps(value))


def getBool(key, default):
    raw = _settings().value(SETTINGS_PREFIX + key)
    if raw is None or raw == "":
        return default
    return str(raw).lower() in ("1", "true", "yes")


def setBool(key, value):
    _settings().setValue(SETTINGS_PREFIX + key, "true" if value else "false")


def getString(key, default):
    raw = _settings().value(SETTINGS_PREFIX + key)
    if raw is None or raw == "":
        return default
    return str(raw)


def setString(key, value):
    _settings().setValue(SETTINGS_PREFIX + key, value)


def getSharedFolders():
    """Returns a list of {"path": str, "writable": bool} dicts."""
    return getJson("SharedFolders", [])


def setSharedFolders(folders):
    setJson("SharedFolders", folders)


def getAllTimeUsage():
    """Returns the persisted all-time usage counter as a
    {"inputTokens": int, "outputTokens": int, "costUsd": float, "costEstimateIncomplete": bool} dict."""
    return getJson("AllTimeUsage", {"inputTokens": 0, "outputTokens": 0, "costUsd": 0.0, "costEstimateIncomplete": False})


def setAllTimeUsage(usage):
    setJson("AllTimeUsage", usage)


def getModel():
    return getString("Model", DEFAULT_MODEL)


def setModel(model):
    setString("Model", model)


def getBackend():
    backend = getString("Backend", DEFAULT_BACKEND)
    return backend if backend in dict(BACKENDS) else DEFAULT_BACKEND


def setBackend(value):
    setString("Backend", value)


def getBackendModel(backend):
    """The chat model of `backend`; "" lets the agent choose (its default model)."""
    if backend == "claude-api":
        return getModel()
    return getString(f"Model/{backend}", "")


def setBackendModel(backend, model):
    if backend == "claude-api":
        setModel(model)
    else:
        setString(f"Model/{backend}", model)


def getBackendModels(backend):
    """The models offered for `backend`, as {"id", "label", "description"} dicts: what the last
    connection check listed, or a fixed list before that."""
    models = getJson(f"Models/{backend}", None)
    if models is None:
        models = {"claude-api": MODEL_PRESETS, "claude": [""] + CLAUDE_CODE_MODELS}.get(backend, [])
    # Older settings stored the ids only.
    return [m if isinstance(m, dict) else {"id": m, "label": m or "Default", "description": ""} for m in models]


def hasListedModels(backend):
    """Whether a connection check has listed the models of `backend` (else a fixed list is offered)."""
    return getJson(f"Models/{backend}", None) is not None


def setBackendModels(backend, models):
    """`models`: {"id", "label", "description"} dicts; the agent's default model has the id ""."""
    setJson(f"Models/{backend}", models)


def getEffort():
    return getString("Effort", "")


def setEffort(value):
    setString("Effort", value)


def getLlmServerUrl():
    return getString("LLMServerUrl", DEFAULT_LLM_SERVER_URL)


def setLlmServerUrl(value):
    setString("LLMServerUrl", value)


def isBackendChecked(backend):
    """Whether the login/server of a local-agent backend passed the check in the Connection panel."""
    return getBool(f"Checked/{backend}", False)


def setBackendChecked(backend, value):
    setBool(f"Checked/{backend}", value)


# When Slicey asks before running code or writing a file. "auto" asks only for the actions
# RiskCheck finds risky.
APPROVAL_MODES = (
    ("auto", "Auto: ask only before risky actions"),
    ("ask", "Ask before every action"),
    ("accept", "Accept all actions"),
)
DEFAULT_APPROVAL_MODE = "auto"


def getApprovalMode():
    mode = getString("ApprovalMode", "")
    if mode in dict(APPROVAL_MODES):
        return mode
    # Before approval modes there was only an auto-accept checkbox (RequireConfirmation=false).
    if not getBool("RequireConfirmation", True):
        return "accept"
    return DEFAULT_APPROVAL_MODE


def setApprovalMode(value):
    setString("ApprovalMode", value)


def getExecutionTarget():
    return getString("ExecutionTarget", "current")


def setExecutionTarget(value):
    setString("ExecutionTarget", value)


def getChatLogFolder():
    """Folder each chat is saved into as Slicey-YYYYMMDD-HHMMSS.md, one file per chat."""
    return getString("ChatLogFolder", os.path.join(os.path.expanduser("~"), ".Slicey"))


def setChatLogFolder(value):
    setString("ChatLogFolder", value)


def getRenderMarkdown():
    """Whether Slicey's replies are shown formatted (Markdown) in the chat view."""
    return getBool("RenderMarkdown", True)


def setRenderMarkdown(value):
    setBool("RenderMarkdown", value)


def getPastChatsAccess():
    """Whether Slicey may look up the user's earlier chats (in the chat log folder)."""
    return getBool("PastChatsAccess", True)


def setPastChatsAccess(value):
    setBool("PastChatsAccess", value)


# Fixed base instructions - not user-editable. The shared-folder list itself is always
# appended fresh from current settings in ClaudeClient.buildSystemPrompt() - it can't be
# baked into this text or it would go stale as folders are added/removed.
SYSTEM_PROMPT_INSTRUCTIONS = (
    "You are Slicey, an AI assistant embedded inside the user's local 3D Slicer application, "
    "helping them use, develop, and modify 3D Slicer extensions and modules.\n\n"
    "You can only read/write inside the shared folders listed below (and only the read-write "
    "ones for writes); any other path will be rejected. Use run_python_in_slicer to act on the "
    "running Slicer application itself - never ask the user to manually paste code into "
    "Slicer's Python console. After changing a scripted module's .py file, reload it with "
    "slicer.util.reloadScriptedModule('ModuleName') instead of restarting Slicer."
)


def getCustomSystemPromptText():
    """Returns the user's optional extra instructions, appended to the fixed system prompt
    in ClaudeClient.buildSystemPrompt(). Empty string if the user hasn't set any."""
    return getString("CustomSystemPromptText", "")


def setCustomSystemPromptText(text):
    setString("CustomSystemPromptText", text)


def _ensureKeyring():
    try:
        import keyring
        return keyring
    except ImportError:
        slicer.util.pip_install("keyring")
        import keyring
        return keyring


def _fallbackSettingsKey(username):
    # The Anthropic key keeps its original settings name.
    return "ApiKeyFallback" if username == KEYRING_USERNAME else f"ApiKeyFallback/{username}"


def getApiKey(username=KEYRING_USERNAME):
    """Returns the stored API key (the Anthropic one by default), or an empty string if none is stored."""
    try:
        keyring = _ensureKeyring()
        key = keyring.get_password(KEYRING_SERVICE_NAME, username)
        if key:
            return key
    except Exception as e:
        logger.warning(f"Slicey: could not read API key from OS keyring ({e}); using fallback storage.")
    # Fallback used only if the OS keyring backend is unavailable (e.g. headless Linux without a secret service).
    return getString(_fallbackSettingsKey(username), "")


def setApiKey(key, username=KEYRING_USERNAME):
    """Stores an API key. Returns True if stored in the OS keyring, False if it fell back to plain settings storage."""
    try:
        keyring = _ensureKeyring()
        keyring.set_password(KEYRING_SERVICE_NAME, username, key)
        setString(_fallbackSettingsKey(username), "")  # clear any previous less-secure copy
        return True
    except Exception as e:
        logger.warning(f"Slicey: could not store API key in OS keyring ({e}); using fallback storage.")
        setString(_fallbackSettingsKey(username), key)
        return False


def clearApiKey(username=KEYRING_USERNAME):
    try:
        keyring = _ensureKeyring()
        keyring.delete_password(KEYRING_SERVICE_NAME, username)
    except Exception:
        pass
    setString(_fallbackSettingsKey(username), "")


def isApiKeyStoredSecurely():
    """Best-effort check of whether the OS keyring backend is usable on this system."""
    try:
        keyring = _ensureKeyring()
        keyring.get_password(KEYRING_SERVICE_NAME, "connection_test")
        return True
    except Exception:
        return False
