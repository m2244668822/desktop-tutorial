#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import shutil
import socket
import struct
import subprocess
import sys
import tempfile
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.parse import quote, urlparse
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BASE_URL = "http://127.0.0.1:5001"
DEFAULT_REPORT = ROOT / "reports" / "chat_shell_browser_smoke_latest.json"
DEFAULT_SCREENSHOT = ROOT / "reports" / "chat_shell_browser_smoke_latest.png"


try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


@dataclass
class BrowserSmokeResult:
    ok: bool
    status: str
    base_url: str
    browser_path: str
    screenshot_path: str
    dom: dict[str, Any]
    console_errors: list[dict[str, Any]]
    exceptions: list[dict[str, Any]]
    log_errors: list[dict[str, Any]]
    notes: list[str]


def candidate_browser_paths() -> list[Path]:
    env_names = ("BROWSER_PATH", "CHROME_PATH", "MSEDGE_PATH", "CHROMIUM_PATH")
    candidates: list[Path] = []
    for name in env_names:
        value = os.environ.get(name)
        if value:
            candidates.append(Path(value))

    program_files = [
        os.environ.get("ProgramFiles"),
        os.environ.get("ProgramFiles(x86)"),
        os.environ.get("LOCALAPPDATA"),
    ]
    for root in [Path(p) for p in program_files if p]:
        candidates.extend(
            [
                root / "Google" / "Chrome" / "Application" / "chrome.exe",
                root / "Microsoft" / "Edge" / "Application" / "msedge.exe",
                root / "Chromium" / "Application" / "chrome.exe",
            ]
        )

    candidates.extend(
        [
            Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"),
            Path("/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge"),
            Path("/Applications/Chromium.app/Contents/MacOS/Chromium"),
            Path("/usr/bin/google-chrome"),
            Path("/usr/bin/chromium-browser"),
            Path("/usr/bin/chromium"),
            Path("/snap/bin/chromium"),
        ]
    )

    for name in ("chrome", "google-chrome", "chromium", "chromium-browser", "msedge"):
        found = shutil.which(name)
        if found:
            candidates.append(Path(found))

    unique: list[Path] = []
    seen: set[str] = set()
    for path in candidates:
        key = str(path)
        if key not in seen:
            seen.add(key)
            unique.append(path)
    return unique


def find_browser(explicit: str | None = None) -> Path | None:
    candidates = [Path(explicit)] if explicit else candidate_browser_paths()
    for path in candidates:
        if path.exists() and path.is_file():
            return path
    return None


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def http_json(url: str, *, method: str = "GET", timeout: float = 3.0) -> dict[str, Any]:
    req = Request(url, method=method)
    with urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8", errors="replace"))


def wait_for_devtools(port: int, timeout: float) -> None:
    deadline = time.time() + timeout
    last_error = ""
    while time.time() < deadline:
        try:
            http_json(f"http://127.0.0.1:{port}/json/version", timeout=1.0)
            return
        except Exception as exc:  # noqa: BLE001
            last_error = str(exc)
            time.sleep(0.2)
    raise RuntimeError(f"Chrome DevTools endpoint did not start: {last_error}")


def create_target(port: int, url: str) -> dict[str, Any]:
    encoded = quote(url, safe=":/?&=#%")
    try:
        return http_json(f"http://127.0.0.1:{port}/json/new?{encoded}", method="PUT")
    except Exception:
        return http_json(f"http://127.0.0.1:{port}/json/new?{encoded}", method="GET")


