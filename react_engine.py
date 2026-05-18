import re

from . import config
from . import llm_api
from . import web_search
from .logger import get_logger

log = get_logger(__name__)

REACT_SYSTEM_PROMPT = (
    '你是《明日方舟》中的凯尔希，罗德岛医疗顾问。冷静理性，言辞简洁锋利，用"博士"称呼对方。\n'
    '绝不说"我是AI"。超出知识范围回答："这不是你目前需要了解的"。\n'
    '\n'
    '你通过一步步思考和行动来解决问题。\n'
    '每次输出必须包含Thought和Action：\n'
    '\n'
    'Thought: [你对当前情况的思考，决定下一步做什么]\n'
    'Action: [工具名(参数="值")]\n'
    '\n'
    '可用工具：\n'
    '- search(query: str): 搜索网络获取实时信息\n'
    '- recall_images(count: int): 从对话历史中找回最近几张图片（默认5张）\n'
    '- create_task(type: str, content: str, seconds: int=0, trigger_at: str="", interval_seconds: int=0): 创建定时提醒\n'
    '  支持的类型：countdown(倒计时，用seconds), temporary(指定时间，用trigger_at ISO格式), long_term(周期性，用interval_seconds)\n'
    '\n'
    '完成任务后输出：\n'
    'Action: Finish[你的回答]\n'
    '\n'
     '规则：\n'
     '- 每次只执行一个Action，等待Observation后再继续\n'
     '- 如果用户要求看图片但没有图片可用，告知用户没有找到图片\n'
     '- 不要编造信息，必要时使用search工具\n'
     '- 如果用户只是打招呼、闲聊或无需调用任何工具，直接回复：Action: Finish[你的回答]\n'
     '- **重要：如果用户要求定时提醒（如"X分钟后提醒我"、"X小时后通知我"、"定时"、"倒计时"等），你必须先调用create_task创建任务，然后再回复确认。绝对不要只口头答应而不执行create_task。**\n'
)

ACTION_RE = re.compile(r'Action:\s*(\w+)\((.+)\)')
FINISH_RE = re.compile(r'Action:\s*Finish\[(.+)\]', re.DOTALL)
KWARG_RE = re.compile(r'(\w+)=("[^"]*"|\d+(?:\.\d+)?)')

TIME_PATTERNS = [
    (r'(\d+)\s*分[钟钟]?\s*后\s*(?:提醒|通知|叫|告诉)', lambda m: ('countdown', int(m.group(1)) * 60)),
    (r'(\d+)\s*个小?时?\s*后\s*(?:提醒|通知|叫|告诉)', lambda m: ('countdown', int(m.group(1)) * 3600)),
    (r'(\d+)\s*秒\s*后\s*(?:提醒|通知|叫|告诉)', lambda m: ('countdown', int(m.group(1)))),
    (r'(\d+)\s*分[钟钟]?\s*(?:后|之[后以])\s*(?:叫|提醒|通知)', lambda m: ('countdown', int(m.group(1)) * 60)),
    (r'(?:提醒|通知|叫)\s*我\s*(\d+)\s*分[钟钟]?\s*后', lambda m: ('countdown', int(m.group(1)) * 60)),
    (r'(\d+)\s*秒\s*(?:后|之[后以])\s*(?:提醒|通知|叫)', lambda m: ('countdown', int(m.group(1)))),
]


def parse_time_request(text):
    for pattern, handler in TIME_PATTERNS:
        m = re.search(pattern, text)
        if m:
            return handler(m)
    return None


def parse_kwargs(text):
    kwargs = {}
    for k, v in KWARG_RE.findall(text):
        if v.startswith('"') and v.endswith('"'):
            kwargs[k] = v[1:-1]
        elif '.' in v:
            kwargs[k] = float(v)
        else:
            kwargs[k] = int(v)
    return kwargs


