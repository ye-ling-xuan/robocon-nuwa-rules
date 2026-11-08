# 验证记录 · 2026-11-08

在 Windows 本机完成以下验证，不需要任何模型 API 配置。

- `python scripts/validate_clauses.py`：188 个条款/章节条目的编号、物理页码、引用片段、PDF SHA-256 和每个高亮矩形全量通过校验。
- `pytest -q`：54 项通过，包含真实 MCP stdio 子进程的七个工具、网页到宿主的 Sampling 回调、未知/被篡改引用的回退、计分、保守犯规判断、保护法则、SSE、端口冲突与本地会话保护。该电脑的默认 pytest 临时目录不可写，执行时使用 `--basetemp=tmp/pytest-final`；这是测试输出目录设置。
- `npm run test:browser`：Playwright 1.61.1 驱动本机 Edge，使用真实 MCP 服务和 PDF.js 页面，完成连续五次问答、首问 P17 高亮、点击 P20 引用、缩放比例核对、80 分计分、超限携带、保护判断、跨页、清除高亮、刷新恢复、quote-only 高亮及 390px 手机布局验证。
- 浏览器支持 Sampling 时，实际通过本地 POST → MCP `sampling/createMessage` → 测试宿主回调 → SSE 完成网页提问。测试回调返回固定的有效 JSON 答案，不是实际 LLM 输出；另有非法条款响应被丢弃的测试。
- 浏览器验收期间禁止非本地请求，实际记录为 0 条外部请求。PDF、CMaps、字体和 WASM 全部由本机提供。
- `python -X utf8 .../quick_validate.py .`：SKILL.md 通过技能格式校验。
- Python wheel 已构建并核查所需数据、PDF.js worker、字体、CMaps、WASM 均包含在安装包内。依赖锁使用公开的 PyPI / npm 地址。

主要环境：Python 3.12、mcp 1.30.0、FastAPI 0.162.2、PyMuPDF 1.28.2、PDF.js 5.6.205。测试框架有一条 Starlette/httpx 接口未来迁移提示，不影响当前通过的结果。

此记录不声称已经在某个具体版本的 Claude Desktop / Cursor 中完成真实模型对话验收。宿主是否遵守回答后调用 `sync_answer`、是否批准独立 Sampling 请求，还取决于用户选择的客户端。GitHub Actions 对 Windows/Linux 和 Python 3.11/3.12 的结果以仓库实际运行记录为准。