class CdpConnection:
    def __init__(self, websocket_url: str, timeout: float = 8.0):
        self.websocket_url = websocket_url
        self.timeout = timeout
        self.sock: socket.socket | None = None
        self.next_id = 1
        self.events: list[dict[str, Any]] = []

    def __enter__(self) -> "CdpConnection":
        parsed = urlparse(self.websocket_url)
        if parsed.scheme != "ws":
            raise ValueError(f"Unsupported WebSocket scheme: {parsed.scheme}")
        host = parsed.hostname or "127.0.0.1"
        port = int(parsed.port or 80)
        path = parsed.path or "/"
        if parsed.query:
            path += f"?{parsed.query}"
        self.sock = socket.create_connection((host, port), timeout=self.timeout)
        self.sock.settimeout(self.timeout)
        key = base64.b64encode(os.urandom(16)).decode("ascii")
        request = (
            f"GET {path} HTTP/1.1\r\n"
            f"Host: {host}:{port}\r\n"
            "Upgrade: websocket\r\n"
            "Connection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {key}\r\n"
            "Sec-WebSocket-Version: 13\r\n\r\n"
        )
        self.sock.sendall(request.encode("ascii"))
        response = self._read_http_response()
        if " 101 " not in response.split("\r\n", 1)[0]:
            raise RuntimeError(f"WebSocket upgrade failed: {response[:200]}")
        return self

    def __exit__(self, *_exc: object) -> None:
        if self.sock:
            try:
                self.sock.close()
            except OSError:
                pass

    def _read_http_response(self) -> str:
        assert self.sock
        chunks: list[bytes] = []
        while b"\r\n\r\n" not in b"".join(chunks):
            chunk = self.sock.recv(4096)
            if not chunk:
                break
            chunks.append(chunk)
        return b"".join(chunks).decode("latin1", errors="replace")

    def _recv_exact(self, size: int) -> bytes:
        assert self.sock
        chunks: list[bytes] = []
        remaining = size
        while remaining:
            chunk = self.sock.recv(remaining)
            if not chunk:
                raise ConnectionError("WebSocket connection closed")
            chunks.append(chunk)
            remaining -= len(chunk)
        return b"".join(chunks)

    def send_text(self, text: str) -> None:
        assert self.sock
        payload = text.encode("utf-8")
        header = bytearray([0x81])
        length = len(payload)
        if length < 126:
            header.append(0x80 | length)
        elif length < 65536:
            header.append(0x80 | 126)
            header.extend(struct.pack("!H", length))
        else:
            header.append(0x80 | 127)
            header.extend(struct.pack("!Q", length))
        mask = os.urandom(4)
        masked = bytes(byte ^ mask[index % 4] for index, byte in enumerate(payload))
        self.sock.sendall(bytes(header) + mask + masked)

    def recv_text(self) -> str | None:
        first = self._recv_exact(2)
        opcode = first[0] & 0x0F
        masked = bool(first[1] & 0x80)
        length = first[1] & 0x7F
        if length == 126:
            length = struct.unpack("!H", self._recv_exact(2))[0]
        elif length == 127:
            length = struct.unpack("!Q", self._recv_exact(8))[0]
        mask = self._recv_exact(4) if masked else b""
        payload = self._recv_exact(length) if length else b""
        if masked:
            payload = bytes(byte ^ mask[index % 4] for index, byte in enumerate(payload))
        if opcode == 0x8:
            return None
        if opcode == 0x9:
            return ""
        if opcode not in (0x1, 0x0):
            return ""
        return payload.decode("utf-8", errors="replace")

    def call(self, method: str, params: dict[str, Any] | None = None, timeout: float | None = None) -> dict[str, Any]:
        cmd_id = self.next_id
        self.next_id += 1
        self.send_text(json.dumps({"id": cmd_id, "method": method, "params": params or {}}))
        return self.wait_for(lambda message: message.get("id") == cmd_id, timeout=timeout)

    def wait_for(self, predicate, timeout: float | None = None) -> dict[str, Any]:
        assert self.sock
        old_timeout = self.sock.gettimeout()
        self.sock.settimeout(0.5)
        deadline = time.time() + (timeout or self.timeout)
        try:
            while time.time() < deadline:
                try:
                    raw = self.recv_text()
                except socket.timeout:
                    continue
                if not raw:
                    continue
                message = json.loads(raw)
                if "method" in message:
                    self.events.append(message)
                if predicate(message):
                    return message
        finally:
            self.sock.settimeout(old_timeout)
        raise TimeoutError("Timed out waiting for CDP response/event")

    def drain_events(self, seconds: float = 0.5) -> None:
        assert self.sock
        old_timeout = self.sock.gettimeout()
        self.sock.settimeout(0.1)
        deadline = time.time() + seconds
        try:
            while time.time() < deadline:
                try:
                    raw = self.recv_text()
                except socket.timeout:
                    continue
                if not raw:
                    continue
                message = json.loads(raw)
                if "method" in message:
                    self.events.append(message)
        finally:
            self.sock.settimeout(old_timeout)


