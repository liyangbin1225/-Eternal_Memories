# Eternal Memories · 永恒记忆系统

**作者**：黎扬斌　|　**仓库**：https://github.com/liyangbin1225/-Eternal_Memories　|　**许可**：MIT

一套本地优先、零第三方依赖的跨智能体长期记忆系统。一个 SQLite 文件承载全部记忆，通过 MCP / REST / CLI / 提示词桥接四种方式，让 WorkBuddy、豆包、DeepSeek、Coze 及自研 Agent 都能拥有跨会话记忆与 3D 星云视图。

---

## 一、3 步快速开始

```bash
# 1. 解压项目到任意目录，进入目录（需 Python 3.10+，无需 pip install）
cd Eternal-Memories

# 2. 初始化记忆库并自检
python cli.py init
python cli.py stats

# 3. 写入一条记忆，然后召回验证
python cli.py remember "偏好：方案先给成品，解释后置" --title "交付偏好" --type preference
python cli.py recall "方案怎么写" -k 3
python cli.py serve          # 启动面板：http://127.0.0.1:8765/
```

项目自带 `data/eternal.db` 初始库（记忆种子数据）。如需从零开始，删除该文件后执行 `init` 即可。

---

## 二、核心能力

| 能力 | 说明 |
|---|---|
| **六臂融合召回** | 词法（中文 bigram + 英文词 TF-IDF，带概念同义扩展）、激活（FSRS 式时间衰减）、图扩散（四类关系图）、画像、时序、因果；RRF 加权融合，名次加成保证精确命中优先 |
| **四类关系图** | temporal / entity / causal / semantic，证据三级 `extracted`/`inferred`/`ambiguous` |
| **记忆治理** | 不可变基准衰减（重复巩固不耗尽记忆）、访问提升、过期归档、内容哈希幂等去重、否定词窗口矛盾检测（只报告不删除） |
| **多格式摄取** | 单文件或整个目录批量导入（md / markdown / txt / html / eml / json / jsonl）；Markdown frontmatter + `[[双链]]` 自动建 entity 边；幂等去重、噪声过滤、文件数上限 |
| **互操作导出** | JSON 全量导出、带 frontmatter 的 Markdown 双链库、SQLite 在线备份 |
| **3D 星云面板** | 黄金角螺旋 + 权重分层 + 透视投影 + 星尘粒子 + 光晕节点 + 召回扩散波；六臂雷达、时间轴、召回/清单/冲突/画像/链路五页签 |
| **全局自动闭环** | WorkBuddy hooks：提问前自动召回注入，每轮结束自动沉淀最后一轮问答（脱敏 + 幂等） |
| **跨智能体自动沉淀** | 会话文件监听（once/watch）、REST 回调 `/api/capture`、文本桥接 `bridge capture`、API 双向闭环、豆包/DeepSeek 桌面客户端 MCP 自动调用，覆盖有文件/能HTTP/有客户端/只能粘贴的四类智能体 |

---

## 三、接入任意智能体

### 3.1 接入方式矩阵

| 智能体 / 场景 | 推荐方式 | 是否自动 |
|---|---|---|
| WorkBuddy | MCP + 全局 hooks | 全自动闭环 |
| Claude Desktop / Cursor / Cline / Windsurf / Chatter | MCP stdio | 工具调用 |
| **豆包桌面客户端** | MCP 自定义连接器 + 技能指令 | **全自动** |
| **DeepSeek 桌面客户端** | MCP 或 `desktop_auto.py` 扫描本地会话 | **全自动** |
| 豆包网页版 / DeepSeek 网页版 | `bridge.py recall` 提示词桥接 | 手动粘贴 |
| DeepSeek API / OpenAI 兼容 API | `examples/deepseek_client.py` | 自动注入 |
| 扣子 Coze / Dify / n8n | REST HTTP 节点 | 自动 |
| 自研 Agent / 脚本 | `from eternal_memory import EternalMemory` | 直接调用 |

### 3.2 WorkBuddy（自动闭环）

1. 备份 `~/.workbuddy/settings.json` 与 `~/.workbuddy/mcp.json`
2. 参照 `configs/workbuddy.json.example`，把 `<PROJECT>` 替换成本项目绝对路径
3. 将 `mcpServers.eternal-memories` 合并进 `mcp.json`，将 `hooks` 合并进 `settings.json`（**不要覆盖原有条目**）
4. 重启 WorkBuddy，`em_recall` 等 15 个工具出现即成功

hooks 保存即生效：提问前自动注入相关记忆；每轮结束沉淀新记忆到 `data/`。

### 3.3 其他 MCP 客户端

