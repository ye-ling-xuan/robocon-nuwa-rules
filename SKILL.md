---
name: robocon-nuwa-rules
description: 查询 ROBOCON 女娲补天 V3 规则、核算分值、核对携带犯规和保护法则，并把问答同步到本地 PDF 原文界面。用于本比赛的规则问询，不用于其它赛季或通用机器人知识。
---

# 女娲补天 V3 规则问答

通过本仓库的七个 MCP 工具检索随包原文。若尚未接入，按 [AGENT_INSTALL.md](AGENT_INSTALL.md) 完成当前宿主的 stdio MCP 配置。由宿主现有模型组织回答，不要求用户提供 API Key、Base URL 或模型名，不调用外部 LLM API。

## 查询并同步

1. 保留用户原问题，先调用 `search_rules(query=原问题)`。专门的算分、犯规和保护判断可使用下述工具，必要时补充检索。
2. 首次结果带 `ui_url` 时告诉用户：“已打开规则查询界面：<完整 ui_url>”。保持 `session` 参数；页面已由工具启动，不要求用户另开服务。
3. 只依据工具返回的 `citations` 和条款组织答案：先结论，再列 `[条款号 · P页码] 原文依据`。页码是 `page` 给出的 PDF 物理页码，不从记忆推断。必要时用 `get_clause` 读完整条款和关联规则。
4. 回答输出后**必须**调用 `sync_answer(question=原问题, answer=完整回答, citations=本次采用的引用, turn_id=本次返回的 turn_id)`。原样传回引用对象，不修改页码、quote、bbox 或 rects。也可仅传 `{"clause_id":"3.6.8"}`，服务器会从权威数据补齐其它字段。
5. 没有依据或检索结果不足以支持结论时，回答并同步“规则未明确，请以原文/裁判为准。”，使用空 citations。不得把关键词命中当成结论已经得到证明。
6. 用户说“看原文”“翻到那一页”，调用 `get_clause(clause_id)` 或 `open_ui()`，返回工具实际给出的链接。点击网页引用由本地服务跳页，无需再问用户。

示例：

> 不能。携带五色石时不得同时携带塔基/中段/塔顶。
>
> 依据：
>
> [3.6.8 · P17] 携带五色石的机器人不得携带任何塔基/中段/塔顶。
>
> [4.4.2 · P20] 携带五色石时不得携带其它比赛用品。

这个示例的引用也必须通过当前连接实际检索取得。不要使用示例作为新版本规则的权威来源。

## 专门判断

- `calc_score(items, level, question=原问题)`：如 `items=[{"kind":"塔顶","count":1}], level="L2"`。kind 支持塔基/中段/塔顶/五色石及 base/middle/top/stone。默认 `mode=build` 仅算安放分；搬运使用 `mode=transport`。说明假设物品已经满足放置、脱离机器人和颜色归属条件，不能凭数量断言现场总分。完成回答后同步该工具的 citations/turn_id。
- `judge_foul(action=原问题)`：明确的超限携带可给出相应结论；`needs_clarification` 要补充事实，`needs_referee` 只说明候选依据，不能升级为确定犯规。TR/BR 持有数量按同一时刻合计。
- `check_protection(towers, previously_satisfied, question=原问题)`：每个塔提供唯一 id、zone（L1_private/L1_public/L2）、standing、complete、in_build_site、top_matches_team。这些是同一时刻的状态；未知留 null，不替用户补成 true。complete 指正确垂直堆叠的完整结构；本队归属由塔顶单色顶面决定。只有用户确认此前已满足时才设 `previously_satisfied=true`。`satisfied=null` 时先澄清；须使用 3.6.1 及相关定义核对。

如果先检索再调用专门工具，将同一个原问题传入 question/action，使界面更新同一条待答记录。同步时使用最后一次工具返回的 turn_id。

## 必须保持的事实边界

禁止编造条款号、页码、原文、现场状态或不存在的处罚。不以其它版本规则替代当前 V3；冲突或歧义应引用相关原文交由裁判确认。找不到原文时不“补全”规则。

界面的模型输入能力由宿主 MCP Sampling 协商决定。若不支持，就继续在 Agent 聊天框接收问题；不要要求用户为了网页输入而额外配置模型。宿主 MCP 配置是否可自动写入，按当前环境权限与能力处理；未成功连通时不要声称安装完成。
