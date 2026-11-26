"""Pushes alerts to staff phones. Non-blocking: sends happen on a worker thread.

ALERT_WEBHOOK_URL   -> JSON POST (point it at an n8n Webhook node -> WhatsApp / Telegram / SMS / Slack)
TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID -> direct Telegram message (no n8n needed)
"""
from __future__ import annotations

import base64
import json
import logging
import uuid
import os
import queue
import threading
import urllib.parse
import urllib.request

log = logging.getLogger("notifier")

ICON = {"service_wait": "🕔 SERVICE", "uncleaned_table": "🧹 CLEANING", "camera_offline": "📷 CAMERA"}


class Notifier:
    def __init__(self, name_fn=None) -> None:
        self.name_fn = name_fn
        self.webhook = os.getenv("ALERT_WEBHOOK_URL", "").strip()
        self.tg_token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
        self.tg_chat = os.getenv("TELEGRAM_CHAT_ID", "").strip()
        self.restaurant = os.getenv("RESTAURANT_NAME", "Restaurant")
        self.enabled = bool(self.webhook or (self.tg_token and self.tg_chat))
        self._q: queue.Queue = queue.Queue(maxsize=200)
        if self.enabled:
            threading.Thread(target=self._worker, daemon=True, name="notifier").start()
            log.info("alert notifications enabled (webhook=%s telegram=%s)",
                     bool(self.webhook), bool(self.tg_token))

    def send(self, event: str, alert: dict) -> None:
        """event: 'alert' | 'resolved'"""
        if not self.enabled:
            return
        try:
            self._q.put_nowait((event, alert))
        except queue.Full:
            log.warning("notification queue full, dropping")

    def _worker(self) -> None:
        while True:
            event, a = self._q.get()
            if self.name_fn:
                self.restaurant = self.name_fn()
            if event == "report":
                self._deliver_report(a)
                continue
            text = (f"{ICON.get(a['kind'], '⚠️')} ALERT · {self.restaurant}\n{a['message']}"
                    if event == "alert" else f"✅ Resolved · {a['table']} ({a['kind']})")
            if self.webhook:
                self._post(self.webhook, {"event": event, "restaurant": self.restaurant,
                                          "text": text, **a})
            if self.tg_token and self.tg_chat and event == "alert":
                self._post(f"https://api.telegram.org/bot{self.tg_token}/sendMessage",
                           {"chat_id": self.tg_chat, "text": text})

    def send_report(self, text: str, pdf: bytes | None, filename: str) -> bool:
        """Queue the weekly report. Returns False when no channel is configured."""
        if not self.enabled:
            return False
        self._q.put(("report", {"text": text, "pdf": pdf, "filename": filename}))
        return True

    def _deliver_report(self, r: dict) -> None:
        if self.webhook:
            self._post(self.webhook, {
                "event": "weekly_report", "restaurant": self.restaurant, "text": r["text"],
                "filename": r["filename"],
                "pdf_base64": base64.b64encode(r["pdf"]).decode() if r["pdf"] else None})
        if self.tg_token and self.tg_chat:
            base = f"https://api.telegram.org/bot{self.tg_token}"
            self._post(f"{base}/sendMessage", {"chat_id": self.tg_chat, "text": r["text"]})
            if r["pdf"]:
                boundary = uuid.uuid4().hex
                parts = [f'--{boundary}\r\nContent-Disposition: form-data; name="chat_id"\r\n\r\n{self.tg_chat}\r\n'.encode(),
                         f'--{boundary}\r\nContent-Disposition: form-data; name="document"; filename="{r["filename"]}"\r\n'
                         f'Content-Type: application/pdf\r\n\r\n'.encode(), r["pdf"],
                         f'\r\n--{boundary}--\r\n'.encode()]
                try:
                    req = urllib.request.Request(f"{base}/sendDocument", data=b"".join(parts), method="POST",
                                                 headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
                    urllib.request.urlopen(req, timeout=20).read()
                except Exception as e:
                    log.warning("telegram document failed: %s", e)

    @staticmethod
    def _post(url: str, payload: dict) -> None:
        try:
            req = urllib.request.Request(url, data=json.dumps(payload).encode(),
                                         headers={"Content-Type": "application/json"}, method="POST")
            urllib.request.urlopen(req, timeout=8).read()
        except Exception as e:  # never let a failed push break the pipeline
            log.warning("notification failed: %s", urllib.parse.urlparse(url).netloc or e)
