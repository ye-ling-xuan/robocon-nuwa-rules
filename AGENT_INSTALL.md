# 给宿主 Agent 的安装说明

这是 ROBOCON 女娲补天 V3 规则 MCP + Skill 包。你使用自己现有的模型回答，服务器仅离线检索规则、进行确定性计算并提供本地问答/PDF 界面。不要索取 API Key、Base URL 或模型名，不调用其它 LLM API。

仓库：https://github.com/ye-ling-xuan/robocon-nuwa-rules

## 自动安装工作流

1. 确认当前宿主支持 stdio MCP，识别操作系统及宿主配置路径。先读取已有配置，保留其它服务器和设置。
2. 检查 Python 3.11+、Git、uv/uvx。如果缺少 uv，可用现有 Python 执行 `python -m pip install --user uv`，或采用 [uv 官方安装方法](https://docs.astral.sh/uv/getting-started/installation/)。需要遵循当前环境已有的执行权限。
3. 把本包添加为 `robocon-nuwa-rules` MCP 服务。用 `Get-Command uvx`（Windows）或 `command -v uvx`（macOS/Linux）取得绝对路径，供图形宿主稳定启动。配置如下，**无需 env 或任何模型参数**：

```json
{
  "mcpServers": {
    "robocon-nuwa-rules": {
      "command": "uvx",
      "args": [
        "--from",
        "git+https://github.com/ye-ling-xuan/robocon-nuwa-rules",
        "robocon-nuwa-mcp"
      ]
    }
  }
}
```

4. 若修改配置后宿主要求重新连接/重启，明确告知用户所需的那一步。配置文件写入并不等于 MCP 已连通。宿主不支持运行时新增服务器时，不声称已在本轮对话获得工具。
5. 读取仓库 [SKILL.md](SKILL.md)，将其作为本规则查询工作流；支持技能安装的宿主可按自身规范安装它。MCP 同时提供相同核心服务器指令，即便宿主没有 Skill 功能也应执行。
6. 连通后调用 `search_rules("五色石")`，确认结果含真实条款（如 3.6.8）和 `ui_url`。再用 `search_rules("TR拿着五色石还能拿塔基吗？")` 验证 3.6.8 · P17、4.4.2 · P20。把完整链接告诉用户，组织回答后必须 `sync_answer`。

服务器经 stdio 启动；stdout 仅用于 MCP 协议。Web 界面在首次工具调用时自动启动，不需要用户单独运行 Web 服务、配置模型或填写密钥。不要把 MCP 命令作为一个会立即退出的普通命令执行后就宣称配置完成。

## 各宿主配置位置

### Claude Desktop

- Windows：`%APPDATA%\Claude\claude_desktop_config.json`
- macOS：`~/Library/Application Support/Claude/claude_desktop_config.json`

合并上面的 `mcpServers` 条目。Windows 的 `command` 推荐使用实际 `uvx.exe` 绝对路径。按宿主要求退出并重新打开应用，随后检查服务/工具是否加载。

### Cursor

- 用户级：`~/.cursor/mcp.json`
- 仅当前项目：`<项目>/.cursor/mcp.json`

合并上面的 JSON，然后在 MCP 设置中重新载入/启用服务。优先沿用用户现有的配置范围，不同时写入两处重复服务。

### 通用 stdio MCP

- command：`uvx` 的实际绝对路径
- args：`["--from", "git+https://github.com/ye-ling-xuan/robocon-nuwa-rules", "robocon-nuwa-mcp"]`
- transport：stdio
- env：不需要

也可直接运行：

```sh
uvx --from git+https://github.com/ye-ling-xuan/robocon-nuwa-rules robocon-nuwa-mcp
```

## 本地克隆 / 完全离线备用

```sh
git clone https://github.com/ye-ling-xuan/robocon-nuwa-rules
cd robocon-nuwa-rules
uv sync --frozen
```

将 MCP `command` 指向刚安装的可执行文件：

- Windows：`<仓库绝对路径>\.venv\Scripts\robocon-nuwa-mcp.exe`
- macOS/Linux：`<仓库绝对路径>/.venv/bin/robocon-nuwa-mcp`
- args：`[]`

无需设置工作目录。此安装方式在依赖下载完成后，启动和规则查询都不需要 GitHub。若没有 uv，可 `python -m venv .venv` 后用该环境的 Python 执行 `-m pip install .`。

如果 Git 协议受本机网络或已有代理配置影响，可下载 [GitHub 官方源码 ZIP](https://codeload.github.com/ye-ling-xuan/robocon-nuwa-rules/zip/refs/heads/main)，解压后在源码目录执行同一条 `uv sync --frozen`，再使用上面的本地可执行文件配置。Agent 可以自动下载和解压；不需要改动用户的全局代理设置。

更新远程安装可在维护时用 `uvx --refresh --from git+https://github.com/ye-ling-xuan/robocon-nuwa-rules robocon-nuwa-mcp` 重新缓存，再重启宿主。完全离线安装则 `git pull` 后重新 `uv sync --frozen`。已发布的引用可固定到 Git 提交，避免自动更新影响队内版本一致性。

## 无法自动修改宿主配置时

不要编造安装成功。输出上面的配置片段，使用本机检测到的绝对命令路径，明确指出应粘贴到哪一个配置文件，说明重新连接/重启步骤。若当前宿主没有 stdio MCP 支持，告知该限制并交付可在兼容宿主使用的配置。

## 验收

1. `search_rules` 返回完整会话链接，浏览器左侧出现问题，右侧第 17 页高亮 3.6.8。
2. 按引用给出结论并调用 `sync_answer`，原问题更新为一条完整问答，不重复插入。
3. 点击 4.4.2 · P20，原文切到第 20 页；缩放后高亮仍对应同一句。
4. `calc_score(items=[{"kind":"塔顶","count":1}], level="L2", question="L2 塔顶多少分？")` 返回 80 和 8.1.3 · P24，后续同步答案。
5. `judge_foul("TR 携带 4 个塔基会怎样？")` 返回超限携带犯规、强制重试和 6.5 · P23。
6. `check_protection` 未知塔状态留 null 并向用户澄清；不得把“有一个塔”判定为满足保护法则。

Sampling 按 MCP 初始化能力协商，不需要配置模型。若宿主不支持或拒绝网页发起的请求，网页禁用输入，仍可从 Agent 聊天框查询和同步。请保持宿主进程运行；每次重启会产生新的会话链接。
