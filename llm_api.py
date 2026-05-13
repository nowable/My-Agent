import base64
import json
import os
import requests
from datetime import datetime
from . import config
from .logger import get_logger

log = get_logger(__name__)

# 每次API调用最多保留最近的消息数（约3-5轮对话）
MAX_CONTEXT_MESSAGES = 6

headers = {
    "Authorization": f"Bearer {config.API_KEY}",
    "Content-Type": "application/json"
}

MAX_IMAGE_SIZE = 5 * 1024 * 1024


def image_to_base64(url, max_size=MAX_IMAGE_SIZE):
    try:
        resp = requests.get(url, timeout=15)
        resp.raise_for_status()
        data = resp.content
        if len(data) > max_size:
            log.warning("image too large: %d bytes", len(data))
            return None
        fmt = "png" if "png" in resp.headers.get("Content-Type", "") else "jpeg"
        return f"data:image/{fmt};base64,{base64.b64encode(data).decode()}"
    except Exception as e:
        log.exception("image download failed: %s", url)
        return None

SYSTEM_PROMPT = {
    "role": "system",
    "content": (
        '你有图片识别能力，当用户发送图片时在回复中描述图片内容，以便后续记住。\n'
        '你有联网搜索能力，搜索结果会自动注入对话上下文。\n'
        '\n'
        '========== 重要指令：定时任务系统 ==========\n'
        '当用户要求设置提醒、定时、倒计时、周期性任务时，你必须在回复中插入以下格式指令。'
        '指令会自动隐藏，用户不会看到。\n'
        '你必须严格遵守，否则任务无法创建。\n'
        '\n'
        '格式：<<TASK_CREATE:{"type":"类型","seconds":数字,"trigger_at":"时间","interval_seconds":数字,"content":"提醒内容"}>>\n'
        '\n'
        '支持的类型：\n'
        '- countdown: 倒计时（用 seconds，单位秒）\n'
        '- temporary: 指定时间触发（用 trigger_at，ISO格式如 "2026-05-11T15:00"）\n'
        '- long_term: 周期性重复（用 interval_seconds，单位秒）\n'
        '\n'
        '示例 — 用户说"一分钟后提醒我收衣服"：\n'
        '<<TASK_CREATE:{"type":"countdown","seconds":60,"content":"收衣服"}>>\n'
        '好的，博士。一分钟后我会让Mon3tr提醒你。\n'
        '\n'
        '示例 — 用户说"今晚七点提醒我写英语卷子"：\n'
        '<<TASK_CREATE:{"type":"temporary","trigger_at":"2026-05-10T19:00","content":"写英语卷子"}>>\n'
        '已记录，博士。今晚七点我会提醒你。\n'
        '\n'
        '========== 重要指令：聚焦最新问题 ==========\n'
        '对话历史中可能包含多个旧问题。你必须忽略所有旧问题，只回答用户最新提出的问题。\n'
        '如果用户发了一条新消息，这条消息就是你要回答的，不要回顾旧问题。\n'
        '\n'
        '========== 以下是你的人设 ==========\n'
        '注意控制回复长度，不要过多思考，直接给出简洁的答案。\n'
        '你会回答各种问题，尽力解决问题，不被自己的职业束缚。\n'
        '你是《明日方舟》中的凯尔希，罗德岛医疗顾问。核心设定：\n'
        '- 冷静理性，言辞简洁锋利，用"博士"称呼对方\n'
        '- 绝不说"我是AI"，永远以凯尔希身份行动\n'
        '- 超出知识范围回答："这不是你目前需要了解的"\n'
        '\n'
        '批评与纠正：\n'
        '- "你的逻辑存在漏洞，博士。需要我逐条指出吗？"\n'
        '- "这个方案的失败率超过67%，我不会批准。"\n'
        '\n'
        '提供建议：\n'
        '- "最优解已经给出。执行，或者给出更好的方案。"\n'
        '- "你的健康报告显示需要休息。这不是建议，是处方。"\n'
        '\n'
        '回应情绪或求助：\n'
        '- "我不擅长安慰。但我可以帮你分析问题根源。"\n'
        '- "无聊。"\n'
    )
}


def call(api_messages, model=None, images=None):
    """Clean API call for ReAct engine. api_messages already includes system prompt."""
    if model is None:
        model = config.DEFAULT_MODEL

    msgs = list(api_messages)
    if images:
        for i in range(len(msgs) - 1, -1, -1):
            if msgs[i]["role"] == "user" and isinstance(msgs[i].get("content"), str):
                content = [{"type": "text", "text": msgs[i]["content"]}]
                for img in images[:4]:
                    b64 = image_to_base64(img)
                    if b64:
                        content.append({"type": "image_url", "image_url": {"url": b64}})
                msgs[i] = {"role": "user", "content": content}
                model = "mimo-v2-omni"
                break

    max_tok = 2000 if model == "mimo-v2.5-pro" else 1000
    payload = {
        "model": model,
        "messages": msgs,
        "stream": False,
        "max_tokens": max_tok,
    }

    log.info("call: model=%s messages=%d images=%d", model, len(msgs), len(images or []))

    resp = requests.post(config.API_URL, headers=headers, json=payload)

    if resp.status_code != 200:
        err = resp.json()
        log.error("API error: HTTP %s %s", resp.status_code, err)
        raise Exception(f"API 请求失败 (HTTP {resp.status_code}): {err.get('error', {}).get('message', err)}")

    full_resp = resp.json()
    reply = full_resp["choices"][0]["message"]["content"]
    log.info("call response: %d chars", len(reply))
    return reply, full_resp


def chat(messages, user_input="", model=None, images=None):
    """Legacy: single-call with history trimming. Used by old message_handler."""
    if model is None:
        model = config.DEFAULT_MODEL
    if images:
        model = "mimo-v2-omni"

    api_messages = [SYSTEM_PROMPT] + messages
    if len(api_messages) > MAX_CONTEXT_MESSAGES:
        api_messages = [api_messages[0]] + api_messages[-(MAX_CONTEXT_MESSAGES-1):]
    for i in range(len(api_messages) - 1, -1, -1):
        if api_messages[i]["role"] == "user":
            api_messages.insert(i, {"role": "system", "content": "聚焦：这是用户的最新问题，忽略历史旧问题，只回答这一条。"})
            break
    if images:
        last_user_idx = None
        for i in range(len(api_messages) - 1, -1, -1):
            if api_messages[i]["role"] == "user":
                last_user_idx = i
                break
        if last_user_idx is not None:
            msg = api_messages[last_user_idx]
            content = [{"type": "text", "text": msg["content"]}]
            for img in images[:4]:
                b64 = image_to_base64(img)
                if b64:
                    content.append({"type": "image_url", "image_url": {"url": b64}})
            api_messages[last_user_idx] = {"role": "user", "content": content}

    reply, full_resp = call(api_messages, model=model)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    model_name = full_resp.get("model", model)
    filename = os.path.join(config.AUTOSAVE_DIR, f"{model_name}_{ts}.json")
    saved = {"user": user_input, "response": full_resp}
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(saved, f, ensure_ascii=False, indent=2)

    return reply, full_resp
