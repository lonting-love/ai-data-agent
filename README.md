# 智能数据查询与可视化 Agent

基于 LangChain 1.x `create_agent` + LangGraph 的人机协同数据分析助手：自然语言 → SQL → 结果 → Plotly 图表，带 SQL 审批、只读沙箱、幂等确认、链路追踪与离线评测。

## 架构

```
Streamlit 前端
   │  POST /chat (query / confirmed / action_id)
   ▼
FastAPI 后端 ── 会话锁 + 幂等键 + 可选 API Key 鉴权
   │
   ├─ Schema 检索（Chroma+BGE，缺依赖自动降级为中文 bigram 词法检索）
   │
   ├─ LangGraph Agent（AsyncSqliteSaver 持久化，interrupt_before=["tools"]）
   │     ├─ execute_sql_tool → SQLite 只读连接 + authorizer + 超时 + 200 行上限
   │     └─ plot_chart_tool  → charts/*.html，经 /charts 静态目录回传
   │
   └─ logs/trace.jsonl（trace_id、SQL、耗时、token）
```

## 功能

- **人在回路**：任何 SQL 执行前暂停并展示语句，用户确认后才运行；取消可清空会话。
- **只读沙箱**：`mode=ro` URI + SQLite authorizer（仅 SELECT/READ/FUNCTION）+ 注释剥离 + 多语句拦截 + 5 秒进度回调中断 + 结果硬截断。
- **幂等确认**：`action_id` + 会话级 `asyncio.Lock`，重复点击不会重复执行 SQL。
- **检索降级**：未安装 Chroma/BGE 时自动使用词法检索（中文二字组 + 领域同义词），服务照常启动。
- **图表回显**：Plotly 输出到 `charts/`，前端用 iframe 渲染，不再只返回一个本地路径。
- **可观测性**：每条请求生成 `trace_id`，JSONL 记录 schema 命中、SQL、耗时、行数、token 用量。
- **评测**：`eval/questions.jsonl` 黄金问题集，统计成功率、P50/P95 延迟与 token。

## 快速开始

```bash
# 1. 安装核心依赖
python -m venv .venv
.venv\Scripts\activate          # Windows
pip install -r requirements.txt

# 2. 可选：启用向量检索
pip install -r requirements-optional.txt

# 3. 配置密钥
copy .env.example .env          # 填入 DEEPSEEK_API_KEY

# 4. 生成示例数据（21 张表）
python generate_sample_data.py

# 5. 启动后端
uvicorn backend:app --reload --port 8000

# 6. 另开终端启动前端
streamlit run frontend.py
```

## 配置项（.env）

| 变量 | 默认 | 说明 |
| --- | --- | --- |
| `DEEPSEEK_API_KEY` | 必填 | 模型密钥 |
| `DEEPSEEK_BASE_URL` | `https://api.deepseek.com` | OpenAI 兼容网关 |
| `DEEPSEEK_MODEL` | `deepseek-chat` | 模型名 |
| `APP_API_KEY` | 空 | 非空时 `/chat` 需要 `X-API-Key` 头 |
| `SQL_ROW_LIMIT` | `200` | 单次查询返回行上限 |
| `SQL_TIMEOUT_SECONDS` | `5` | SQL 执行超时 |
| `MAX_AUTO_RESUMES` | `10` | 单轮自动恢复工具次数 |

## API

```bash
curl http://localhost:8000/health

curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"query":"各城市客户数量","session_id":"demo"}'
# → {"requires_confirmation":true,"pending_sql":"SELECT ...","trace_id":"..."}

curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"query":"各城市客户数量","session_id":"demo","confirmed":true,"action_id":"<uuid>"}'
# → {"response":"...","charts":["/charts/chart_xxx.html"],"usage":{...}}
```

## 部署与安全边界

- **单 worker 运行**：会话锁与 `action_id` 幂等都保存在进程内存，`uvicorn --workers > 1` 会失效；需要横向扩展时应换成 Redis 锁/幂等存储。
- **默认仅本机使用**：`APP_API_KEY` 留空时 `/chat` 不鉴权，请只绑定 `127.0.0.1`；对局域网开放前必须设置 `APP_API_KEY`。
- **会话 ID 即访问范围**：接口是无状态的，拿到 `session_id` 就能读取/续跑该会话；生产环境应由登录态签发并绑定用户。
- **密钥**：`.env` 已被 git 忽略，仓库只提交 `.env.example`；如果真实 key 曾经外泄，请到控制台轮换。
- **运行产物**：`charts/` 下 24 小时前的图表会在启动时清理；`logs/trace.jsonl` 超过 5MB 自动轮转为 `.1`，其中会记录 SQL 文本，分享日志前先脱敏。

## 测试与评测

```bash
python -m unittest discover -s tests -v
python eval/run_eval.py --base http://localhost:8000 --min-success 0.8
```

评测报告写入 `eval/reports/eval_*.json`，包含逐题响应预览，便于定位失败问题。

## 目录结构

```
backend.py              FastAPI 入口、审批流、幂等、静态图表服务
frontend.py             Streamlit 聊天界面
schema_store.py         向量检索 + 词法降级
execute_sql_tool.py     只读 SQL 沙箱
plot_chart_tool.py      Plotly 图表生成
prompts.py              系统提示词
action_store.py         会话锁与动作幂等
observability.py        JSONL 链路日志
config.py               环境变量与路径
generate_sample_data.py 21 张示例表数据生成
tests/                  unittest 单测
eval/                   黄金问题集 + 评测脚本
charts/                 生成的图（git 忽略）
logs/                   trace.jsonl（git 忽略）
```

## 设计取舍（面试可讲）

1. **为什么用 authorizer 而不只靠关键字拦截**：正则会被注释、大小写、函数调用绕过；`mode=ro` + authorizer 是执行层的白名单，即使模型生成 `WITH ... DELETE` 也会被拒绝。
2. **为什么确认要幂等**：LLM 生成的写操作需要人工确认，网络重试/双击可能让同一条 SQL 跑两次；用 `(session_id, action_id)` 认领，失败自动释放以便重试。
3. **为什么检索要能降级**：BGE + Chroma 首次下载模型体积大、内网常失败；降级路径保证 demo 在任何机器上都能跑，向量只作为质量增强。
4. **为什么评测按端到端成功率**：只看 SQL 语法正确率会漏掉「查错表」「图表没回显」「确认流卡死」这类真实失败。
