import hashlib
import json
import threading
import time
from collections import deque

import requests
import websocket

from . import config
from .logger import get_logger

log = get_logger(__name__)


class NapCatClient:
    def __init__(self):
        self.ws = None
        self._handlers = []
        self._running = False
        self._thread = None
        self._seen_ids = deque(maxlen=200)
        self._seen_content = deque(maxlen=100)
        self._dedup_window = 3.0

    def on_event(self, handler):
        self._handlers.append(handler)

    def _dispatch(self, event: dict):
        for handler in self._handlers:
            try:
                handler(event)
            except Exception as e:
                log.exception("handler error")

    def send_message(self, message_type, target_id, message, at_user_id=None):
        if message_type == "group" and at_user_id is not None:
            message = f"[CQ:at,qq={at_user_id}] {message}"
        id_field = "user_id" if message_type == "private" else "group_id"
        payload = {
            "message_type": message_type,
            id_field: target_id,
            "message": message,
        }
        url = config.NAP_HTTP.rstrip("/") + "/send_msg"
        headers = {}
        if config.NAP_TOKEN:
            headers["Authorization"] = f"Bearer {config.NAP_TOKEN}"
        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=10)
        except Exception:
            log.exception("send_msg request failed")
            return
        if resp.status_code != 200:
            log.error("send_msg failed: %s %s", resp.status_code, resp.text)

    def _on_message(self, _ws, raw):
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return
        if "post_type" not in data:
            return
        msg_id = data.get("message_id")
        if msg_id is not None:
            if msg_id in self._seen_ids:
                log.debug("duplicate msg_id ignored: %s", msg_id)
                return
            self._seen_ids.append(msg_id)
        if data.get("post_type") == "message":
            raw_text = ""
            msg = data.get("message")
            if isinstance(msg, list):
                for seg in msg:
                    if seg.get("type") == "text":
                        raw_text += seg.get("data", {}).get("text", "")
            elif isinstance(msg, str):
                raw_text = msg
            content_key = json.dumps({
                "u": data.get("user_id"),
                "g": data.get("group_id"),
                "t": raw_text.strip(),
                "m": data.get("message_type"),
            }, sort_keys=True)
            h = hashlib.md5(content_key.encode()).hexdigest()
            now = time.time()
            for ts, old_h in self._seen_content:
                if old_h == h and now - ts < self._dedup_window:
                    log.debug("duplicate content ignored: hash=%s", h)
                    return
            self._seen_content.append((now, h))
        self._dispatch(data)

    def _on_error(self, _ws, error):
        log.error("WS error: %s", error, exc_info=True)

    def _on_close(self, _ws, close_status_code, close_msg):
        log.warning("WS closed (%s)", close_status_code)

    def _on_open(self, _ws):
        log.info("WS connected")

    def _run_ws(self):
        headers = {}
        if config.NAP_WS_TOKEN:
            headers["Authorization"] = f"Bearer {config.NAP_WS_TOKEN}"
        self.ws = websocket.WebSocketApp(
            config.NAP_WS,
            header=headers,
            on_open=self._on_open,
            on_message=self._on_message,
            on_error=self._on_error,
            on_close=self._on_close,
        )
        self.ws.run_forever(reconnect=3)

    def start(self):
        self._running = True
        self._thread = threading.Thread(target=self._run_ws, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False
        if self.ws:
            self.ws.close()
