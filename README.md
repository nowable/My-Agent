# llm_bot

基于 NapCat 的 QQ 机器人，接入 LLM API，支持联网搜索、定时任务、多会话管理。

## 架构

```
NapCat (QQ 客户端)  ←WS/HTTP→  llm_bot  →  LLM API
                                    ↓
                             Tavily Search API
```

## 技术栈

- Python 3.10+
- `requests` / `websocket-client`
- NapCat (OneBot v11)
- LLM API (兼容 OpenAI 格式)

## 模块

| 模块 | 职责 |
|------|------|
| `napcat_client` | NapCat WebSocket 收消息 + HTTP 发消息，自动重连，消息去重 |
| `message_handler` | 消息路由，私聊/群聊分流，调用 ReAct 引擎 |
| `react_engine` | ReAct 循环引擎：Thought → Action → Observation，支持 search/recall_images/create_task 三种工具 |
| `llm_api` | LLM API 封装，支持文本和图片输入 |
| `session_manager` | 多会话隔离，按 `(user_id, group_id)` 存储上下文，自动清理过期会话 |
| `task_manager` | 定时任务系统（倒计时/指定时间/周期性），JSON 持久化 |
| `web_search` | 通过 Tavily API 搜索网络 |
| `logger` | 统一日志，控制台 INFO+，文件 DEBUG+，5MB 轮转 |

## 原理流程

```
用户发消息
    ↓
NapCat 收到 → WS 推送 → napcat_client
    ↓
message_handler 路由
    ├─ 私聊 → 直接处理
    └─ 群聊 → 需 @机器人
    ↓
react_engine (ReAct 循环)
    ├─ Thought: 模型思考需要什么工具
    ├─ Action: search / recall_images / create_task
    ├─ Observation: 工具返回结果
    └─ Finish: 生成最终回复
    ↓
napcat_client HTTP POST → NapCat → 用户收到回复
```

## 快速开始

```bash
pip install -r requirements.txt

export MIMO_API_KEY=your_key
export TAVILY_API_KEY=your_key   # 可选，联网搜索
export NAP_WS_TOKEN=your_token   # NapCat WebSocket token
export NAP_TOKEN=your_token      # NapCat HTTP token

python -m llm_bot.main
```

## 配置

环境变量 | 说明
---|---
`MIMO_API_KEY` | LLM API 密钥
`TAVILY_API_KEY` | Tavily 搜索 API 密钥（可选）
`NAP_WS_TOKEN` | NapCat WebSocket token
`NAP_TOKEN` | NapCat HTTP token
