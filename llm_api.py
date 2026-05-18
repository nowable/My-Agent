import base64
import requests

from . import config
from .logger import get_logger

log = get_logger(__name__)

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
    except Exception:
        log.exception("image download failed: %s", url)
        return None


def call(api_messages, model=None, images=None):
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
                model = config.VISION_MODEL
                break

    max_tok = 2000 if model == config.DEFAULT_MODEL else 1000
    payload = {
        "model": model,
        "messages": msgs,
        "stream": False,
        "max_tokens": max_tok,
    }

    log.info("call: model=%s messages=%d images=%d", model, len(msgs), len(images or []))

    resp = requests.post(config.API_URL, headers=headers, json=payload, timeout=30)

    if resp.status_code != 200:
        err = resp.json()
        log.error("API error: HTTP %s %s", resp.status_code, err)
        raise Exception(f"API 请求失败 (HTTP {resp.status_code}): {err.get('error', {}).get('message', err)}")

    full_resp = resp.json()
    reply = full_resp["choices"][0]["message"]["content"]
    log.info("call response: %d chars", len(reply))
    return reply, full_resp
