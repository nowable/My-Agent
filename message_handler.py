from . import llm_api
from .logger import get_logger
from .react_engine import ReActEngine
from .session_manager import SessionManager

log = get_logger(__name__)


class MessageHandler:
    def __init__(self, napcat_client, task_manager=None):
        self.nc = napcat_client
        self.tm = task_manager
        self.sessions = SessionManager()
        self.nc.on_event(self._handle_event)

    @staticmethod
    def _extract_text(event: dict) -> str:
        msg = event.get("message")
        if isinstance(msg, list):
            parts = []
            for seg in msg:
                if seg.get("type") == "text":
                    parts.append(seg.get("data", {}).get("text", ""))
            return "".join(parts).strip()
        raw = event.get("raw_message")
        if raw:
            return raw.strip()
        return ""

    @staticmethod
    def _extract_images(event: dict):
        msg = event.get("message")
        if not isinstance(msg, list):
            return []
        urls = []
        for seg in msg:
            if seg.get("type") == "image":
                url = seg.get("data", {}).get("url", "")
                if url:
                    urls.append(url)
        return urls

    @staticmethod
    def _is_mentioned(event: dict) -> bool:
        msg = event.get("message")
        if isinstance(msg, list):
            for seg in msg:
                if seg.get("type") == "at":
                    qq = seg.get("data", {}).get("qq", "")
                    if qq == "3361591334":
                        return True
        return False

    def _handle_event(self, event: dict):
        if event.get("post_type") != "message":
            return

        msg_type = event.get("message_type")
        user_id = event.get("user_id")
        raw_msg = self._extract_text(event)
        images = self._extract_images(event)

        if not raw_msg and not images:
            return

        if msg_type == "private":
            group_id = None
            target_id = user_id
        elif msg_type == "group":
            group_id = event.get("group_id")
            target_id = group_id
            if not self._is_mentioned(event):
                self.sessions.add_message(user_id, "user", raw_msg or "[图片]", group_id, images=images)
                return
        else:
            return

        log.info("recv %s from %s%s: %s %d image(s)", msg_type, user_id,
                 f" in {group_id}" if group_id else "", raw_msg[:50], len(images))
        self._handle_message(msg_type, target_id, user_id, group_id, raw_msg, images)

    def _handle_message(self, msg_type, target_id, user_id, group_id, raw_msg, images=None):
        if raw_msg == "/reset":
            self.sessions.reset(user_id, group_id)
            self.nc.send_message(msg_type, target_id, "对话已重置", at_user_id=user_id if msg_type == "group" else None)
            return

        if not raw_msg and images:
            raw_msg = "[图片]"

        self.sessions.add_message(user_id, "user", raw_msg, group_id, images=images)

        engine = ReActEngine(self.sessions, self.nc, self.tm)
        try:
            reply = engine.run(user_id, group_id, raw_msg, images or [], msg_type, target_id)
        except Exception:
            log.exception("react engine failed")
            reply = "处理出错，请稍后重试"

        self.sessions.add_message(user_id, "assistant", reply, group_id)
        if images:
            self.sessions.add_message(user_id, "system",
                                       "[系统] 用户发了一张图片，你已查看并描述。", group_id)
        try:
            self.nc.send_message(msg_type, target_id, reply, at_user_id=user_id if msg_type == "group" else None)
        except Exception:
            log.exception("send_message failed")