参照 `configs/generic-mcp.json.example`，把 `mcpServers` 内容合并进客户端配置。Windows 路径中的 `\` 写成 `\\`。客户端重启后可调用 `em_recall`、`em_remember` 等工具。

### 3.4 豆包 / DeepSeek 网页版（无插件接口）

```bash
python bridge.py recall "我要写季度项目交付计划"
```

把输出整段复制进豆包或 DeepSeek 对话框。输出已包含召回记忆、可注入上下文和用户问题，模型无需任何插件即可"记住"你的历史。

把 `python bridge.py prompt generic` 的输出放进智能体的"人设/系统提示词"，可让模型默认遵循记忆优先原则。

### 3.5 DeepSeek API（自动注入）

```bash
export DEEPSEEK_API_KEY=sk-xxx     # Windows 用 set
python examples/deepseek_client.py "项目交付计划怎么安排？"
```

脚本先在本地召回，再作为 system 消息注入请求。**记忆数据库不上传**，只发送召回出的文本。

### 3.6 扣子 / Dify / n8n（REST）

先 `python cli.py serve`，然后在工作流中加 HTTP 节点：

```
POST http://127.0.0.1:8765/api/recall
Content-Type: application/json

{"query": "用户问题", "top_k": 5}
```

返回 `items`（命中记忆）与 `context_pack`（可直接塞进大模型上下文的文本）。服务默认只绑定 `127.0.0.1`，如需跨设备访问自行配置端口转发与鉴权。

### 3.7 本地文件 / 整个目录成为记忆（重点）

**一个命令把整个本地文件夹变成记忆库**：`import` 自动识别路径是文件还是目录。

```bash
# 整目录导入（递归，默认最多 200 个文件）
python cli.py import "D:\我的资料"

# 只扫当前层，不进子目录
python cli.py import "D:\我的资料" --no-recursive

# 限制本次最多处理 500 个文件
python cli.py import "D:\我的资料" --max-files 500

# 桥接器同样支持（供豆包/DeepSeek 场景）
python bridge.py import "D:\我的资料"
```

导入行为：

- 识别 `md / markdown / txt / html / htm / eml / json / jsonl`，其余扩展名自动跳过
- 跳过隐藏文件、`__pycache__`、`node_modules`、`.git`、`backups` 等噪声目录
- 单个文件超过 2MB 跳过并记入 `skipped`；单文件解析失败记入 `errors`，不影响整批
- **内容哈希幂等**：同一文件重复导入只更新时间戳，不产生重复记忆（注意 source 不同视为不同来源）
- 返回 `scanned / imported / memories_added / memories_duplicate / skipped / errors` 汇总

MCP 客户端调用 `em_import_folder`（参数 `path`、`recursive`、`max_files`、`source`）；REST 用 `POST /api/import` 且 `{"path":"D:\\我的资料","kind":"auto"}`（目录自动识别）。

Markdown 文件可在开头写 frontmatter 控制记忆点属性：

```markdown
---
title: 沟通时间偏好
tags: [协作, 时间]
importance: 0.9
memory_type: preference
---

# 回访时间
团队偏好每周三下午同步进度。
```

### 3.8 Python 直接调用

```python
from eternal_memory import EternalMemory

g = EternalMemory("data")
g.remember("客户偏好周三回访", "回访偏好", "preference", ["客户"], "python")
g.import_folder(r"D:\我的资料")          # 整目录成为记忆点
result = g.recall("沟通时间安排", top_k=5)
print(result["context_pack"])
g.close()
```

### 3.9 其他智能体如何自动记住当天对话（重点）

**现状**：WorkBuddy 已由全局 hooks 实现全自动读写闭环；其他智能体也已补齐三条自动通路。

| 智能体类型 | 自动沉淀方式 | 是否全自动 |
|---|---|---|
| WorkBuddy | 全局 hooks（UserPromptSubmit 召回 + Stop 沉淀） | 全自动 |
| **豆包桌面客户端** | 自定义连接器挂载 MCP + 技能指令自动调用 `em_capture_turn` | **全自动** |
| **DeepSeek 桌面客户端** | MCP（Harness 等）或本地会话文件扫描 | **全自动** |
| Claude Code / Cursor / Cline（有会话文件） | `auto_capture.py once` 或 `watch` 扫描 JSONL | 全自动 |
| 扣子 / Dify / n8n / 自研 Agent（能发 HTTP） | `POST /api/capture` 回调 | 全自动 |
| DeepSeek API / OpenAI 兼容 API | `examples/auto_memory_client.py` 读写闭环 | 全自动（脚本内自动） |
| 豆包 / DeepSeek 网页版（无插件无文件） | `bridge.py capture` 粘贴一轮对话 | 半自动（需复制一次） |

**方式一：扫描本地会话文件（当天新增轮次，增量幂等）**

```bash
python auto_capture.py once "D:\会话记录" --since today
python auto_capture.py watch "D:\会话记录" --interval 60   # 常驻监听，Ctrl+C 停止
```

支持 WorkBuddy transcript、Claude Code JSONL 及纯文本对话；进度记录在 `data/capture_state.json`，文件追加时只处理新轮次，重复内容靠内容哈希去重。`--since all` 可关闭日期过滤。

**方式二：REST 回调（任意能发 HTTP 的智能体）**

```bash
python cli.py serve
```

```
POST http://127.0.0.1:8765/api/capture
Content-Type: application/json

