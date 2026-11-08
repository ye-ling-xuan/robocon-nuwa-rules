# 验证方法

先 `uv sync --extra dev --frozen`，然后执行：

```sh
uv run python scripts/validate_clauses.py
uv run pytest
npm install
npx playwright install chromium
npm run test:browser
```

浏览器测试用本地 `.venv` 中的 Python 启动真正的 stdio MCP 服务；Playwright 操作实际 PDF.js 页面。测试宿主的 Sampling 回调返回固定的有依据回答，仅用来验证协议传递，不连接任何模型 API。

可用 `NUWA_TEST_PYTHON` 指定其它已安装本项目的 Python，用 `NUWA_TEST_BROWSER` 指定本机 Chromium/Edge 可执行文件。两者仅是测试运行器选项，正常使用无需配置。截图保存在 `tmp/browser/`，不提交测试进程或会话标识。

验证内容包括：原文与坐标全量校验、两个直接携带条款、同条问答更新、引用切页、随缩放定位、没有 bbox 时跨文本匹配、计分和犯规、保护条件及信息不足、跨页提示、无依据回退、刷新恢复、端口冲突、会话隔离/同源保护、Sampling 支持与不支持/错误引用回退。真实桌面宿主是否按要求调用 `sync_answer`，还须在所选宿主实际连接后确认。
