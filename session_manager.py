import threading
import time
from datetime import datetime, timedelta

from . import config
from .logger import get_logger

log = get_logger(__name__)


class SessionManager:
    def __init__(self):
        self._sessions = {}
        self._start_cleanup_thread()

    def _session_key(self, user_id, group_id=None):  #这里一定要写None，作用是赋默认值。在函数语法中，赋默认值则输入可有可无，若不赋值则一定要有一个输入
        return f"group_{group_id}_user_{user_id}" if group_id else f"private_{user_id}"

    def get_context(self, user_id, group_id=None):
        key = self._session_key(user_id, group_id)
        session = self._sessions.get(key)  #检查上下文是否存在，不存在则创建并加入字典
        if not session:
            session = {
                "messages": [],
                "round": 0,
                "last_active": time.time(),
            }
            self._sessions[key] = session  #这个字典在初始化就创建了
        else:
            session["last_active"] = time.time()
        return session

    def add_message(self, user_id, role, content, group_id=None, images=None):
        session = self.get_context(user_id, group_id)
        if role == "user":
            if session["round"] >= config.MAX_ROUNDS:
                idx = None
                for i, m in enumerate(session["messages"]):
                    if m["role"] == "user":
                        idx = i
                        break
                if idx is not None:
                    del session["messages"][idx:idx+2]
            else:
                session["round"] += 1
        msg = {"role": role, "content": content}
        if images:
            msg["images"] = images
        session["messages"].append(msg)
        return session

    def get_recent_images(self, user_id, group_id=None, count=10):
        session = self.get_context(user_id, group_id)
        urls = []
        for msg in reversed(session["messages"][-count:]):
            for url in msg.get("images", []):
                if url not in urls:
                    urls.append(url)
        return urls

    def reset(self, user_id, group_id=None):
        key = self._session_key(user_id, group_id)
        self._sessions.pop(key, None)

    def cleanup_expired(self):
        now = time.time()
        ttl = config.SESSION_TTL_DAYS * 86400
        expired = [k for k, v in self._sessions.items()
                   if now - v.get("last_active", 0) > ttl]
        for k in expired:
            del self._sessions[k]
        if expired:
            log.info("cleanup_expired: removed %d stale sessions", len(expired))

    def _start_cleanup_thread(self):
        t = threading.Thread(target=self._cleanup_loop, daemon=True)
        t.start()

    def _cleanup_loop(self):
        while True:
            now = datetime.now()
            next_midnight = (now + timedelta(days=1)).replace(
                hour=0, minute=0, second=0, microsecond=0)
            sleep_seconds = (next_midnight - now).total_seconds()
            time.sleep(sleep_seconds)
            self.cleanup_expired()
