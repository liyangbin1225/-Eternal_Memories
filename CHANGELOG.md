# Eternal Memories 更新说明

**版本**：v1.0.0（2026-11-27）　|　**作者**：黎扬斌　|　**仓库**：https://github.com/liyangbin1225/-Eternal_Memories　|　**许可**：MIT

---

## 一、版本说明

v1.0.0 是首次公开发布版本，包含当前全部能力：六臂融合召回、四类关系图、本地文件与目录批量导入、跨智能体自动记忆、3D 星云面板。发布包已清除全部个人业务数据与演示内容，仅保留作者署名与仓库地址。

---

## 二、功能清单

| 模块 | 功能 | 说明 |
|---|---|---|
| `eternal_memory.py` | 记忆引擎 | 六臂召回（词法/激活/图/画像/时序/因果）+ RRF 融合；四类关系图；不可变基准衰减；矛盾检测；幂等去重 |
| `eternal_memory.py` | 本地摄取 | `import_file` 支持 md/txt/html/eml/json/jsonl；`import_folder` 递归批量导入，白名单+噪声过滤+2MB 上限+幂等 |
| `mcp_server.py` | MCP 工具 | 15 个 `em_*` 工具，新增 `em_capture_turn` 供桌面客户端每轮自动沉淀；stdio 协议 |
| `web_server.py` | REST + 面板 | 只读查询、读写操作、治理操作、`/api/capture` 自动沉淀；默认仅绑定 `127.0.0.1` |
| `auto_capture.py` | 会话自动沉淀 | `once` 扫描当天新增轮次、`watch` 常驻增量监听、`text` 单轮文本；进度存状态文件，重复内容哈希去重 |
| `capture_common.py` | 公共沉淀层 | 兼容 WorkBuddy / Claude Code JSONL 与纯文本对话；统一脱敏、敏感词过滤、幂等写入 |
| `bridge.py` | 通用桥接 | recall/json/remember/import/capture/prompt/serve，覆盖无插件的网页版智能体 |
| `desktop_auto.py` | 桌面客户端自动记忆 | 探测豆包 / DeepSeek 客户端会话存储；可解析的 SQLite/JSON/JSONL 增量扫描沉淀 |
| `configs/doubao-mcp.md`、`configs/deepseek-mcp.md` | 桌面客户端配置 | 豆包自定义连接器与 DeepSeek MCP 配置步骤 + 可复制的技能指令模板 |
| `hooks/` | WorkBuddy 闭环 | UserPromptSubmit 自动召回注入；Stop 自动沉淀最后一轮问答；异常静默放行 |
| `dashboard.html` | 3D 星云面板 | 六瓣布局、粒子星尘、透视投影、召回扩散波；六臂雷达、时间轴、五个页签 |
| `examples/` | 接入示例 | DeepSeek API 记忆注入示例、API 读写双向自动记忆示例 |

---

## 三、跨智能体自动记忆通路

| 智能体类型 | 方式 | 自动程度 |
|---|---|---|
| WorkBuddy | 全局 hooks | 全自动 |
| 豆包桌面客户端 | MCP 自定义连接器 + 技能指令调用 `em_capture_turn` | 全自动 |
| DeepSeek 桌面客户端 | MCP 或 `desktop_auto.py` 扫描本地会话 | 全自动 |
| Claude Code / Cursor / Cline | `auto_capture.py once / watch` 扫描会话文件 | 全自动 |
| 扣子 / Dify / n8n / 自研 Agent | `POST /api/capture` | 全自动 |
| DeepSeek / OpenAI 兼容 API | `examples/auto_memory_client.py` | 全自动 |
| 豆包 / DeepSeek 网页版 | `bridge.py capture` 粘贴一轮对话 | 半自动（平台无插件接口） |

---

## 四、升级与兼容

- 解压即用，Python 3.10+，仅标准库，无需 pip install。
- 默认数据目录为项目内 `data/eternal.db`；可用 `EM_DATA_DIR` 指向自定义位置。
- MCP 客户端需重启后加载 15 个工具；WorkBuddy hooks 配置保存即生效。
- 发布包内数据库仅含中性演示数据，首次使用可删除 `data/eternal.db` 后执行 `python cli.py init` 从零开始。

---

## 五、验证结果

- 全部 Python 模块编译通过，发布包解压自检通过。
- 会话沉淀：首次写入、二次去重、敏感轮次跳过、手机号脱敏均验证通过。
- REST 三种入参（user/assistant、text、path）与 MCP 工具列表验证通过。
- 全文扫描确认无个人业务数据与敏感词残留，作者署名与仓库地址保留。
