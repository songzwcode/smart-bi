# Smart BI 智能问数桌面应用

通过自然语言查询数据库、生成图表、输出 SQL 脚本和存储过程的**跨平台本地化桌面应用**。

## ✨ 核心特性

- 💬 **Query Mode（智能问数）**：自然语言 → 意图识别 → SQL 生成 → 执行 → 表格 + Plotly 图表
- 📝 **Script Mode（SQL 脚本）**：自然语言 → SQL/存储过程生成 → Monaco 编辑器 → 一键格式化 / 执行预览 / 导出 `.sql`
- 🔌 **多数据库支持**：SQLite / MySQL / PostgreSQL（SQLAlchemy 统一适配）
- 🤖 **多 LLM 后端**：本地 Ollama、OpenAI、Anthropic Claude、**Custom（OpenAI-兼容 HTTP 端点）**，可运行时切换
- 🛡️ **安全策略**：默认只读，禁止 DROP/ALTER 等危险操作
- 🎯 **精准识别**：Function Calling 意图分类 + Schema RAG + Plan-and-Execute + SQL 自纠
- 🖥️ **跨平台桌面**：PyWebView + PyInstaller，macOS / Windows / Linux 独立运行
- 🚫 **离线优先**：本地 LLM + 本地数据库，数据不出本机

## 📂 项目结构

```
smart-bi/
├── backend/                # Python 后端
│   ├── agent/              # 意图、规划、NL2SQL、SP 生成
│   ├── api/                # FastAPI 端点
│   ├── data/               # SQLAlchemy、Schema RAG、安全检查
│   ├── llm/                # LLM 客户端抽象（Ollama / OpenAI / Anthropic / Custom OpenAI-compatible）
│   ├── output/             # 图表、表格、SQL 格式化、导出
│   ├── server.py           # FastAPI 工厂
│   └── app.py              # PyWebView 桌面入口
├── frontend/               # React + TypeScript 前端
│   ├── src/views/          # QueryMode / ScriptMode / SettingsView
│   ├── src/components/     # ChatPanel, SqlEditor (Monaco), ChartView (Plotly), SchemaTree
│   └── src/api/            # axios 客户端
├── examples/               # 示例 SQLite + 演示查询
├── packaging/              # PyInstaller spec + 构建脚本
├── config.yaml             # 默认配置
└── pyproject.toml          # Python 依赖
```

## 🚀 快速开始

### 1. 安装依赖

```bash
# 克隆/进入项目目录
cd smart-bi

# Python 依赖（建议 Python 3.10+）
pip install -e ".[dev]"

# 生成示例数据库（SQLite）
python examples/seed_data.py

# 前端依赖
cd frontend
npm install
cd ..
```

### 2. 开发模式

需要打开两个终端：

```bash
# 终端 A：前端 dev server（5173 端口）
cd frontend
npm run dev

# 终端 B：后端 + 桌面窗口
python -m backend.app
```

桌面窗口会自动打开并加载前端。

> 想不打开桌面窗口、只用浏览器？访问 `http://127.0.0.1:17890/`（后端默认端口）。

### 3. 生产构建（构建独立桌面应用）

```bash
# 1. 先构建前端
cd frontend
npm run build         # 产物输出到 backend/static/
cd ..

# 2. 打包桌面应用（按平台选择）
bash packaging/build_macos.sh     # → dist/SmartBI.app
powershell packaging/build_windows.ps1  # → dist\SmartBI.exe
bash packaging/build_linux.sh     # → dist/SmartBI
```

> ⚠️ Linux 需要 `webkit2gtk` 系统库：`sudo apt install libwebkit2gtk-4.1-dev`

## ⚙️ 配置

主配置文件：`config.yaml`（也可用环境变量 / `.env` 覆盖）。

```yaml
llm:
  default_provider: "ollama"   # ollama | openai | anthropic
  providers:
    ollama:
      base_url: "http://localhost:11434"
      default_model: "qwen2.5-coder:14b"
    openai:
      default_model: "gpt-4o"
    anthropic:
      default_model: "claude-3-5-sonnet-20241022"

database:
  default_url: "sqlite:///examples/sample.db"
  readonly_by_default: true
  allowed_dml: ["SELECT"]      # 默认只允许 SELECT

agent:
  enable_planner: true         # 启用 Plan-and-Execute
  enable_schema_rag: true      # 启用 Schema RAG
  max_self_correct_rounds: 2   # SQL 执行失败自纠最大轮数
```