{"user":"用户问题","assistant":"智能体回答","source":"coze"}
```

也可用 `{"text":"【用户】...【助手】..."}` 或 `{"path":"D:\\会话.jsonl","since":"today"}`。返回 `remembered / duplicates / skipped / errors` 汇总。

**方式三：无插件网页版（豆包 / DeepSeek）**

```bash
python bridge.py capture --user "用户问题" --assistant "智能体回答" --source doubao
# 或把整段对话粘贴进 stdin
echo "【用户】问题【助手】回答" | python bridge.py capture --source doubao
```

**方式四：API 智能体读写双向闭环**

```bash
set DEEPSEEK_API_KEY=sk-xxx
python examples/auto_memory_client.py "项目交付计划怎么安排？"
```

脚本先本地召回注入 system，再请求模型，最后自动把本轮问答沉淀回记忆库。把 `_ask()` 换成任意模型调用即可复用。

**方式五：豆包 / DeepSeek 桌面客户端全自动（推荐）**

```bash
python desktop_auto.py detect                              # 探测本机会话存储类型
python desktop_auto.py watch --interval 60 --source deepseek-desktop   # 可解析文件时常驻扫描
```

- **豆包桌面端**支持自定义连接器（STDIO）：挂载 `mcp_server.py`，再把自动沉淀指令写入「技能/人设」，每轮结束由模型调用 `em_capture_turn`，无需人工干预。完整步骤见 `configs/doubao-mcp.md`。
- **DeepSeek 桌面端**：支持 MCP 的客户端按 `configs/deepseek-mcp.md` 挂载并写入技能指令；会话存为 SQLite/JSON 的客户端用 `desktop_auto.py watch` 扫描即可。
- 豆包官方客户端的会话存于 Chromium IndexedDB（LevelDB/Snappy/V8 序列化），标准库无法可靠解析，因此走 MCP 通路而非文件扫描。

以上所有路径共用 `capture_common.py` 的脱敏与过滤规则：身份证/卡号/手机号/邮箱替换占位符，薪资/佣金比例等敏感词整轮跳过，过短轮次不沉淀。

---

## 四、接口清单

### MCP 工具（15 个，前缀 `em_`）

`em_health` / `em_recall` / `em_remember` / `em_capture_turn` / `em_link` / `em_import_workbuddy` / `em_import_file` / `em_import_folder` / `em_consolidate` / `em_conflicts` / `em_stats` / `em_graph` / `em_profile` / `em_export` / `em_backup`（共 15 个）

### REST 端点

| 方法 | 路径 | 用途 |
|---|---|---|
| GET | `/api/health` `/api/stats` `/api/graph` `/api/conflicts` `/api/profile` `/api/export` `/api/memories` | 只读查询 |
| POST | `/api/recall` `/api/remember` `/api/link` `/api/import` `/api/consolidate` `/api/backup` | 读写操作 |
| POST | `/api/capture` | 跨智能体会话自动沉淀（user/assistant、text 或 path） |
| POST | `/api/archive` `/api/pin` `/api/forget` | 治理操作 |

### CLI

```bash
python cli.py --help
python cli.py recall "关键词" -k 5 --compact
python cli.py remember "内容" --title "标题" --tags "标签1,标签2"
python cli.py import ./notes.md
python cli.py export --format markdown --path ./export
python cli.py backup
python cli.py serve        # REST + 面板
python cli.py mcp          # MCP stdio（供客户端拉起）

