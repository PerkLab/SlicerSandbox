"""A local relay between Claude Code and an Anthropic-compatible LLM server (LM Studio, ...).

Claude Code sends models it does not know "system" messages in the middle of the conversation (the
environment description, for example), and falls back to sending them without only if the server
answers HTTP 400 or 422. The chat templates of many local models (Qwen's, for example) raise "System
message must be at the beginning" instead, which LM Studio reports as HTTP 500, so the request fails
again on every retry. The relay moves those messages into the system prompt before passing the
request on, and streams the server's answer back unchanged.
"""

import http.server
import json
import logging
import threading
import urllib.error
import urllib.request

logger = logging.getLogger(__name__)

_HOP_HEADERS = ("host", "content-length", "connection", "transfer-encoding", "keep-alive")

_relay = None  # (server, target url)


def moveSystemMessages(request):
    """`request` (a Messages API request body) with its "system" messages moved to the end of its
    system prompt."""
    messages = request.get("messages") or []
    moved = [m for m in messages if m.get("role") == "system"]
    if not moved:
        return request
    system = request.get("system") or []
    if isinstance(system, str):
        system = [{"type": "text", "text": system}]
    for message in moved:
        content = message.get("content")
        if isinstance(content, str):
            system.append({"type": "text", "text": content})
        else:
            system += [{"type": "text", "text": b["text"]} for b in content or [] if b.get("type") == "text"]
    return {**request, "system": system, "messages": [m for m in messages if m.get("role") != "system"]}


def _handlerClass(target):
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))  # no system proxy for a local server

    class Handler(http.server.BaseHTTPRequestHandler):
        def _relay(self):
            length = int(self.headers.get("content-length") or 0)
            body = self.rfile.read(length) if length else None
            if body and self.path.split("?")[0].endswith("/messages"):
                try:
                    body = json.dumps(moveSystemMessages(json.loads(body))).encode()
                except (ValueError, AttributeError, KeyError, TypeError):
                    pass  # not a request we understand: pass it on as it is
            headers = {k: v for k, v in self.headers.items() if k.lower() not in _HOP_HEADERS}
            request = urllib.request.Request(target + self.path, data=body, method=self.command, headers=headers)
            try:
                response = opener.open(request, timeout=3600)
            except urllib.error.HTTPError as e:
                response = e
            except OSError as e:
                self.send_error(502, f"Slicey relay: {target} is not reachable ({e})")
                return
            with response:
                self.send_response(response.status if hasattr(response, "status") else response.code)
                for k, v in response.headers.items():
                    if k.lower() not in _HOP_HEADERS:
                        self.send_header(k, v)
                self.send_header("Connection", "close")
                self.end_headers()
                while True:
                    chunk = response.read1(65536)
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    self.wfile.flush()

        do_GET = do_POST = do_PUT = do_DELETE = _relay

        def log_message(self, format, *args):
            logger.debug("Slicey relay: " + format, *args)

    return Handler


def relayUrl(target):
    """The URL of a relay to `target` (started on first use, replaced when the target changes)."""
    global _relay
    target = target.rstrip("/")
    if _relay is None or _relay[1] != target:
        if _relay is not None:
            _relay[0].shutdown()
            _relay[0].server_close()
        server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _handlerClass(target))
        server.daemon_threads = True
        threading.Thread(target=server.serve_forever, name="SliceyServerRelay", daemon=True).start()
        _relay = (server, target)
    return f"http://127.0.0.1:{_relay[0].server_address[1]}"
