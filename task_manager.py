import json
import os
import threading
import time
import uuid
from datetime import datetime

from .logger import get_logger

log = get_logger(__name__)

TASKS_FILE = "tasks.json"


class Task:
    def __init__(self, task_type, content, user_id, group_id, message_type,
                 seconds=None, trigger_at=None, interval_seconds=None):
        self.id = str(uuid.uuid4())[:8]
        self.type = task_type
        self.content = content
        self.user_id = user_id
        self.group_id = group_id
        self.message_type = message_type
        self.created_at = time.time()
        self.active = True
        self.interval_seconds = interval_seconds

        if task_type == "countdown" and seconds is not None:
            self.next_trigger = time.time() + seconds
        elif task_type == "temporary" and trigger_at is not None:
            if isinstance(trigger_at, str):
                self.next_trigger = datetime.fromisoformat(trigger_at).timestamp()
            else:
                self.next_trigger = trigger_at
        elif task_type == "long_term" and interval_seconds is not None:
            self.next_trigger = time.time() + interval_seconds
        else:
            self.next_trigger = None

    def to_dict(self):
        return {
            "id": self.id,
            "type": self.type,
            "content": self.content,
            "user_id": self.user_id,
            "group_id": self.group_id,
            "message_type": self.message_type,
            "created_at": self.created_at,
            "next_trigger": self.next_trigger,
            "interval_seconds": self.interval_seconds,
            "active": self.active,
        }

    @classmethod
    def from_dict(cls, d):
        t = cls.__new__(cls)
        t.id = d["id"]
        t.type = d["type"]
        t.content = d["content"]
        t.user_id = d["user_id"]
        t.group_id = d["group_id"]
        t.message_type = d["message_type"]
        t.created_at = d["created_at"]
        t.next_trigger = d["next_trigger"]
        t.interval_seconds = d["interval_seconds"]
        t.active = d["active"]
        return t


class TaskManager:
    def __init__(self, napcat_client):
        self.nc = napcat_client
        self.tasks = []
        self._lock = threading.Lock()
        self._load()
        self._start_worker()

    def _load(self):
        if not os.path.exists(TASKS_FILE):
            return
        try:
            with open(TASKS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            with self._lock:
                self.tasks = [Task.from_dict(t) for t in data if t.get("active")]
            log.info("loaded %d active tasks", len(self.tasks))
        except Exception:
            log.exception("load tasks failed")

    def _save(self):
        try:
            with self._lock:
                data = [t.to_dict() for t in self.tasks if t.active]
            with open(TASKS_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception:
            log.exception("save tasks failed")

    def create_task(self, task_type, content, user_id, group_id, message_type,
                    seconds=None, trigger_at=None, interval_seconds=None):
        task = Task(task_type, content, user_id, group_id, message_type,
                    seconds, trigger_at, interval_seconds)
        with self._lock:
            self.tasks.append(task)
        self._save()
        log.info("task created: %s type=%s content=%s", task.id, task_type, content[:30])
        return task

    def delete_task(self, task_id):
        with self._lock:
            for t in self.tasks:
                if t.id == task_id:
                    t.active = False
                    break
        self._save()

    def _start_worker(self):
        t = threading.Thread(target=self._worker_loop, daemon=True)
        t.start()
        log.info("task worker started")

    def _worker_loop(self):
        while True:
            now = time.time()
            due = []
            with self._lock:
                for t in self.tasks:
                    if t.active and t.next_trigger is not None and t.next_trigger <= now:
                        due.append(t)
            for t in due:
                self._execute_task(t)
            time.sleep(1)

    def _execute_task(self, task):
        target_id = task.user_id if task.message_type == "private" else task.group_id
        try:
            self.nc.send_message(task.message_type, target_id,
                                 f"[定时提醒] {task.content}")
            log.info("task triggered: %s -> %s", task.id, task.content[:30])
        except Exception:
            log.exception("task execute failed")

        if task.type == "long_term" and task.interval_seconds:
            task.next_trigger = time.time() + task.interval_seconds
            self._save()
        else:
            task.active = False
            self._save()
