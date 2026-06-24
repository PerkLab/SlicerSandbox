import json
import logging

import slicer

logger = logging.getLogger(__name__)

SETTINGS_PREFIX = "Slicey/"

KEYRING_SERVICE_NAME = "Slicey"
KEYRING_USERNAME = "anthropic_api_key"

DEFAULT_MODEL = "claude-sonnet-4-6"
MODEL_PRESETS = [
    "claude-sonnet-4-6",
    "claude-opus-4-8",
    "claude-haiku-4-5-20251001",
    "claude-fable-5",
]
# Cheap/fast model used only to validate that an API key works, regardless of the user's
# selected chat model.
VALIDATION_MODEL = "claude-haiku-4-5-20251001"

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


def getRequireConfirmation():
    return getBool("RequireConfirmation", True)


def setRequireConfirmation(value):
    setBool("RequireConfirmation", value)


def getExecutionTarget():
    return getString("ExecutionTarget", "current")


def setExecutionTarget(value):
    setString("ExecutionTarget", value)


def _ensureKeyring():
    try:
        import keyring
        return keyring
    except ImportError:
        slicer.util.pip_install("keyring")
        import keyring
        return keyring


def getApiKey():
    """Returns the stored Anthropic API key, or an empty string if none is stored."""
    try:
        keyring = _ensureKeyring()
        key = keyring.get_password(KEYRING_SERVICE_NAME, KEYRING_USERNAME)
        if key:
            return key
    except Exception as e:
        logger.warning(f"Slicey: could not read API key from OS keyring ({e}); using fallback storage.")
    # Fallback used only if the OS keyring backend is unavailable (e.g. headless Linux without a secret service).
    return getString("ApiKeyFallback", "")


def setApiKey(key):
    """Stores the Anthropic API key. Returns True if stored in the OS keyring, False if it fell back to plain settings storage."""
    try:
        keyring = _ensureKeyring()
        keyring.set_password(KEYRING_SERVICE_NAME, KEYRING_USERNAME, key)
        setString("ApiKeyFallback", "")  # clear any previous less-secure copy
        return True
    except Exception as e:
        logger.warning(f"Slicey: could not store API key in OS keyring ({e}); using fallback storage.")
        setString("ApiKeyFallback", key)
        return False


def clearApiKey():
    try:
        keyring = _ensureKeyring()
        keyring.delete_password(KEYRING_SERVICE_NAME, KEYRING_USERNAME)
    except Exception:
        pass
    setString("ApiKeyFallback", "")


def isApiKeyStoredSecurely():
    """Best-effort check of whether the OS keyring backend is usable on this system."""
    try:
        keyring = _ensureKeyring()
        keyring.get_password(KEYRING_SERVICE_NAME, "connection_test")
        return True
    except Exception:
        return False
