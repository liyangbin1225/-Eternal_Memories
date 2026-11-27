# Eternal Memories v1.0.0 使用说明与功能说明

**作者**：黎扬斌　|　**仓库**：https://github.com/liyangbin1225/-Eternal_Memories　|　**许可**：MIT　|　**发布**：2026-11-27

本文件为发布用的一页式说明，功能清单与上手步骤均可直接复制到 GitHub Release 或 README。逐项细节见 `README.md`，改动记录见 `CHANGELOG.md`，发布摘要见 `RELEASE_NOTES.md`。

---

## 一、产品定位

本地优先、零第三方依赖的跨智能体长期记忆系统。一个 SQLite 文件承载全部记忆，通过 MCP / REST / CLI / 提示词桥接四种通道，让 WorkBuddy、豆包、DeepSeek、Claude、Cursor、扣子等智能体拥有跨会话记忆与 3D 星云视图。

- **数据只存本地**：默认 `data/eternal.db`，无需联网、无需 API Key（模型 API 示例除外）
- **零安装**：Python 3.10+ 标准库 + 原生 Canvas，不需要 `pip install`
- **可迁移**：JSON 全量导出、Markdown 双链库、SQLite 在线备份

---

## 二、功能说明

### 2.1 能力总览

| 功能 | 说明 | 价值 |
|---|---|---|
| **六臂融合召回** | 词法（中文 bigram + 英文 TF-IDF，含概念同义扩展）、激活（时间衰减）、图扩散、画像、时序、因果；RRF 加权融合，精确命中优先 | 不再靠关键词硬搜，历史结论与偏好自动浮出 |
| **四类关系图** | temporal / entity / causal / semantic；证据三级 extracted / inferred / ambiguous | 记忆可追溯、可扩散、可解释 |
| **记忆治理** | 不可变基准衰减、访问提升、过期归档、内容哈希幂等、矛盾检测（只报告不删除） | 重复导入不产生垃圾，记忆不会越用越少 |
| **本地文件 / 目录摄取** | 单文件或整目录批量导入 md/markdown/txt/html/htm/eml/json/jsonl；frontmatter 与 `[[双链]]` 自动建边 | 本地资料、历史笔记一键成为记忆点 |
| **跨智能体自动记忆** | WorkBuddy hooks、豆包/DeepSeek 桌面端 MCP、会话文件监听、REST 回调、文本桥接、API 双向闭环 | 当天对话自动沉淀，下次会话自动召回 |
| **3D 星云面板** | 黄金角螺旋 + 权重分层 + 透视投影 + 星尘粒子 + 召回扩散波；六臂雷达、时间轴、五个页签 | 记忆结构可视化，召回过程可观测 |
| **本地安全** | REST 仅绑 `127.0.0.1` 并校验 Host；CORS 仅本机 Origin；静态资源后缀白名单；统一脱敏与敏感词跳过 | 隐私数据不外泄，敏感内容不入库 |
| **开放接口** | 15 个 MCP 工具、17 个 REST 端点、完整 CLI、Python API、桥接器 | 任意智能体、任意脚本都能接入 |

### 2.2 六臂召回机制

| 臂 | 机制 |
|---|---|
| LEX | 中文 bigram / 英文词 TF-IDF 余弦 + 概念词典同义扩展；前三名加成 3.0 / 2.0 / 1.5 |
| ACT | 基于创建时间的 FSRS 式衰减 + 访问次数提升，置顶记忆保底 |
| GRAPH | 四类边的邻居传播，剔除种子自身 |
| PROFILE | 与身份、偏好、禁忌类记忆的匹配 |
| TEMPORAL | 时间词与记忆时间窗口匹配 |
| CAUSAL | 因果边相关记忆扩散 |

融合采用 RRF 变体：每臂按名次加权 `权重/(60+名次)`，同一记忆多臂命中累加，分数归一到 `[0,1]`。

### 2.3 自动记忆矩阵

| 智能体 / 场景 | 方式 | 自动程度 |
|---|---|---|
| WorkBuddy | MCP + 全局 hooks（UserPromptSubmit 召回 + Stop 沉淀） | 全自动 |
| 豆包桌面客户端 | 自定义连接器挂载 MCP + 技能指令调用 `em_capture_turn` | 全自动 |
| DeepSeek 桌面客户端 | MCP，或 `desktop_auto.py` 扫描本地会话 | 全自动 |
| Claude Desktop / Cursor / Cline / Windsurf | MCP stdio（15 个 `em_*` 工具） | 工具调用 |
| Claude Code / Cursor 会话文件 | `auto_capture.py once / watch` | 全自动 |
| 扣子 / Dify / n8n | `POST /api/recall`、`POST /api/capture` | 全自动 |
| DeepSeek / OpenAI 兼容 API | `examples/auto_memory_client.py` 读写闭环 | 全自动 |
| 豆包 / DeepSeek 网页版 | `bridge.py recall / capture` 提示词桥接 | 手动粘贴（平台无插件接口） |
| 自研 Agent / 脚本 | `from eternal_memory import EternalMemory` | 直接调用 |

