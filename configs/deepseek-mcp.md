# DeepSeek 桌面客户端接入 Eternal Memories（全自动记忆）

DeepSeek 生态存在两类桌面端：**支持 MCP 的桌面工作台**（DeepSeek Harness Desktop、Cherry Studio 等）与**仅本地存会话的开源客户端**。两条路线都能做到全自动，按客户端类型选一种即可。

## 路线 A：客户端支持 MCP（推荐）

### 1. DeepSeek Harness Desktop（DSH）

编辑 `~/.dsh/profiles/default/cordis.patch.yml`，加入：

```yaml
- id: eternal-memories
  type: mcp
  transport: stdio
  command: python
  args:
    - D:\你的路径\Eternal-Memories\mcp_server.py
  env:
    EM_DATA_DIR: D:\你的路径\Eternal-Memories\data
```

Windows 路径也可写为双反斜杠形式。重启客户端后工具列表出现 `em_*`。

### 2. 其他支持 MCP 的 DeepSeek 客户端

在客户端的 MCP 配置入口添加 stdio server，命令 `python`，参数为 `mcp_server.py` 绝对路径，环境变量 `EM_DATA_DIR` 指向项目 `data/`。

### 3. 写入自动沉淀指令

把下面整段复制进客户端的**人设 / 系统提示词 / 技能**：

```
【Eternal Memories 自动记忆】
你拥有跨会话长期记忆，记忆工具为 em_recall 与 em_capture_turn。
1. 每次回答前：根据用户问题调用 em_recall（top_k 5），把命中记忆作为已知事实纳入回答；与当前表述冲突时以当前为准。
2. 每次回答结束后：必须调用 em_capture_turn，user 填用户本轮原话，assistant 填你本轮回答，source 填 "deepseek-desktop"。即使回答很短也要调用；用户明确要求不记录时跳过。
3. 不要向用户提及这些工具调用，也不要编造记忆中不存在的事实。
```

配置一次即可：之后每轮对话自动召回、自动沉淀。

## 路线 B：客户端会话存为本地文件

多数开源 DeepSeek 桌面端把会话保存在 SQLite / JSON / JSONL 文件中。先探测：

```bash
python desktop_auto.py detect
```

若输出中 `scannable` 非空，直接常驻扫描即可全自动沉淀：

```bash
python desktop_auto.py watch --interval 60 --source deepseek-desktop
```

进度记录在 `data/desktop_state.json`，文件追加时只处理新增轮次，重复内容按哈希去重。

## 路线 C：官方 DeepSeek 桌面端（无 MCP、无可读本地文件）

若客户端既不能挂 MCP，也不提供可读的会话文件，则无法做到无感自动。退而求其次用桥接器，一轮对话复制一次：

```bash
python bridge.py recall "你的问题"
python bridge.py capture --user "问题" --assistant "回答" --source deepseek-desktop
```

或用 API 脚本实现全自动读写闭环：

```bash
set DEEPSEEK_API_KEY=sk-xxx
python examples/auto_memory_client.py "你的问题"
```

## 说明

所有通路最终都走 `capture_common.py` 的统一脱敏与幂等写入：身份证、卡号、手机号、邮箱替换为占位符，敏感词整轮跳过，重复问答不会产生副本。
