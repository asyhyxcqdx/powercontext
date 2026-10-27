"""Demo corpus for LitMemory: an AI-agent-memory researcher's notebook."""
from __future__ import annotations

from datetime import datetime
from typing import Any

SEED_NOTES: list[dict[str, Any]] = [
    {
        "id": "paper_memgpt",
        "title": "MemGPT: Towards LLMs as Operating Systems",
        "kind": "paper",
        "authors": "Packer et al.",
        "year": 2023,
        "tags": "长期记忆,虚拟上下文,操作系统隐喻",
        "source": "arXiv:2310.08560",
        "content": "MemGPT 把大模型上下文窗口类比为操作系统内存，通过主上下文与外部上下文的分层管理、分页与中断机制，让 Agent 在有限上下文内维持长期记忆。核心贡献是把记忆读写变成可调度的系统调用，并在多轮对话与文档问答中验证跨会话一致性。局限是记忆检索策略仍以规则和摘要为主，缺少与检索质量的联合优化。",
    },
    {
        "id": "paper_mem0",
        "title": "Mem0: Building Production-Ready AI Agents with Scalable Long-Term Memory",
        "kind": "paper",
        "authors": "Chhikara et al.",
        "year": 2025,
        "tags": "长期记忆,记忆抽取,图记忆,生产可用",
        "source": "arXiv:2504.19413",
        "content": "Mem0 提出抽取-整合-检索的三段式记忆管线：从对话中抽取事实与偏好，与已有记忆做增删改整合，再按查询检索相关条目。论文报告在 LOCOMO 等基准上相较全上下文方案显著降低 token 消耗并提升答案质量，同时讨论了图结构记忆对多跳问题的帮助。工程上强调可部署性与延迟控制。",
    },
    {
        "id": "paper_amem",
        "title": "A-MEM: Agentic Memory for LLM Agents",
        "kind": "paper",
        "authors": "Xu et al.",
        "year": 2025,
        "tags": "记忆网络,Zettelkasten,动态链接,记忆演化",
        "source": "arXiv:2502.12110",
        "content": "A-MEM 借鉴 Zettelkasten 卡片盒笔记法，把每条记忆建模为带上下文描述、关键词与标签的原子笔记，并通过动态链接形成记忆网络。新记忆写入时会寻找语义近邻并建立关联，旧记忆可被更新与演化。实验中在长对话与多跳问答上优于扁平向量记忆，说明结构化关联对记忆复用很重要。",
    },
    {
        "id": "paper_genagents",
        "title": "Generative Agents: Interactive Simulacra of Human Behavior",
        "kind": "paper",
        "authors": "Park et al.",
        "year": 2023,
        "tags": "记忆流,反思,新近性,重要性,相关性",
        "source": "arXiv:2304.03442",
        "content": "Generative Agents 用记忆流记录 Agent 的全部经历，检索时综合新近性、重要性与相关性打分，并周期性生成反思形成高层记忆。小镇实验表明记忆与反思能让 Agent 产生连贯的长期行为。该工作给出了记忆评分函数的经典基线，但反思依赖 LLM，成本较高。",
    },
    {
        "id": "paper_reflexion",
        "title": "Reflexion: Language Agents with Verbal Reinforcement Learning",
        "kind": "paper",
        "authors": "Shinn et al.",
        "year": 2023,
        "tags": "反思,情景记忆,强化学习,失败复盘",
        "source": "arXiv:2303.11366",
        "content": "Reflexion 让 Agent 在任务失败后生成语言化反思，把反思写入情景记忆，并在后续尝试中作为上下文复用，从而不更新模型参数也能提升表现。在代码生成与决策任务上验证了失败复盘的价值。关键启示是记忆不仅保存事实，也应保存可操作的教训。",
    },
    {
        "id": "paper_voyager",
        "title": "Voyager: An Open-Ended Embodied Agent with Large Language Models",
        "kind": "paper",
        "authors": "Wang et al.",
        "year": 2023,
        "tags": "技能库,终身学习,代码即技能,开放世界",
        "source": "arXiv:2305.16291",
        "content": "Voyager 在 Minecraft 中通过自动课程、技能库与迭代提示实现开放世界探索。技能以可执行代码形式存入技能库，需要时检索复用，形成终身学习闭环。它说明记忆的载体可以是可执行资产，而不只是自然语言条目。",
    },
    {
        "id": "paper_hipporag",
        "title": "HippoRAG: Neurobiologically Inspired Long-Term Memory for Large Language Models",
        "kind": "paper",
        "authors": "Gutiérrez et al.",
        "year": 2024,
        "tags": "知识图谱,PageRank,多跳检索,海马体",
        "source": "arXiv:2405.14831",
        "content": "HippoRAG 受海马体索引理论启发，把文档构建成知识图谱，并用个性化 PageRank 在图上做多跳检索，再交给 LLM 生成答案。相比纯向量检索，它在多跳问答上召回更高且更省 token。启示是图结构索引可以弥补稠密向量对关系建模的不足。",
    },
    {
        "id": "paper_graphrag",
        "title": "From Local to Global: A Graph RAG Approach to Query-Focused Summarization",
        "kind": "paper",
        "authors": "Edge et al.",
        "year": 2024,
        "tags": "GraphRAG,社区摘要,全局问题,实体图",
        "source": "arXiv:2404.16130",
        "content": "GraphRAG 先抽取实体与关系构建图，再做社区发现并为每个社区生成摘要，查询时结合局部实体与全局社区摘要。它擅长回答需要跨文档汇总的全局性问题，代价是构图与摘要的预处理成本较高。",
    },
    {
        "id": "paper_selfrag",
        "title": "Self-RAG: Learning to Retrieve, Generate, and Critique through Self-Reflection",
        "kind": "paper",
        "authors": "Asai et al.",
        "year": 2023,
        "tags": "自适应检索,自我批判,反思token,RAG",
        "source": "arXiv:2310.11511",
        "content": "Self-RAG 训练模型在生成过程中输出反思 token，自主决定是否需要检索、检索结果是否相关、生成内容是否被支持。它把检索从固定管线变成模型可控的动作，在多个问答基准上提升事实性并减少无关检索。",
    },
    {
        "id": "paper_longmem",
        "title": "Augmenting Language Models with Long-Term Memory",
        "kind": "paper",
        "authors": "Wang et al.",
        "year": 2023,
        "tags": "长期记忆库,残差侧网络,缓存,长上下文",
        "source": "arXiv:2306.07174",
        "content": "LongMem 设计长期记忆库缓存历史键值，并用残差侧网络融合记忆读取结果，使模型在不扩展主上下文的情况下利用久远信息。它从模型结构层面讨论记忆，与检索式记忆形成互补。",
    },
    {
        "id": "note_group_20261023",
        "title": "组会纪要 · 2026-10-23 混合检索基线",
        "kind": "note",
        "authors": "",
        "year": 2026,
        "tags": "组会,混合检索,基线,召回率",
        "source": "组会记录",
        "content": "本次组会讨论了三类记忆方案：MemGPT 的分层上下文、Mem0 的抽取-整合管线、A-MEM 的卡片网络。决定先做 seekdb 混合检索基线，用 BM25/全文 + 向量 + RRF 融合，数据集选用实验室内部文献库。导师要求下周补充 Recall@5、MRR 与 token 消耗对比，并说明记忆复用带来的跨会话收益。",
    },
    {
        "id": "note_amem_reading",
        "title": "阅读笔记 · A-MEM 的卡片链接机制",
        "kind": "note",
        "authors": "",
        "year": 2026,
        "tags": "A-MEM,卡片盒,记忆链接,阅读笔记",
        "source": "个人笔记",
        "content": "A-MEM 最值得借鉴的是写入时就建立语义链接，而不是查询时才做近邻搜索。我们可以把 seekdb 的向量近邻结果作为候选链接，再用全文匹配确认主题一致性。风险是链接过多导致噪声，需要设置相似度阈值并定期衰减。",
    },
    {
        "id": "note_experiment_plan",
        "title": "实验计划 · 混合检索对比（Recall@5 / MRR）",
        "kind": "log",
        "authors": "",
        "year": 2026,
        "tags": "实验,消融,Recall@5,MRR,token",
        "source": "实验记录",
        "content": "实验分三组：A 纯向量检索；B 纯全文检索；C 向量+全文+标量过滤的 RRF 融合。统一用同一批查询与人工标注的相关段落。指标：Recall@5、MRR、平均响应时间、注入上下文的 token 数。预期 C 组在中文专有名词和长尾概念上更稳。失败案例分析要记录检索为空与误召回两类。",
    },
    {
        "id": "note_advisor_feedback",
        "title": "导师反馈 · 不要只堆模型",
        "kind": "note",
        "authors": "",
        "year": 2026,
        "tags": "导师反馈,叙事,跨会话,真实收益",
        "source": "导师邮件",
        "content": "导师强调：不要只比较模型规模，要把叙事放在“记忆被保存并在后续会话中复用”上。建议用真实使用日志证明跨会话收益，例如第二次会话不再重复交代研究背景，周报初稿直接引用上次结论。还要避免把 embedding 模型当成黑盒，说明检索失败时如何降级。",
    },
    {
        "id": "note_research_question",
        "title": "研究问题 · 如何在不膨胀上下文的前提下复用研究记忆",
        "kind": "note",
        "authors": "",
        "year": 2026,
        "tags": "研究问题,上下文预算,记忆选择,个性化",
        "source": "研究日志",
        "content": "核心问题：面对长期科研过程，Agent 如何在有限上下文预算内选择最相关的记忆？需要同时考虑查询相关性、记忆时效性、重要性与冗余度。计划把 seekdb 的检索分数与 PowerContext 的记忆条目结合，做一个可解释的选择策略，并在组会汇报中给出消融结果。",
    },
    {
        "id": "note_weekly_draft",
        "title": "周报草稿 · 第 43 周",
        "kind": "log",
        "authors": "",
        "year": 2026,
        "tags": "周报,进展,组会",
        "source": "周报草稿",
        "content": "本周完成文献梳理 6 篇，重点读完 Mem0、A-MEM、HippoRAG；搭好 seekdb 混合检索原型；整理出三组对比实验设计。下周计划：补齐基线数据、完成失败案例分析、准备组会 10 分钟汇报。",
    },
]

