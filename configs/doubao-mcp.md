# 豆包桌面客户端接入 Eternal Memories（全自动记忆）

适用于 Windows / macOS 豆包桌面端。豆包支持「自定义连接器（STDIO）」，挂载后模型可在每轮对话中自动调用记忆工具。

## 一、添加 MCP 连接器

1. 打开豆包客户端 → 左侧 **插件 · 技能 · 伙伴**。
2. 插件页右上角 **+ 添加** → **新建自定义连接器**。
3. 传输类型选 **STDIO / 仅本地电脑**。
4. 运行命令填 `python`（或本机 Python 3.10+ 的绝对路径）。
5. 参数填 `mcp_server.py` 的绝对路径，例如：

```
D:\你的路径\Eternal-Memories\mcp_server.py
```

6. 环境变量填：

```
EM_DATA_DIR=D:\你的路径\Eternal-Memories\data
```

7. 保存后进入连接器详情，点 **在对话中试用**；工具列表出现 `em_recall`、`em_capture_turn` 等 **15 个 `em_*` 工具**即接入成功。

> 路径中的反斜杠按客户端要求填写；若客户端不接受单反斜杠，改用双反斜杠或正斜杠。

## 二、写入自动沉淀指令（关键）

把下面整段复制进豆包的**技能 / 人设 / 自定义指令**，保存后即可全自动记忆：

```
【Eternal Memories 自动记忆】
你拥有跨会话长期记忆，记忆工具为 em_recall 与 em_capture_turn。
1. 每次回答前：根据用户问题调用 em_recall（top_k 5），把命中记忆作为已知事实纳入回答；与当前表述冲突时以当前为准。
2. 每次回答结束后：必须调用 em_capture_turn，user 填用户本轮原话，assistant 填你本轮回答，source 填 "doubao-desktop"。即使回答很短也要调用；用户明确要求不记录时跳过。
3. 不要向用户提及这些工具调用，也不要编造记忆中不存在的事实。
```

配置完成后无需手动复制粘贴：每轮对话自动召回、自动沉淀，全部数据写入本机 `data/eternal.db`。

## 三、为什么不做本地会话文件解析

豆包桌面端把会话写在 Chromium IndexedDB（`%LOCALAPPDATA%\Doubao\User Data\...\chrome_doubao-chat_0.indexeddb.leveldb`），格式为 LevelDB + Snappy + V8 结构化序列化，且回复完成后会清空本地正文快照。标准库无法可靠解析，强行走文件扫描会漏数据。因此豆包走 MCP 通路，由 `capture_common.py` 在工具入口统一脱敏后写入。

可运行 `python desktop_auto.py detect` 查看本机客户端的会话存储类型与建议。