> 网页版既无插件接口也无本地会话文件读取权限，无法无感自动；其余类型均可全自动。

### 2.4 自动沉淀的安全规则

所有通路（hooks / auto_capture / desktop_auto / REST / bridge / API 示例）共用同一套规则：

- 身份证、卡号、手机号、邮箱按先长后短替换为占位符
- 薪资、佣金比例等强敏感词整轮跳过
- 过短轮次不沉淀
- 内容哈希幂等：同一问答重复出现只更新时间戳，不产生副本
- 异常静默放行并记录到 `data/hook.log`，绝不阻塞对话

---

## 三、使用说明

### 3.1 三步开始

```bash
# 1. 解压后进入目录（需 Python 3.10+，无需 pip install）
cd Eternal-Memories

# 2. 初始化并自检
python cli.py init
python cli.py stats

# 3. 写入一条记忆，再召回验证
python cli.py remember "偏好：结论前置，解释后置" --title "交付偏好" --type preference
python cli.py recall "方案怎么写" -k 3
python cli.py serve          # 面板：http://127.0.0.1:8765/
```

发布包自带中性演示库（8 条记忆 / 6 条边）。如需从零开始，删除 `data/eternal.db` 后执行 `python cli.py init`。

### 3.2 让本地文件 / 文件夹成为记忆

```bash
# 单个文件
python cli.py import ./notes.md

# 整个目录（递归，默认最多 200 个文件）
python cli.py import "D:\我的资料"

# 只扫当前层 / 限制文件数
python cli.py import "D:\我的资料" --no-recursive
python cli.py import "D:\我的资料" --max-files 500

# Python 内调用
from eternal_memory import EternalMemory
g = EternalMemory("data")
g.import_folder(r"D:\我的资料")
g.close()
```

导入规则：8 种扩展名白名单；跳过隐藏文件、`__pycache__`、`node_modules`、`.git`、`backups`；单文件 2MB 上限；单文件失败隔离；同来源重复导入幂等。

Markdown 文件可用 frontmatter 控制记忆属性：

```markdown
---
title: 沟通时间偏好
tags: [协作, 时间]
importance: 0.9
memory_type: preference
---

团队偏好每周三下午同步进度。`[[协作规范]]` 中记录了完整约定。
```

### 3.3 各智能体接入

| 智能体 | 操作 |
|---|---|
| **WorkBuddy** | 参照 `configs/workbuddy.json.example`，把 `<PROJECT>` 换成本项目绝对路径，将 hooks 与 MCP 配置合并进 `~/.workbuddy/settings.json`、`~/.workbuddy/mcp.json`，重启后 15 个 `em_*` 工具出现即成功 |
| **豆包桌面端** | 按 `configs/doubao-mcp.md`：插件·技能·伙伴 → 新建自定义连接器 → STDIO → 命令 `python`、参数 `mcp_server.py` 绝对路径、环境变量 `EM_DATA_DIR` 指向 `data/`，再把技能指令写入人设 |
| **DeepSeek 桌面端** | 按 `configs/deepseek-mcp.md` 挂载 MCP 并写入技能指令；会话存为文件的用 `desktop_auto.py detect` 探测后 `watch` 扫描 |
| **其他 MCP 客户端** | 参照 `configs/generic-mcp.json.example` 合并 `mcpServers`，Windows 路径中的 `\` 写成 `\\` |
| **扣子 / Dify / n8n** | 先 `python cli.py serve`，工作流加 HTTP 节点 POST `http://127.0.0.1:8765/api/recall`，体 `{"query":"用户问题","top_k":5}` |
| **DeepSeek API** | 设置 `DEEPSEEK_API_KEY` 后 `python examples/deepseek_client.py "你的问题"` |
| **豆包 / DeepSeek 网页版** | `python bridge.py recall "你的问题"` 输出整段复制进对话框；把 `python bridge.py prompt generic` 放进人设 |

### 3.4 自动记住当天对话

