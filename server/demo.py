"""Optional review session, explicitly labelled as examples rather than host output."""
from .tools.calc_score import ScoreItem


def populate(service):
    service.state.demo = True
    question = "TR拿着五色石还能拿塔基吗？"
    result = service.search_rules(question, 2)
    service.sync_answer(question, "不能。携带五色石时不得同时携带塔基/中段/塔顶。", result["citations"], result["turn_id"])
    question = "L2 塔顶多少分？"
    result = service.calc_score([ScoreItem(kind="塔顶")], "L2", question)
    service.sync_answer(question, f"在满足正确放置等计分条件时，L2 塔顶为 {result['total']} 分。", result["citations"], result["turn_id"])
    question = "TR 携带 4 个塔基会怎样？"
    result = service.judge_foul(question)
    service.sync_answer(question, "超限携带犯规，强制重试。超出限制后拿取的塔基须在重试时取出并禁用。", result["citations"], result["turn_id"])
    service.get_clause("3.6.8")
    service.state.publish("notice", {"message": "这是本地示例会话。接入自己的 Agent 后，真实问答将自动同步。"})
