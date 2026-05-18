import os

API_KEY = os.getenv("MIMO_API_KEY")
API_URL = "https://token-plan-cn.xiaomimimo.com/v1/chat/completions"

DEFAULT_MODEL = "mimo-v2.5-pro"
VISION_MODEL = "mimo-v2-omni"
TASKS_FILE = "tasks.json"

NAP_WS = "ws://127.0.0.1:3001"
NAP_HTTP = "http://127.0.0.1:3000"
NAP_TOKEN = os.getenv("NAP_TOKEN", "")
NAP_WS_TOKEN = os.getenv("NAP_WS_TOKEN", "")

TAVILY_API_KEY = os.getenv("TAVILY_API_KEY")

BOT_QQ = os.getenv("BOT_QQ", "3361591334")

MAX_ROUNDS = 20
SESSION_TTL_DAYS = 5