python auto_capture.py once "D:\会话记录" --since today   # 当天会话自动沉淀
python auto_capture.py watch "D:\会话记录" --interval 60  # 常驻监听
python bridge.py capture --user "问题" --assistant "回答" # 网页版智能体沉淀
python desktop_auto.py detect                              # 探测豆包/DeepSeek 客户端
python desktop_auto.py watch --interval 60                 # 客户端会话全自动沉淀
```

---

## 五、六臂召回与数据模型

| 臂 | 机制 |
|---|---|
| LEX | 中文 bigram / 英文词 TF-IDF 余弦 + 概念词典同义扩展；前三名加成 3.0/2.0/1.5 |
| ACT | 基于创建时间的 FSRS 式衰减 + 访问次数提升，置顶记忆保底 |
| GRAPH | temporal/entity/causal/semantic 四类边的邻居传播，剔除种子自身 |
| PROFILE | 与身份、偏好、禁忌类记忆的匹配 |
| TEMPORAL | 时间词与记忆时间窗口匹配 |
| CAUSAL | 因果边相关记忆扩散 |

融合采用 RRF 变体：每臂按名次加权 `权重/(60+名次)`，同一记忆多臂命中累加。分数统一归一到 `[0,1]`。

数据表：`memories`（含 `base_importance` 不可变基准）、`edges`、`traces`、`seen`。所有写入按内容哈希幂等，重复导入不产生副本。

---

## 六、数据安全

- 数据全部落在本地 `data/eternal.db`，无需联网、无需 API Key（DeepSeek 示例除外）
- REST 服务仅绑定 `127.0.0.1`，校验 Host 头防 DNS rebinding，CORS 仅放行本机 Origin，`/static` 后缀白名单防止源码读取
- 所有自动沉淀路径（hooks / auto_capture / REST / bridge / API 示例）共用同一套脱敏：身份证、卡号、手机号、邮箱替换为占位符；薪资、佣金比例等敏感词整轮跳过
- hooks 异常静默放行，写入 `data/hook.log` 供排障，绝不阻塞对话
- 修改全局配置前请备份；`configs/` 中示例仅作模板

---

## 七、目录结构

```
Eternal-Memories/
├── README.md                 完整技术文档
├── USER_GUIDE.md             一页式使用说明与功能说明（可直接贴 Release）
├── LICENSE                   MIT 许可（黎扬斌）
├── eternal_memory.py         核心引擎：六臂召回、图治理、导入导出
├── capture_common.py         会话沉淀公共逻辑：提取问答、脱敏、幂等写入
├── auto_capture.py           跨智能体会话自动沉淀器（once/watch/text）
├── desktop_auto.py           豆包/DeepSeek 桌面客户端会话探测与增量沉淀
├── mcp_server.py             MCP stdio 服务（15 个 em_* 工具）
├── web_server.py             REST API + 星云面板托管
├── cli.py                    命令行入口
├── bridge.py                 通用智能体桥接器（豆包/DeepSeek 网页版）
├── dashboard.html            自包含 3D 星云面板（无需 CDN）
├── hooks/
│   ├── recall_hook.py        UserPromptSubmit 自动召回
│   ├── capture_hook.py       Stop 自动沉淀（脱敏+幂等）
│   └── hook_log.py           异常日志
├── configs/
│   ├── workbuddy.json.example
│   ├── generic-mcp.json.example
│   ├── doubao-mcp.md          豆包桌面客户端全自动配置
│   └── deepseek-mcp.md        DeepSeek 桌面客户端全自动配置
├── examples/
│   ├── deepseek_client.py    DeepSeek API 记忆注入示例
│   └── auto_memory_client.py API 读写双向自动记忆示例
└── data/
    ├── eternal.db            初始记忆库（种子数据）
    └── capture_state.json    会话扫描进度（首次运行后生成）
```

---

## 八、常见问题

**Q：Python 版本要求？** 3.10+（使用了 `X | None` 类型语法），仅标准库，无需 pip install。

**Q：如何清空记忆重来？** 删除 `data/eternal.db` 后执行 `python cli.py init`。

**Q：面板打不开？** 确认 `python cli.py serve` 正在运行，浏览器访问 `http://127.0.0.1:8765/`。端口可用环境变量 `EM_PORT` 修改。

**Q：数据目录想放别处？** 设置环境变量 `EM_DATA_DIR`，或用 CLI 参数 `--data-dir`。

**Q：能真正做语义向量检索吗？** 当前用概念同义扩展 + TF-IDF 近似，零成本断网可用。如需真向量，可自行接入本地 embedding 服务扩展第七臂。

**Q：豆包/DeepSeek 网页版能全自动记忆吗？** 网页版既无插件接口也无本地会话文件，无法做到无感自动。用 `bridge.py capture` 粘贴一轮对话即可沉淀；若用 API 或 MCP 客户端则可全自动。

**Q：会话文件在哪？** WorkBuddy 在设置中可查看 transcript 路径；Claude Code 通常在 `~/.claude/projects/<项目>/` 下的 `.jsonl`。把所在目录传给 `auto_capture.py` 即可，无需关心具体文件名。
