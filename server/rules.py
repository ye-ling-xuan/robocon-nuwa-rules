"""Authoritative local rule store and deterministic keyword retrieval."""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import re
import unicodedata
from pathlib import Path
from typing import Any

DATA_DIR = Path(__file__).resolve().parent / "data"
UNSPECIFIED = "规则未明确，请以原文/裁判为准。"


def normalize(value: str) -> str:
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", value)).lower()


ALIASES = {
    "携带": ("拿", "持有", "抓", "抬起", "带着", "装着", "携带"),
    "塔基": ("底座", "底部", "塔基"), "中段": ("中部", "中段"),
    "塔顶": ("顶部", "塔顶"), "五色石": ("补天石", "五色石"),
    "保护法则": ("保护规则", "保护法则"), "重试": ("重来", "重置", "重试"),
    "分值": ("分值", "多少分", "得几分", "几分", "分数", "得分", "记分", "计分"),
    "持平": ("平分", "同分", "平局", "破平", "持平"),
    "尺寸": ("多大", "大小", "尺寸"), "重量": ("多重", "重量"),
    "通信": ("通讯", "发信号", "通信"),
}


class RuleStore:
    def __init__(self, data_dir: Path = DATA_DIR):
        self.data_dir = data_dir
        self.clauses = json.loads((data_dir / "clauses.json").read_text(encoding="utf-8"))
        self.meta = json.loads((data_dir / "page_map.json").read_text(encoding="utf-8"))
        self.by_id = {c["clause_id"]: c for c in self.clauses}
        if len(self.by_id) != len(self.clauses):
            raise ValueError("Duplicate clause IDs in rules data")
        if hashlib.sha256((data_dir / "rules.pdf").read_bytes()).hexdigest() != self.meta["pdf_sha256"]:
            raise ValueError("Rules PDF changed. Rebuild and validate clauses.json and page_map.json.")
        self.texts = {c["clause_id"]: normalize(c["text"]) for c in self.clauses}
        self.vocabulary = {k for c in self.clauses for k in c["keywords"]} | set(ALIASES)

    def get(self, clause_id: str) -> dict:
        if clause_id not in self.by_id:
            raise ValueError(f"规则中不存在条款 {clause_id}")
        return deepcopy(self.by_id[clause_id])

    def citation(self, clause_id: str) -> dict:
        clause = self.get(clause_id)
        return {**{key: clause[key] for key in ("clause_id", "chapter", "page", "quote")},
                "bbox": clause.get("bbox"), "rects": clause.get("rects", []),
                "cross_page": clause.get("cross_page", False), "segments": clause.get("segments", [])}

    def citations(self, ids: list[str]) -> list[dict]:
        return [self.citation(cid) for cid in dict.fromkeys(ids)]

    def canonicalize(self, citations: list[dict[str, Any]]) -> list[dict]:
        """Only data-backed IDs, pages, quotes and coordinates may enter the UI."""
        if len(citations) > 16:
            raise ValueError("一次最多同步 16 条引用")
        result = []
        seen = set()
        for provided in citations:
            if not isinstance(provided, dict) or not isinstance(provided.get("clause_id"), str):
                raise ValueError("引用必须包含 clause_id")
            c = self.citation(provided["clause_id"])
            if "page" in provided and (type(provided["page"]) is not int or provided["page"] != c["page"]):
                raise ValueError(f"{c['clause_id']} 的页码必须来自规则数据：P{c['page']}")
            if "quote" in provided and normalize(provided["quote"]) != normalize(c["quote"]):
                raise ValueError(f"{c['clause_id']} 的引用原文与规则数据不符")
            for field in ("bbox", "rects", "segments"):
                if field in provided and provided[field] != c[field]:
                    raise ValueError(f"{c['clause_id']} 的 {field} 与规则数据不符")
            if c["clause_id"] not in seen:
                result.append(c)
                seen.add(c["clause_id"])
        return result

    def search(self, query: str, limit: int = 5) -> list[dict]:
        if not query.strip() or len(query) > 4000:
            raise ValueError("问题应为 1 到 4000 字符")
        if not 1 <= limit <= 12:
            raise ValueError("limit 必须为 1 到 12")
        q = normalize(query)
        explicit = re.findall(r"(?<![\d.])\d{1,2}(?:\.\d+){1,2}(?![\d.])", q)
        if explicit:
            return self.citations([cid for cid in explicit if cid in self.by_id][:limit])
        terms = {k for k in self.vocabulary if normalize(k) in q}
        for term, variants in ALIASES.items():
            if any(normalize(v) in q for v in variants):
                terms.add(term)
        # A generic word by itself is insufficient evidence of a rule match.
        if not terms - {"机器人", "同时", "携带", "得分", "分值", "安全", "TR", "BR"}:
            return []
        boosts: dict[str, float] = {}
        building = bool(terms & {"塔基", "中段", "塔顶"})
        if "五色石" in terms and "携带" in terms and building:
            boosts.update({"3.6.8": 100, "4.4.2": 95, "3.4.6": 35, "6.5": 30})
        if "保护法则" in terms:
            boosts.update({"3.6.1": 100, "3.6.2": 70, "4.5.1": 40, "2.22": 20})
        if "分值" in terms:
            boosts["8.1.3"] = 100 if building else 15
            if "五色石" in terms:
                boosts["8.1.5"] = 110
            if "搬运" in q or "运送" in q:
                boosts["8.1.1"] = 115
        if "持平" in terms:
            boosts["9.2"] = 100
        if building and ("携带" in terms or "超限" in q) and re.search(r"犯规|怎样|处罚|超限|[4-9四五六七八九]\s*个", q):
            boosts.update({"6.5": 150, "4.4.2": 85})
        ranked = []
        for clause in self.clauses:
            cid = clause["clause_id"]
            text = self.texts[cid]
            score = sum((1 if k in {"机器人", "TR", "BR", "L1", "L2", "同时"} else 4) for k in terms if normalize(k) in text)
            score += boosts.get(cid, 0)
            if len(text) < 18 or "." not in cid:
                score -= 15
            if score >= 4:
                # Prefer direct, short rules when relevance is otherwise equal.
                ranked.append((score - min(len(text), 1200) / 2000, cid))
        ranked.sort(key=lambda pair: (-pair[0], tuple(int(n) for n in pair[1].split("."))))
        if ranked and ranked[0][0] >= 80:
            ranked = [pair for pair in ranked if pair[0] >= ranked[0][0] * .65]
        return self.citations([cid for _, cid in ranked[:limit]])

    def validate_answer(self, answer: str, citations: list[dict]) -> str:
        if not citations:
            return UNSPECIFIED
        answer = answer.strip()
        if not answer or len(answer) > 20000:
            raise ValueError("回答应为 1 到 20000 字符")
        expected = {c["clause_id"]: c["page"] for c in citations}
        refs = re.findall(r"\[(\d+(?:\.\d+){0,2})\s*[·•|]\s*P\s*(\d+)\]", answer)
        for cid, page in refs:
            if expected.get(cid) != int(page):
                raise ValueError(f"回答中的 [{cid} · P{page}] 不在本次权威引用中")
        if not refs:
            answer += "\n\n依据：\n" + "\n".join(f"[{c['clause_id']} · P{c['page']}] {c['quote']}" for c in citations)
        return answer
