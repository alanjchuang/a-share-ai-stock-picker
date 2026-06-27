# A股多因子智能选股Web系统

本项目是一个本地轻量化运行的 A 股多因子智能选股平台，前后端分离，不依赖 Docker、MySQL 或外部服务。行情财务数据源可配置，默认 `auto` 会优先使用 AKShare，失败后尝试 Tushare，最后回退演示数据，确保页面、接口、因子计算、舆情评分、自然语言解析和策略管理都能直接跑起来。

固定免责声明：本工具仅基于公开数据做 AI 量化统计，不构成任何投资建议；A 股存在高波动风险，所有盈亏由用户自行承担。

## 技术栈

- 前端：Vite、React 18、TypeScript 5、Ant Design Pro Components、ECharts、Zustand、Axios、xlsx、dayjs、lodash
- 后端：FastAPI、SQLite、AKShare、Tushare、Pandas、NumPy、APScheduler、httpx
- 配置：根目录 `config.toml`
- 数据库：`backend/data/stock_picker.sqlite3`

## 快速启动

```bash
cd /Users/bytedance/PycharmProjects/a-share-ai-stock-picker
chmod +x start.sh stop.sh
./start.sh
```

启动后访问：

- 前端：http://127.0.0.1:5173
- 后端文档：http://127.0.0.1:8000/docs

停止服务：

```bash
./stop.sh
```

## 配置说明

所有核心配置都在 `config.toml`：

- `[market_data] provider`：默认 `auto`，可选 `akshare`、`tushare`、`demo`。`auto` 会按 AKShare -> Tushare -> 演示数据顺序尝试。
- `[akshare]`：AKShare 数据源配置，包括复权方式、请求间隔、历史K线/财务/新闻/基础信息批量上限。批量全市场同步建议保留请求间隔，降低网页数据源临时限流风险。
- `[tushare] token`：使用 Tushare 时填入 token；不填 token 时 Tushare 路径会跳过或回退。
- `[llm] provider`：默认 `heuristic`，不内置任何大模型密钥。进入“系统配置”页后可切到 OpenAI 兼容、通义千问兼容或本地模型，并填写 API 地址、Key、模型和超时重试参数。
- `[llm] max_tokens`、`timeout_seconds`、`num_retries`：大模型调用的输出长度、超时和重试控制。
- `[llm] api_base`：OpenAI 兼容接口地址；配置后系统会请求 `{api_base}/chat/completions`。
- `[search]`：火山独立搜索 API 配置，不内置搜索 API Key。进入“系统配置”页填写后，请求按火山搜索接口的 `Query/SearchType/Count/Filter/NeedSummary` 结构发送。
- `[workflow] default_path`：可留空；系统会从 `workflows/` 下读取可用 workflow。也可以在“系统配置”页设置默认 workflow，并在工作台运行 AI 选股前临时选择。
- `[filters]`：全局剔除 ST、停牌、次新股阈值、最小市值。
- `[weights]`：基本面、技术、资金、舆情四维度综合 AI 评分权重。
- `[scheduler] daily_sync_cron`：默认交易日 18:30 执行本地同步任务。

大模型可选依赖：

```bash
cd backend
source .venv/bin/activate
pip install -r requirements-llm.txt
```

## 功能模块

### 1. 指数筛选引擎

支持沪深300、中证500、中证1000、上证50、创业板指、科创50、北证50，以及申万行业和 AI、半导体、储能、军工、医药等概念赛道。可按成分股、N 日相对指数超额收益、PE/PB 估值分位、赛道动量 Top N 进行过滤。

### 2. 多因子量化系统

后端 `app/services/factor_engine.py` 会批量计算并缓存：

- 基本面：PE(TTM)、PB、PEG、ROE、毛利率、净利率、营收同比、扣非净利润增速、资产负债率、经营现金流、股息率、市值、商誉占比
- 技术：MA5/10/20/60/120、MACD、KDJ、RSI、BOLL、ATR、换手率、振幅、N 日涨跌幅、量比、筹码获利比例、涨停频次
- 资金：北向持仓/流入、主力净流入、融资余额变化、机构持仓占比、龙虎榜评分
- 评分：四维度归一化 0-100，并按配置权重生成 AI 综合评分和 A/B/C/D 评级

### 3. LLM 财经新闻和公告舆情

后端 `app/services/sentiment_service.py` 提供统一舆情打分接口：

- 80-100：重大利好
- 60-79：普通利好
- 40-59：中性
- 20-39：普通利空
- 0-19：重大利空