### LLM API Keys

复制 `.env.example` 为 `.env` 并填入：

```bash
cp .env.example .env
# 编辑 .env
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...
```

或者在桌面应用内 `设置 → LLM 提供方` 直接输入 key。

## 🎯 使用演示

### Query Mode 例子

> 问：**"显示销售额最高的前 10 个客户"**

Agent 会：
1. 意图分类 → `query_data`
2. 检索 Schema RAG 命中 `customers`/`orders` 表
3. LLM 生成 SQL：`SELECT ... ORDER BY total_sales DESC LIMIT 10`
4. 执行返回结果 → 表格 + 柱状图

### Script Mode 例子

> 输入：**"写一个存储过程，归档 1 年前的订单到 orders_archive 表"**

Agent 会：
1. 识别为 `generate_script`（subtype: `procedure`）
2. 读取 MySQL/PG 方言
3. LLM 生成 `CREATE PROCEDURE`（含错误处理、参数、注释）
4. 在 Monaco 编辑器中高亮显示
5. 你可以：Refine / Format / Export `.sql` / Execute Preview

## 🛠️ API 端点（高级用法）

`http://127.0.0.1:17890/api/...`

| 端点 | 方法 | 说明 |
|---|---|---|
| `/api/health` | GET | 健康检查 + 当前 LLM/DB 状态 |
| `/api/schema` | GET | 获取当前数据库 schema |
| `/api/query` | POST | Query Mode 主入口 |
| `/api/script` | POST | Script Mode 主入口 |
| `/api/script/refine` | POST | 迭代修改 SQL |
| `/api/sql/execute` | POST | 直接执行 SQL（带安全检查） |
| `/api/sql/format` | POST | sqlfluff 格式化 |
| `/api/connection/connect` | POST | 切换数据库 |
| `/api/llm/switch` | POST | 切换 LLM |

## 🐛 调试

### 启用调试模式

`config.yaml` 中：

```yaml
app:
  debug: true
```

或在 `backend/app.py` 中 `webview.start(debug=True)`。

### WebView 开发者工具

- **macOS**：`webview.start(debug=True)` 已开启；右键 → Inspect Element
- **Windows**：`webview.start(debug=True)`；F12 打开 DevTools
- **Linux**：GTK WebKit2 调试较复杂，建议用 `cd frontend && npm run dev` 在浏览器中调试

### 日志位置

- `~/.smart-bi/logs/app.log`（按 10MB 滚动，保留 7 天）
- 终端 stdout/stderr

## 🏗️ 跨平台打包详解

### macOS

```bash
bash packaging/build_macos.sh
# 输出：dist/SmartBI.app

# 签名 + 公证（可选，用于分发）
codesign --deep --force --sign "Developer ID Application: Your Name" dist/SmartBI.app
xcrun notarytool submit dist/SmartBI.zip --keychain-profile <profile> --wait
```

需要 Apple Developer 账号（$99/年）做签名公证，否则用户首次打开会看到"未知开发者"警告。

### Windows

```powershell
powershell packaging/build_windows.ps1
# 输出：dist\SmartBI.exe
```

可选：用 `signtool` 代码签名避免 SmartScreen 警告。

### Linux

```bash
bash packaging/build_linux.sh
# 输出：dist/SmartBI
# 可进一步打包为 AppImage / .deb / Flatpak
```

## 🔐 安全说明

- **默认只读**：`database.allowed_dml: ["SELECT"]`，禁止 `DROP/TRUNCATE/ALTER/DELETE/UPDATE`
- **参数化查询**：所有 SQL 走 SQLAlchemy，防 SQL 注入
- **AST 校验**：用 `sqlglot` 解析 + 关键字黑名单
- **建议生产环境**：用专门的只读 DB 用户
- **API Key 安全**：Custom / OpenAI 兼容端点的 API Key **绝不写入仓库**。请用 Settings UI 输入，或在 `.env` 配置 `CUSTOM_LLM_API_KEY`。