INITIAL_MEMORIES: list[dict[str, str]] = [
    {
        "kind": "preference",
        "text": "我的研究方向是 AI Agent 的长期记忆机制，重点关注跨会话记忆复用、混合检索与上下文预算分配。",
    },
    {
        "kind": "preference",
        "text": "写材料时偏好结构化中文表达：先给结论，再列证据，最后写风险与下一步。",
    },
    {
        "kind": "working_note",
        "text": "本周目标：完成 seekdb 混合检索基线（向量+全文+标量过滤），并在组会上汇报 Recall@5 与 MRR 对比。",
    },
    {
        "kind": "decision",
        "text": "2026-10-23 组会决定：优先做混合检索对比实验，图记忆模块暂缓到下一阶段。",
    },
    {
        "kind": "fact",
        "text": "导师要求每周五下午组会，汇报必须包含数据、失败案例和下一步计划。",
    },
    {
        "kind": "working_note",
        "text": "上次会话结论：Mem0 的抽取-整合流程适合作为记忆写入管线参考；A-MEM 的写入时链接值得借鉴但要控制噪声。",
    },
]


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def seed_payload() -> list[dict[str, Any]]:
    now = _now()
    items = []
    for item in SEED_NOTES:
        items.append({**item, "created_at": now, "updated_at": now})
    return items


async def ensure_memories(memory_service) -> int:
    """Add demo memories only when the scope is still empty."""
    existing = await memory_service.list_entries()
    texts = {" ".join(e.get("text", "").split()) for e in existing.get("entries", [])}
    added = 0
    for item in INITIAL_MEMORIES:
        normalized = " ".join(item["text"].split())
        if normalized in texts:
            continue
        await memory_service.remember(item["kind"], item["text"], reason="LitMemory demo seed")
        added += 1
    return added