默认内置关键词规则，可配置 OpenAI/通义千问等兼容 Chat Completions 的服务。筛选支持近 N 日平均分、关键词白名单、关键词黑名单和利空占比过滤。

### 4. 自然语言 AI 选股解析

后端 `app/services/stock_selection_workflow.py` 提供可配置大模型选股 workflow。Workflow 文件放在 `workflows/` 目录，前端工作台会读取列表让用户选择；系统配置页也可设置默认 workflow。它参考 AgentLoom 的分阶段编排思路，把一次“大模型选股”拆成：

1. 自然语言条件解析
2. 条件校验与规则补强
3. 多因子确定性筛选
4. 火山搜索实时资料检索
5. 候选股大模型复核

旧的 `app/services/nl_parser.py` 仍作为规则兜底使用。用户在前端工作台输入自然语言条件后，系统会自动转换为指数、基本面、资金、舆情和市值过滤条件，并一键执行。

Workflow 步骤可在 TOML 中开关、改提示词、调整候选数量。例如：

```toml
[[steps]]
id = "web_research"
type = "web_search"
enabled = true
query_template = "{{user_text}} A股 最新 政策 财报 舆情 新闻 候选股：{{candidate_names}}"

[[steps]]
id = "candidate_reviewer"
type = "llm_candidate_review"
enabled = true
candidate_limit = 20
```

## 页面说明

- 选股工作台：左侧多条件筛选，顶部自然语言输入，结果表格、Excel 导出、K线、因子雷达、行业分布、舆情直方图
- 个股详情：基础信息、关键财务指标、120 日 K 线、新闻列表、LLM 舆情标签、四维度因子雷达、AI 评级
- 策略管理：保存、编辑、删除、执行策略，展示策略选股数量、平均得分、平均涨幅对比
- 系统配置：数据源选择、AKShare/Tushare 参数、LLM API、火山搜索 API、全局过滤规则、评分权重、调度配置、缓存重算

## 后端接口

统一返回体：

```json
{
  "code": 0,
  "message": "ok",
  "data": {}
}
```

核心接口：

- `GET /api/health`
- `GET /api/meta/indices`
- `POST /api/sync/run`
- `POST /api/factors/calculate`
- `POST /api/screener/run`
- `POST /api/ai/parse`
- `GET /api/ai/workflows`
- `POST /api/ai/search`
- `POST /api/ai/stock-selection-workflow`
- `POST /api/ai/sentiment/analyze`
- `GET /api/stocks/{ts_code}`
- `GET /api/strategies`
- `POST /api/strategies`
- `PUT /api/strategies/{id}`
- `DELETE /api/strategies/{id}`
- `GET /api/config`
- `PUT /api/config`

## 目录结构

```text
a-share-ai-stock-picker/
  config.toml
  start.sh
  stop.sh
  README.md
  workflows/
    stock_selection.toml
  backend/
    requirements.txt
    requirements-llm.txt
    app/
      main.py
      core/
      db/
        schema.sql
        seed.py
      models/
      routers/
      services/
      utils/
  frontend/
    package.json
    vite.config.ts
    src/
      api/
      components/
      layout/
      pages/
      router/
      store/
      styles/
      types/
```

## 扩展入口

- 新增指标：在 `backend/app/services/factor_engine.py` 增加字段计算和评分权重，在 `frontend/src/types/index.ts` 与表格列中展示。
- 新增指数：写入 `index_info` 与 `index_members`，或扩展 `backend/app/services/akshare_service.py` / `backend/app/services/tushare_service.py` 的指数映射。
- 切换大模型：修改 `config.toml` 的 `[llm]`，或在 `sentiment_service.py` 和 `nl_parser.py` 中扩展 provider。
- 切换搜索源：修改 `config.toml` 的 `[search]`，或扩展 `backend/app/services/web_search_service.py`，workflow 中的 `web_search` 步骤会自动复用。
- 扩展新闻源：在 `akshare_service.py` 或 `tushare_service.py` 新增源数据落库到 `stock_news`，舆情刷新会自动复用统一打分接口。

## 数据源切换示例

使用 AKShare：

```toml
[market_data]
provider = "akshare"

[akshare]
enabled = true
adjust = "qfq"
request_interval_seconds = 0.4
```

使用 Tushare：

```toml
[market_data]
provider = "tushare"

[tushare]
enabled = true
token = "你的Tushare Token"
```

使用火山搜索：

```toml
[search]
enabled = true
base_url = "https://open.feedcoopapi.com/search_api/web_search"
api_key = "你的火山搜索API Key"
model = "volc-search"
timeout_seconds = 30
default_count = 8
```

也可以在系统配置页直接切换，保存后点击“同步行情”即可。
