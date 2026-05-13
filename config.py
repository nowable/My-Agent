import os

API_KEY = os.getenv("MIMO_API_KEY")
API_URL = "https://token-plan-cn.xiaomimimo.com/v1/chat/completions"

DEFAULT_MODEL = "mimo-v2.5-pro"
AUTOSAVE_DIR = "responses"  # 自动保存目录

NAP_WS = "ws://127.0.0.1:3001"   # NAP WebSocket 地址
NAP_HTTP = "http://127.0.0.1:3000"   # NAP HTTP 地址
NAP_TOKEN = os.getenv("NAP_TOKEN", "123456789012")   # NAP HTTP 令牌
NAP_WS_TOKEN = os.getenv("NAP_WS_TOKEN", "")   # NAP WebSocket 令牌

TAVILY_API_KEY = os.getenv("TAVILY_API_KEY")

MAX_ROUNDS = 20   # 最大轮数
SESSION_TTL_DAYS = 5   # 会话闲置自动删除天数

os.makedirs(AUTOSAVE_DIR, exist_ok=True)   # 确保自动保存目录存在
