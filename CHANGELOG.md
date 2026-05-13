# CHANGELOG — 2025-05-10

## 新功能

- **task_manager.py** — 定时任务系统，支持三种任务类型：倒计时（countdown）、临时（temporary）、长期重复（long_term）；JSON 文件持久化，重启不丢失；后台 daemon 线程每秒检查到期任务
- **模型自主创建任务** — `llm_api.py` 注入 task system prompt，模型回复可携带 `<<TASK_CREATE:{...}>>` 指令；`message_handler.py` 自动解析指令创建任务，指令标签对用户不可见
- **会话闲置自动清理** — `session_manager.py` 新增 daemon 线程，每天午夜 00:00 自动删除超过 5 天未活跃的会话

## 配置变更

| 配置项 | 说明 |
|--------|------|
| `SESSION_TTL_DAYS` | 会话闲置自动删除天数，默认 `5` |

---

# CHANGELOG — 2025-05-09

## 新功能

- **napcat_client.py** — WebSocket 客户端实现，连接 NapCat 收消息 + HTTP API 发消息，支持自动重连、消息去重（`deque` 缓存 200 条 message_id）
- **message_handler.py** — 消息路由，区分私聊/群聊，支持 `/reset` 命令
- **session_manager.py** — 多会话上下文管理，按 `(user_id, group_id)` 隔离，支持 MAX_ROUNDS 滚动窗口（超出自动删最早对话）
- **logger.py** — 统一日志系统，控制台 INFO+，文件 DEBUG+，按 5MB 轮转

## 修复

- **send_message 字段名修复** — 私聊用 `user_id` 而非 `private_id`（OneBot v11 协议要求）
- **messagePostFormat: array 适配** — 增加 `_extract_text()` 从数组格式消息中提取纯文本，跳过 `reply`/`at` 等非文字段
- **WS token 分离** — NapCat HTTP 和 WebSocket 使用不同 token，增加 `NAP_WS_TOKEN` 配置
- **异常堆栈** — 所有异常捕获处改用 `log.exception()`，带上完整 traceback
- **send_message 防崩溃** — HTTP 请求加 try/except，网络不通不崩

## 行为变更

- **对话上限策略** — 从"阻断回复"改为"自动删除最早一轮对话"，保持滑动窗口
- **群聊 @ 触发** — 群聊中只有 @机器人 才回复，直接发消息忽略
- **私聊不受影响** — 私聊直接回复，无需 @

## 配置变更

| 配置项 | 旧值 | 新值 |
|--------|------|------|
| `API_URL` | `https://api.deepseek.com/v1/chat/completions` | `https://token-plan-cn.xiaomimimo.com/v1/chat/completions` |
| `DEFAULT_MODEL` | `deepseek-chat` | `mimo-v2.5-pro` |
| `API_KEY` 来源 | `DEEPSEEK_API_KEY` | `MIMO_API_KEY` |
| `NAP_WS_TOKEN` | (无) | 从环境变量读取 |

## 部署（远程 Linux）

- 项目部署至 `/home/xingyue/DeepSeek_bot/`
- 停止 Docker 版 NapCat（`systemctl stop napcat && systemctl disable napcat`）
- 禁用 NapCat 配置中无用的 httpClients/websocketClients，消除重连报错
- `run_bot.sh` 通过环境变量注入 API Key