```bash
# 方式一：会话文件扫描（增量去重）
python auto_capture.py once "D:\会话记录" --since today
python auto_capture.py watch "D:\会话记录" --interval 60

# 方式二：桌面客户端探测 + 扫描
python desktop_auto.py detect
python desktop_auto.py watch --interval 60 --source deepseek-desktop

# 方式三：网页版粘贴一轮对话
python bridge.py capture --user "问题" --assistant "回答" --source doubao

# 方式四：API 智能体读写闭环
set DEEPSEEK_API_KEY=sk-xxx
python examples/auto_memory_client.py "你的问题"
```

REST 回调（任意能发 HTTP 的智能体）：

```
POST http://127.0.0.1:8765/api/capture
Content-Type: application/json

{"user":"用户问题","assistant":"智能体回答","source":"coze"}
```

也可用 `{"text":"【用户】...【助手】..."}` 或 `{"path":"D:\\会话.jsonl","since":"today"}`。

### 3.5 接口速查

**MCP 工具（15 个，`em_` 前缀）**：`em_health` / `em_recall` / `em_remember` / `em_capture_turn` / `em_link` / `em_import_workbuddy` / `em_import_file` / `em_import_folder` / `em_consolidate` / `em_conflicts` / `em_stats` / `em_graph` / `em_profile` / `em_export` / `em_backup`

**REST 端点**：

| 方法 | 路径 | 用途 |
|---|---|---|
| GET | `/api/health` `/api/stats` `/api/graph` `/api/conflicts` `/api/profile` `/api/export` `/api/memories` | 只读查询 |
| POST | `/api/recall` `/api/remember` `/api/link` `/api/import` `/api/consolidate` `/api/backup` | 读写操作 |
| POST | `/api/capture` | 会话自动沉淀 |
| POST | `/api/archive` `/api/pin` `/api/forget` | 治理操作 |

**CLI 常用命令**：

```bash
python cli.py --help
python cli.py recall "关键词" -k 5 --compact
python cli.py remember "内容" --title "标题" --tags "标签1,标签2"
python cli.py export --format markdown --path ./export
python cli.py backup
python cli.py serve        # REST + 面板
python cli.py mcp          # MCP stdio（供客户端拉起）
```

---

## 四、常见问题

| 问题 | 答案 |
|---|---|
| Python 版本要求？ | 3.10+（使用 `X | None` 语法），仅标准库，无需 pip install |
| 如何清空记忆重来？ | 删除 `data/eternal.db` 后执行 `python cli.py init` |
| 面板打不开？ | 确认 `python cli.py serve` 正在运行，访问 `http://127.0.0.1:8765/`；端口可用 `EM_PORT` 修改 |
| 数据目录想放别处？ | 设置环境变量 `EM_DATA_DIR`，或用 CLI 参数 `--data-dir` |
| 能做语义向量检索吗？ | 当前用概念同义扩展 + TF-IDF 近似，断网可用；真向量可自行接本地 embedding 扩展第七臂 |
| 网页版能全自动吗？ | 不能，网页版无插件接口与会话文件权限；用 `bridge.py capture` 粘贴一轮，或改用客户端 / API |
| 会话文件在哪？ | WorkBuddy 在设置中查看 transcript 路径；Claude Code 通常在 `~/.claude/projects/<项目>/` 下的 `.jsonl` |

---

## 五、文件清单

| 文件 | 作用 |
|---|---|
| `eternal_memory.py` | 核心引擎：六臂召回、图治理、导入导出 |
| `capture_common.py` | 会话沉淀公共层：提取、脱敏、幂等写入 |
| `auto_capture.py` | 会话自动沉淀器（once / watch / text） |
| `desktop_auto.py` | 豆包 / DeepSeek 桌面客户端会话探测与增量沉淀 |
| `mcp_server.py` | MCP stdio 服务（15 个 `em_*` 工具） |
| `web_server.py` | REST API + 面板托管 |
| `cli.py` / `bridge.py` | 命令行入口 / 通用智能体桥接器 |
| `dashboard.html` | 自包含 3D 星云面板，无 CDN |
| `hooks/` | WorkBuddy 自动召回与沉淀钩子 |
| `configs/` | WorkBuddy、通用 MCP、豆包、DeepSeek 配置模板 |
| `examples/` | DeepSeek 注入示例、API 读写闭环示例 |
| `data/eternal.db` | 中性演示记忆库（8 条记忆 / 6 条边） |
| `README.md` / `USER_GUIDE.md` / `CHANGELOG.md` / `RELEASE_NOTES.md` | 完整文档 / 本说明 / 更新记录 / 发布摘要 |

---

## 六、验证结论

全部模块编译通过；召回、导入、去重、脱敏、REST、MCP、hooks、会话自动沉淀与桌面客户端探测均已验证。发布包解压即用，无需安装依赖，包内数据库为 8 条中性演示记忆，业务敏感信息命中 0 条。