## 🧩 Custom / OpenAI-Compatible LLM

Smart BI 内置通用的 OpenAI 兼容 HTTP 客户端，可对接任何暴露 `/chat/completions` 与 `/models` 端点的服务（vLLM、llama.cpp server、LiteLLM、OpenRouter、OneAPI、自建网关、**MiniMax 平台**等）。

### 快速配置（运行时，UI）

1. 打开桌面应用 → **Settings → LLM 提供方**
2. Provider 选 `Custom / OpenAI-Compatible`
3. 填写：
   - **Base URL**：例如 `https://api.minimaxi.com/v1`
   - **模型**：例如 `MiniMax-M3`
   - **API Key**：Bearer Token
4. 点 **测试连通** 验证 → 点 **切换 LLM** 生效

### 快速配置（.env，推荐给打包后 / 无人值守）

```bash
# .env
CUSTOM_LLM_URL=https://api.minimaxi.com/v1
CUSTOM_LLM_API_KEY=sk-cp-...
```

`config.yaml` 里的 `llm.default_provider` 改成 `"custom"` 即默认走它。

### API

```bash
# 临时切换（不落盘）
POST /api/llm/switch
{
  "provider": "custom",
  "model": "MiniMax-M3",
  "custom_url": "https://api.minimaxi.com/v1",
  "api_key": "sk-cp-..."
}

# 探测连通（不切换）
POST /api/llm/test?provider=custom&custom_url=https://api.minimaxi.com/v1&api_key=sk-cp-...
```

### MiniMax 平台配置（默认已预置）

| 区域 | Base URL |
|---|---|
| 国内（默认）| `https://api.minimaxi.com/v1` |
| 海外 | `https://api.minimax.io/v1` |

可用模型：`MiniMax-M3`（默认）/ `MiniMax-M2.7` / `MiniMax-M2.7-highspeed` / `MiniMax-M2.5` / `MiniMax-M2.1` / `MiniMax-M2`。

### 支持的能力

- ✅ Chat completions（text）
- ✅ Function Calling / Tool Use（OpenAI 格式）
- ✅ 流式（`chat_stream`）
- ✅ `/models` 列表探测
- ✅ Bearer Token 鉴权
- ✅ 推理模型 `<think>...</think>` 自动剥离（MiniMax-M3、Qwen3、DeepSeek-R1 等）

### 安全说明

- API Key **绝不写入仓库**。请用 Settings UI 输入，或在 `.env` 配置 `CUSTOM_LLM_API_KEY`（`.env` 已在 `.gitignore`）。
- `config.yaml` 里 `custom.api_key` 留空，key 只走环境变量。

## ❓ 常见问题

**Q: 没有 LLM 时启动会怎样？**
A: 后端会启动但 `/api/query` 会返回错误。前端会显示 "no LLM"。请安装 Ollama 或设置 API key。

**Q: 我想接自家部署的 LLM / 第三方代理（vLLM、LiteLLM、OpenRouter…）怎么办？**
A: 用 **Custom / OpenAI-Compatible** 端点。Settings → Provider 选 Custom → 填 Base URL + 模型名 + API Key。任何暴露 `/chat/completions` 的服务都直接可用。详见上文"Custom / OpenAI-Compatible LLM"一节。

**Q: 怎样让 SQL 不带 LIMIT？**
A: 当前为防止结果过大默认 LIMIT 1000，可在 SQL 末尾加 `LIMIT 1000000` 解除，或修改 `database.max_rows`。

**Q: 怎样提高 NL2SQL 准确率？**
A: 三招：
1. 在 `backend/agent/prompts/few_shots.json` 加更多业务样本
2. Schema RAG 用的表/字段描述会显著影响准确率
3. 用更强的代码专用模型：`qwen2.5-coder:32b` / `deepseek-coder-v2`

**Q: 支持中文表/字段名吗？**
A: 支持。SQLite/MySQL/PostgreSQL 都支持 Unicode 标识符（PG 需要双引号）。

**Q: PyWebView 在 Linux 上不工作？**
A: 需要 `libwebkit2gtk-4.1-dev`，或退回浏览器模式（修改 `backend/app.py`）。

## 📜 License

MIT
