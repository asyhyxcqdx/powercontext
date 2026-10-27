"""Deterministic group-meeting / weekly report composition.

No LLM is required: the draft is assembled from seekdb-retrieved notes and
PowerContext memories so every line has a traceable source.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any


def _clean(text: str, limit: int = 240) -> str:
    value = " ".join((text or "").split())
    if len(value) <= limit:
        return value
    return value[:limit].rstrip() + "…"


def _key_points(document: str, title: str) -> str:
    body = (document or "").replace(title, " ", 1)
    sentences = []
    for chunk in body.replace("！", "。").replace("？", "。").split("。"):
        sentence = " ".join(chunk.split())
        if len(sentence) >= 12:
            sentences.append(sentence)
        if len(sentences) >= 2:
            break
    return "。".join(sentences) + ("。" if sentences else _clean(body, 200))


def _week_bounds(week_start: str | None, week_end: str | None) -> tuple[date, date]:
    if week_start:
        start = date.fromisoformat(week_start)
    else:
        today = date.today()
        start = today - timedelta(days=today.weekday())
    if week_end:
        end = date.fromisoformat(week_end)
    else:
        end = start + timedelta(days=6)
    return start, end


def _in_week(note: dict[str, Any], start: date, end: date) -> bool:
    raw = str(note.get("updated_at") or note.get("created_at") or "")
    try:
        day = datetime.fromisoformat(raw.replace("Z", "+00:00")).date()
    except ValueError:
        try:
            day = datetime.strptime(raw[:10], "%Y-%m-%d").date()
        except ValueError:
            return False
    return start <= day <= end


def _memory_lines(entries: list[dict[str, Any]], kinds: tuple[str, ...]) -> list[str]:
    lines = []
    for entry in entries:
        if entry.get("kind") in kinds and entry.get("state", "active") == "active":
            lines.append(_clean(entry.get("text", ""), 180))
    return lines


def build_report(
    notes: list[dict[str, Any]],
    entries: list[dict[str, Any]],
    prepared: str | None,
    week_start: str | None = None,
    week_end: str | None = None,
    scope: str = "",
) -> dict[str, Any]:
    start, end = _week_bounds(week_start, week_end)
    this_week = [n for n in notes if _in_week(n, start, end)]
    candidates = this_week or notes[:8]
    papers = [n for n in candidates if n.get("kind") == "paper"]
    others = [n for n in candidates if n.get("kind") != "paper"]

    goals = _memory_lines(entries, ("working_note", "constraint"))
    preferences = _memory_lines(entries, ("preference",))
    decisions = _memory_lines(entries, ("decision",))

    lines: list[str] = []
    lines.append(f"# 组会周报 · {start.strftime('%Y-%m-%d')} ~ {end.strftime('%Y-%m-%d')}")
    lines.append("")
    lines.append("> 由 LitMemory 自动草拟：检索证据来自 seekdb，研究上下文来自 PowerContext。")
    lines.append("")
    lines.append("## 一、本周概览")
    lines.append(
        f"- 本周共整理 **{len(candidates)}** 条资料：论文 {len(papers)} 篇，笔记/记录 {len(others)} 条。"
    )
    if goals:
        lines.append(f"- 当前研究目标：{goals[0]}")
    elif preferences:
        lines.append(f"- 研究方向：{preferences[0]}")
    else:
        lines.append("- 尚未在「研究记忆」中记录本周目标，建议先补充一条进行中事项。")
    lines.append("")

    lines.append("## 二、阅读与关键发现")
    if papers:
        for paper in papers:
            title = paper.get("title") or "未命名文献"
            year = paper.get("year") or ""
            meta = f"（{year}）" if year else ""
            body = paper.get("content") or paper.get("document", "")
            lines.append(f"### {title}{meta}")
            lines.append(f"- 要点：{_key_points(body, title)}")
            if paper.get("tags"):
                lines.append(f"- 标签：{'、'.join(paper.get('tags', []))}")
            if paper.get("source"):
                lines.append(f"- 来源：{paper.get('source')}")
            lines.append("")
    else:
        lines.append("- 本周没有新增论文记录，可补充阅读笔记后再生成。")
        lines.append("")

    if others:
        lines.append("### 笔记与实验记录")
        for note in others[:6]:
            body = note.get("content") or note.get("document", "")
            lines.append(
                f"- **{note.get('title') or '未命名记录'}**：{_key_points(body, note.get('title', ''))}"
            )
        lines.append("")

    lines.append("## 三、与研究目标的关系")
    if prepared:
        for line in prepared.strip().splitlines():
            cleaned = line.strip().lstrip("-• ").strip()
            if cleaned and not cleaned.startswith("#"):
                lines.append(f"- {_clean(cleaned, 220)}")
    elif decisions or preferences:
        for line in (decisions + preferences)[:5]:
            lines.append(f"- {line}")
    else:
        lines.append("- 暂无可复用的研究记忆，建议先在「研究记忆」中记录方向与已定结论。")
    lines.append("")

    lines.append("## 四、下周计划")
    if goals:
        for line in goals[:4]:
            lines.append(f"- [ ] {line}")
    else:
        lines.append("- [ ] 补充本周阅读笔记，并记录下周研究目标。")
    lines.append("")

    lines.append("## 五、待确认问题")
    lines.append("- 本周的关键结论是否有可复现的实验数据支撑？")
    lines.append("- 与导师/同学讨论后，是否需要调整研究方向或优先级？")
    if not decisions:
        lines.append("- 组会上需要明确的决策点尚未记录到「研究记忆」。")
    lines.append("")

    lines.append("## 附：证据索引")
    lines.append(f"- seekdb：数据库 `litmemory`，集合 `litmemory_notes`，命中资料 {len(candidates)} 条。")
    lines.append(f"- PowerContext：scope `{scope}`，可复用记忆 {len(entries)} 条。")
    for paper in papers[:8]:
        lines.append(f"  - 文献 `{paper.get('id')}` · {paper.get('title')}")
    for entry in entries[:8]:
        citation = entry.get("citation", {})
        lines.append(
            f"  - 记忆 `{entry.get('kind')}` · entry_id={citation.get('entry_id', '')[:12]} · {_clean(entry.get('text', ''), 80)}"
        )
    lines.append("")

    markdown = "\n".join(lines)
    return {
        "markdown": markdown,
        "week_start": start.isoformat(),
        "week_end": end.isoformat(),
        "stats": {
            "candidates": len(candidates),
            "papers": len(papers),
            "notes": len(others),
            "memories": len(entries),
        },
        "evidence": {
            "note_ids": [n.get("id") for n in candidates],
            "memory_entries": [
                {
                    "kind": e.get("kind"),
                    "entry_id": e.get("citation", {}).get("entry_id"),
                    "text": e.get("text"),
                }
                for e in entries[:12]
            ],
            "scope": scope,
        },
    }
