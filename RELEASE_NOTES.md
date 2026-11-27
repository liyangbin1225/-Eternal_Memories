# Eternal Memories v1.0.0 发布说明

**作者**：黎扬斌　|　**仓库**：https://github.com/liyangbin1225/-Eternal_Memories　|　**许可**：MIT　|　**发布**：2026-11-27

---

## 一句话介绍

本地优先、零第三方依赖的跨智能体长期记忆系统。一个 SQLite 文件承载全部记忆，通过 MCP / REST / CLI / 提示词桥接四种方式，让 WorkBuddy、豆包、DeepSeek、Claude、Cursor、扣子等智能体拥有跨会话记忆与 3D 星云视图。

---

## 功能亮点

| 能力 | 说明 |
|---|---|
| **六臂融合召回** | 词法（中文 bigram + 英文 TF-IDF，含概念同义扩展）、激活（时间衰减）、图扩散、画像、时序、因果；RRF 加权融合，精确命中优先 |
| **四类关系图** | temporal / entity / causal / semantic，证据三级 `extracted` / `inferred` / `ambiguous` |
| **记忆治理** | 不可变基准衰减（重复巩固不耗尽记忆）、访问提升、过期归档、内容哈希幂等、矛盾检测（只报告不删除） |
| **本地文件摄取** | 单文件或整个目录批量导入，md/txt/html/eml/json/jsonl；Markdown frontmatter 与 `[[双链]]` 自动建边；噪声过滤 + 2MB 上限 + 幂等 |
| **跨智能体自动记忆** | 会话文件监听、REST 回调、文本桥接、API 读写闭环四条通路，覆盖有文件 / 能 HTTP / 只能粘贴的三类智能体 |
| **3D 星云面板** | 黄金角螺旋 + 权重分层 + 透视投影 + 粒子星尘 + 召回扩散波；六臂雷达、时间轴、五个页签 |
| **本地安全** | 数据只存本地；REST 仅绑 `127.0.0.1` 并校验 Host；脱敏先长后短替换身份证/卡号/手机号/邮箱；敏感词整轮跳过 |
| **零依赖** | 纯 Python 标准库 + 原生 Canvas，Python 3.10+，无需 pip install |

---

## 3 步开始

```bash
# 1. 解压后进入目录（Python 3.10+）
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

---

## 接入任意智能体

| 智能体 / 场景 | 方式 | 自动程度 |
|---|---|---|
| WorkBuddy | MCP + 全局 hooks | 全自动 |
| Claude Desktop / Cursor / Cline / Windsurf | MCP stdio（15 个 `em_*` 工具） | 工具调用 |
| **豆包桌面客户端** | MCP 自定义连接器 + 技能指令自动调用 `em_capture_turn` | **全自动** |
| **DeepSeek 桌面客户端** | MCP 或 `desktop_auto.py` 扫描本地会话 | **全自动** |
| Claude Code / Cursor 会话文件 | `python auto_capture.py once "D:\会话记录" --since today` | 全自动 |
| 扣子 / Dify / n8n | `POST http://127.0.0.1:8765/api/recall` | 自动 |
| 扣子 / Dify / n8n 自动沉淀 | `POST /api/capture` | 全自动 |
| DeepSeek / OpenAI 兼容 API | `python examples/auto_memory_client.py "你的问题"` | 全自动（读写闭环） |
| 豆包 / DeepSeek 网页版 | `python bridge.py recall "你的问题"`、`python bridge.py capture ...` | 手动粘贴 |
| 自研 Agent / 脚本 | `from eternal_memory import EternalMemory` | 直接调用 |

### 让智能体自动记住当天对话

- **豆包 / DeepSeek 桌面客户端**：挂载 MCP 并写入技能指令，每轮自动召回与沉淀，配置见 `configs/doubao-mcp.md` 与 `configs/deepseek-mcp.md`
- **DeepSeek 会话存为本地文件**：`python desktop_auto.py detect` 探测，再用 `watch` 常驻扫描
- **有会话文件**：`python auto_capture.py once "D:\会话记录" --since today`，常驻监听加 `watch --interval 60`
- **能发 HTTP**：`POST /api/capture`，请求体 `{"user":"问题","assistant":"回答","source":"coze"}`
- **网页版**：`python bridge.py capture --user "问题" --assistant "回答" --source doubao`
- **API 智能体**：设置 `DEEPSEEK_API_KEY` 后运行 `examples/auto_memory_client.py`

网页版本身无插件接口与会话文件读取权限，无法做到无感自动；其余类型均可全自动。

完整配置模板见 `configs/`，逐项用法见 `README.md`，改动记录见 `CHANGELOG.md`。

---

## 数据与隐私

- 所有数据保存在本地 `data/eternal.db`，默认不联网、不需要 API Key。
- REST 服务只监听 `127.0.0.1`，校验 Host 防 DNS rebinding，CORS 仅放行本机 Origin，静态资源后缀白名单。
- 所有自动沉淀通路共用同一套脱敏规则；强敏感词整轮跳过，异常静默放行并记录到 `data/hook.log`。
- 发布包内已清除个人业务数据与演示内容，仅保留作者署名与仓库地址。

---

## 文件清单

| 文件 | 作用 |
|---|---|
| `eternal_memory.py` | 核心引擎：六臂召回、图治理、导入导出 |
| `capture_common.py` | 会话沉淀公共层：提取、脱敏、幂等写入 |
| `auto_capture.py` | 会话自动沉淀器（once / watch / text） |
| `mcp_server.py` | MCP stdio 服务（15 个 `em_*` 工具） |
| `desktop_auto.py` | 豆包 / DeepSeek 桌面客户端会话探测与增量沉淀 |
| `configs/doubao-mcp.md`、`configs/deepseek-mcp.md` | 桌面客户端全自动配置与技能指令模板 |
| `web_server.py` | REST API + 面板托管 |
| `cli.py` / `bridge.py` | 命令行入口 / 通用智能体桥接器 |
| `dashboard.html` | 自包含 3D 星云面板，无 CDN |
| `hooks/` | WorkBuddy 自动召回与沉淀钩子 |
| `configs/` | WorkBuddy 与通用 MCP 配置模板 |
| `examples/` | DeepSeek 注入示例、API 读写闭环示例 |
| `data/eternal.db` | 中性演示记忆库 |
| `README.md` / `USER_GUIDE.md` | 完整技术文档 / 一页式使用与功能说明 |
| `CHANGELOG.md` / `RELEASE_NOTES.md` | 功能清单与改动记录 / 发布摘要 |

---

## 验证

全部模块编译通过；召回、导入、去重、脱敏、REST、MCP、hooks 与会话自动沉淀均已验证。发布包解压即用，无需安装依赖。