DOM_AUDIT_EXPRESSION = r"""
(() => {
  const byId = (id) => document.getElementById(id);
  const visible = (el) => {
    if (!el) return false;
    const style = getComputedStyle(el);
    const rect = el.getBoundingClientRect();
    return style.display !== "none" && style.visibility !== "hidden" && rect.width > 0 && rect.height > 0;
  };
  const rectOf = (selector) => {
    const el = document.querySelector(selector);
    if (!el || !visible(el)) return null;
    const rect = el.getBoundingClientRect();
    return {
      selector,
      x: Math.round(rect.x),
      y: Math.round(rect.y),
      width: Math.round(rect.width),
      height: Math.round(rect.height),
      bottom: Math.round(rect.bottom),
      right: Math.round(rect.right),
    };
  };
  const overlapArea = (a, b) => {
    if (!a || !b) return 0;
    const x = Math.max(0, Math.min(a.right, b.right) - Math.max(a.x, b.x));
    const y = Math.max(0, Math.min(a.bottom, b.bottom) - Math.max(a.y, b.y));
    return x * y;
  };
  const boxes = {
    topbar: rectOf(".topbar"),
    app: rectOf(".app"),
    inputBar: rectOf(".input-bar"),
    sidebar: rectOf(".sidebar"),
    main: rectOf(".main"),
    rightPanel: rectOf(".right-panel"),
    hub: rectOf("#hubView"),
  };
  const overlaps = {
    topbarInput: overlapArea(boxes.topbar, boxes.inputBar),
    appInput: overlapArea(boxes.app, boxes.inputBar),
    sidebarMain: overlapArea(boxes.sidebar, boxes.main),
    rightPanelMain: overlapArea(boxes.rightPanel, boxes.main),
  };
  return {
    href: location.href,
    title: document.title,
    readyState: document.readyState,
    viewport: { width: innerWidth, height: innerHeight },
    bodyTextLength: document.body.innerText.length,
    requiredIds: {
      hubView: !!byId("hubView"),
      tasksPanel: !!byId("tasksPanel"),
      tasksList: !!byId("tasksList"),
      agentActivityMeta: !!byId("agentActivityMeta"),
      agentActivityBoard: !!byId("agentActivityBoard"),
      chatView: !!byId("chatView"),
      chatArea: !!byId("chatArea"),
      msgInput: !!byId("msgInput"),
      sendBtn: !!byId("sendBtn"),
      bridgeState: !!byId("bridgeState"),
      monOpenClaw: !!byId("mon-openclaw"),
      monOpenClawPolicy: !!byId("mon-openclaw-policy"),
      monOpenClawNote: !!byId("mon-openclaw-note"),
    },
    visible: {
      hubView: visible(byId("hubView")),
      agentActivityBoard: visible(byId("agentActivityBoard")),
      msgInput: visible(byId("msgInput")),
      sendBtn: visible(byId("sendBtn")),
      monOpenClaw: visible(byId("mon-openclaw")),
      monOpenClawPolicy: visible(byId("mon-openclaw-policy")),
    },
    contract: {
      providerBackoff:
        typeof PROVIDER_RATE_LIMIT_BACKOFF_MS !== "undefined" &&
        PROVIDER_RATE_LIMIT_BACKOFF_MS === 1800000,
      tasksFilter: typeof _tasksFilter !== "undefined" ? _tasksFilter : null,
      renderAgentActivityBoard: typeof renderAgentActivityBoard === "function",
      fetchTasksSummary: typeof fetchTasksSummary === "function",
      bootstrapPolling: typeof bootstrapPolling === "function",
    },
    boxes,
    overlaps,
  };
})()
"""


def simplify_console_event(event: dict[str, Any]) -> dict[str, Any]:
    params = event.get("params", {})
    args = params.get("args") or []
    values: list[str] = []
    for arg in args:
        if "value" in arg:
            values.append(str(arg.get("value")))
        elif "description" in arg:
            values.append(str(arg.get("description")))
    return {
        "type": params.get("type", ""),
        "text": " ".join(values)[:800],
        "url": params.get("stackTrace", {}).get("callFrames", [{}])[0].get("url", ""),
    }