class ReActEngine:
    def __init__(self, sessions, napcat_client, task_manager):
        self.sessions = sessions
        self.nc = napcat_client
        self.tm = task_manager
        self.max_steps = 6
        self.step_timeout = 20

    def run(self, user_id, group_id, raw_msg, msg_images, msg_type, target_id):
        session = self.sessions.get_context(user_id, group_id)

        api_messages = [{"role": "system", "content": REACT_SYSTEM_PROMPT}]
        history = session["messages"][-6:]
        api_messages.extend(history)

        user_content = raw_msg if raw_msg else "[图片]"
        api_messages.append({"role": "user", "content": user_content})

        context_images = list(msg_images) if msg_images else []
        self._task_created = False
        task_backup = None

        for step in range(self.max_steps):
            model = config.VISION_MODEL if context_images else config.DEFAULT_MODEL

            log.info("react step=%d model=%s images=%d messages=%d",
                     step + 1, model, len(context_images), len(api_messages))

            try:
                reply, _ = llm_api.call(
                    api_messages, images=context_images or None, model=model
                )
            except Exception as e:
                log.exception("react step %d failed", step + 1)
                return f"处理出错: {e}"

            finish_m = FINISH_RE.search(reply)
            if finish_m:
                final = finish_m.group(1).strip()
                if not self._task_created:
                    task_backup = self._auto_create_task(user_content, user_id, group_id, msg_type)
                if task_backup:
                    final += f"\n（已设置{task_backup}后的提醒）"
                return final

            action_m = ACTION_RE.search(reply)
            if not action_m:
                log.warning("no valid action in reply, treating as final: %s", reply[:80])
                if not self._task_created:
                    task_backup = self._auto_create_task(user_content, user_id, group_id, msg_type)
                if task_backup:
                    reply += f"\n（已设置{task_backup}后的提醒）"
                return reply

            tool_name = action_m.group(1)
            args_str = action_m.group(2)
            kwargs = parse_kwargs(args_str)

            log.info("react tool=%s args=%s", tool_name, kwargs)

            if tool_name == "search":
                observation = self._tool_search(kwargs.get("query", ""))
            elif tool_name == "recall_images":
                observation = self._tool_recall_images(
                    user_id, group_id, kwargs.get("count", 5), context_images
                )
            elif tool_name == "create_task":
                observation = self._tool_create_task(
                    kwargs, user_id, group_id, msg_type
                )
            else:
                observation = f"错误: 未知工具 '{tool_name}'，可用工具: search, recall_images, create_task"

            api_messages.append({"role": "assistant", "content": reply})
            api_messages.append({"role": "user", "content": f"Observation: {observation}"})

        if not self._task_created:
            task_backup = self._auto_create_task(user_content, user_id, group_id, msg_type)
        if task_backup:
            return f"已设置{task_backup}后的提醒。"
        return "处理超时，请重试或简化你的问题。"

    def _tool_search(self, query):
        if not query:
            return "错误: search需要提供query参数"
        log.info("search: %s", query[:60])
        try:
            result = web_search.search(query)
            return f"[联网搜索结果]\n{result[:800]}"
        except Exception as e:
            return f"搜索失败: {e}"

    def _tool_recall_images(self, user_id, group_id, count, context_images):
        urls = self.sessions.get_recent_images(user_id, group_id, count=10)
        if not urls:
            return "对话历史中没有找到图片。"
        new_count = 0
        for url in urls:
            if url not in context_images:
                context_images.append(url)
                new_count += 1
        return f"已从对话历史中加载 {new_count} 张图片。"

    def _tool_create_task(self, kwargs, user_id, group_id, msg_type):
        if not self.tm:
            return "错误: 定时任务系统未启动"
        task_type = kwargs.get("type", "")
        content = kwargs.get("content", "")
        try:
            self.tm.create_task(
                task_type=task_type,
                content=content,
                user_id=user_id,
                group_id=group_id,
                message_type=msg_type,
                seconds=kwargs.get("seconds"),
                trigger_at=kwargs.get("trigger_at"),
                interval_seconds=kwargs.get("interval_seconds"),
            )
            self._task_created = True
            return f"定时任务已创建: {content[:30]}"
        except Exception as e:
            return f"创建定时任务失败: {e}"

    def _auto_create_task(self, user_content, user_id, group_id, msg_type):
        parsed = parse_time_request(user_content)
        if not parsed or not self.tm:
            return None
        task_type, seconds = parsed
        try:
            task = self.tm.create_task(
                task_type=task_type,
                content=user_content,
                user_id=user_id,
                group_id=group_id,
                message_type=msg_type,
                seconds=seconds,
            )
            self._task_created = True
            log.info("auto-created task: %s (%ds)", task.id, seconds)
            if seconds >= 3600:
                return f"{seconds//3600}小时{(seconds%3600)//60}分钟"
            elif seconds >= 60:
                return f"{seconds//60}分钟"
            else:
                return f"{seconds}秒"
        except Exception as e:
            log.exception("auto-create task failed")
            return None