def simplify_exception_event(event: dict[str, Any]) -> dict[str, Any]:
    params = event.get("params", {})
    details = params.get("exceptionDetails", {})
    exception = details.get("exception", {})
    return {
        "text": details.get("text", ""),
        "description": exception.get("description", ""),
        "url": details.get("url", ""),
        "line": details.get("lineNumber"),
        "column": details.get("columnNumber"),
    }


def simplify_log_event(event: dict[str, Any]) -> dict[str, Any]:
    entry = event.get("params", {}).get("entry", {})
    return {
        "level": entry.get("level", ""),
        "text": entry.get("text", "")[:800],
        "url": entry.get("url", ""),
        "source": entry.get("source", ""),
    }


def evaluate_result_value(response: dict[str, Any]) -> Any:
    if "error" in response:
        raise RuntimeError(json.dumps(response["error"], ensure_ascii=False))
    result = response.get("result", {}).get("result", {})
    if result.get("subtype") == "error":
        raise RuntimeError(result.get("description", "Runtime.evaluate failed"))
    return result.get("value")


def run_smoke(
    *,
    base_url: str,
    browser_path: Path,
    screenshot_path: Path,
    timeout: float,
    width: int,
    height: int,
) -> BrowserSmokeResult:
    notes: list[str] = []
    port = free_port()
    target_url = f"{base_url.rstrip('/')}/chat_shell"
    with tempfile.TemporaryDirectory(
        prefix="chat-shell-browser-smoke-",
        ignore_cleanup_errors=True,
    ) as user_data_dir:
        args = [
            str(browser_path),
            "--headless=new",
            "--disable-gpu",
            "--disable-extensions",
            "--disable-background-networking",
            "--no-first-run",
            "--no-default-browser-check",
            f"--remote-debugging-port={port}",
            f"--user-data-dir={user_data_dir}",
            "about:blank",
        ]
        proc = subprocess.Popen(
            args,
            cwd=str(ROOT),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        try:
            wait_for_devtools(port, timeout=timeout)
            target = create_target(port, "about:blank")
            ws_url = target.get("webSocketDebuggerUrl")
            if not ws_url:
                raise RuntimeError(f"Missing DevTools websocket URL: {target}")

            with CdpConnection(ws_url, timeout=timeout) as cdp:
                cdp.call("Runtime.enable")
                cdp.call("Log.enable")
                cdp.call("Page.enable")
                cdp.call(
                    "Emulation.setDeviceMetricsOverride",
                    {
                        "width": width,
                        "height": height,
                        "deviceScaleFactor": 1,
                        "mobile": False,
                    },
                )
                cdp.call("Page.navigate", {"url": target_url})
                cdp.wait_for(lambda message: message.get("method") == "Page.loadEventFired", timeout=timeout)
                cdp.drain_events(seconds=1.5)
                ready = cdp.call(
                    "Runtime.evaluate",
                    {
                        "expression": "document.readyState",
                        "returnByValue": True,
                    },
                )
                if evaluate_result_value(ready) != "complete":
                    notes.append("document.readyState did not reach complete after load event")

                dom_response = cdp.call(
                    "Runtime.evaluate",
                    {
                        "expression": DOM_AUDIT_EXPRESSION,
                        "returnByValue": True,
                        "awaitPromise": True,
                    },
                )
                dom = evaluate_result_value(dom_response) or {}

                screenshot_response = cdp.call(
                    "Page.captureScreenshot",
                    {"format": "png", "captureBeyondViewport": False},
                    timeout=timeout,
                )
                screenshot_path.parent.mkdir(parents=True, exist_ok=True)
                screenshot_path.write_bytes(base64.b64decode(screenshot_response["result"]["data"]))

                console_errors = [
                    simplify_console_event(event)
                    for event in cdp.events
                    if event.get("method") == "Runtime.consoleAPICalled"
                    and event.get("params", {}).get("type") in {"error", "assert"}
                ]
                exceptions = [
                    simplify_exception_event(event)
                    for event in cdp.events
                    if event.get("method") == "Runtime.exceptionThrown"
                ]
                log_errors = [
                    simplify_log_event(event)
                    for event in cdp.events
                    if event.get("method") == "Log.entryAdded"
                    and event.get("params", {}).get("entry", {}).get("level") == "error"
                ]

                missing_ids = [
                    key for key, present in (dom.get("requiredIds") or {}).items() if not present
                ]
                visible_map = dom.get("visible") or {}
                viewport_width = int((dom.get("viewport") or {}).get("width") or width)
                required_visible = ["hubView", "agentActivityBoard", "msgInput", "sendBtn"]
                if viewport_width >= 720:
                    required_visible.extend(["monOpenClaw", "monOpenClawPolicy"])
                invisible = [key for key in required_visible if not visible_map.get(key)]
                contract = dom.get("contract") or {}
                contract_failures = [
                    key for key, value in contract.items()
                    if value is not True and key != "tasksFilter"
                ]
                if contract.get("tasksFilter") != "unresolved":
                    contract_failures.append("tasksFilter")
                overlap_failures = [
                    key for key, value in (dom.get("overlaps") or {}).items() if int(value or 0) > 0
                ]
                text_too_short = int(dom.get("bodyTextLength") or 0) < 200
                if text_too_short:
                    notes.append("body text is unexpectedly short")

                ok = not any(
                    [
                        missing_ids,
                        invisible,
                        contract_failures,
                        overlap_failures,
                        console_errors,
                        exceptions,
                        log_errors,
                        text_too_short,
                    ]
                )
                if missing_ids:
                    notes.append(f"missing ids: {', '.join(missing_ids)}")
                if invisible:
                    notes.append(f"invisible elements: {', '.join(invisible)}")
                if contract_failures:
                    notes.append(f"contract failures: {', '.join(contract_failures)}")
                if overlap_failures:
                    notes.append(f"layout overlaps: {', '.join(overlap_failures)}")

                return BrowserSmokeResult(
                    ok=ok,
                    status="ready" if ok else "failed",
                    base_url=base_url.rstrip("/"),
                    browser_path=str(browser_path),
                    screenshot_path=str(screenshot_path),
                    dom=dom,
                    console_errors=console_errors,
                    exceptions=exceptions,
                    log_errors=log_errors,
                    notes=notes,
                )
        finally:
            try:
                proc.terminate()
                proc.wait(timeout=5)
            except Exception:
                proc.kill()


def write_report(result: BrowserSmokeResult, path: Path) -> None:
    payload = asdict(result)
    payload["generated_at"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Headless browser smoke test for /chat_shell.")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--browser-path", default="")
    parser.add_argument("--json-out", default=str(DEFAULT_REPORT))
    parser.add_argument("--screenshot-out", default=str(DEFAULT_SCREENSHOT))
    parser.add_argument("--timeout", type=float, default=12.0)
    parser.add_argument("--width", type=int, default=1440)
    parser.add_argument("--height", type=int, default=1000)
    args = parser.parse_args()

    browser = find_browser(args.browser_path or None)
    if not browser:
        result = BrowserSmokeResult(
            ok=False,
            status="browser_not_found",
            base_url=args.base_url.rstrip("/"),
            browser_path="",
            screenshot_path=args.screenshot_out,
            dom={},
            console_errors=[],
            exceptions=[],
            log_errors=[],
            notes=["Set BROWSER_PATH, CHROME_PATH, or MSEDGE_PATH to a Chromium-compatible browser."],
        )
        write_report(result, Path(args.json_out))
        print("== Chat Shell Browser Smoke ==")
        print("[FAIL] browser_not_found")
        return 1

    try:
        result = run_smoke(
            base_url=args.base_url,
            browser_path=browser,
            screenshot_path=Path(args.screenshot_out),
            timeout=args.timeout,
            width=args.width,
            height=args.height,
        )
    except (URLError, OSError, RuntimeError, TimeoutError) as exc:
        result = BrowserSmokeResult(
            ok=False,
            status="smoke_error",
            base_url=args.base_url.rstrip("/"),
            browser_path=str(browser),
            screenshot_path=args.screenshot_out,
            dom={},
            console_errors=[],
            exceptions=[],
            log_errors=[],
            notes=[str(exc)],
        )

    write_report(result, Path(args.json_out))
    print("== Chat Shell Browser Smoke ==")
    print(f"browser: {result.browser_path}")
    print(f"base_url: {result.base_url}")
    print(f"screenshot: {result.screenshot_path}")
    print(f"status: {result.status}")
    for note in result.notes:
        print(f"[NOTE] {note}")
    print("[OK] browser smoke passed" if result.ok else "[FAIL] browser smoke failed")
    return 0 if result.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
