# 验证记录 · LitMemory

本文记录 LitMemory 在真实环境中的端到端验证结果，对应赛题「验证样例」提交项。
所有输出均来自 2026-10-28 的实际运行，未做修饰。

## 1. 验证环境

| 组件 | 版本 / 配置 |
| --- | --- |
| 操作系统 | Linux（阿里云 ECS），Python 3.12 venv |
| seekdb | 1.4.0.post1，`127.0.0.1:2881` |
| 数据库 / 集合 | `litmemory` / `litmemory_notes`（HNSW cosine + IK 全文索引） |
| PowerContext | `archive/powercontext-main`，Server 监听 `127.0.0.1:8000`，scope `project:litmemory:demo` |
| 嵌入模型 | `BAAI/bge-small-zh-v1.5`（fastembed，512 维，本地推理） |
| 应用 | FastAPI + Uvicorn，`0.0.0.0:8765` |
| 项目官网 | `https://litmemory-c8a8093w5oo.qoder.zone`（Qoder Sites，公开访问） |
| 演示入口 | `https://rebates-summer-tale-solely.trycloudflare.com`（Cloudflare Quick Tunnel，临时域名） |

## 2. 一键验证

```bash
cd /root/litmemory
.venv/bin/python scripts/verify.py --base http://127.0.0.1:8765
```

实际输出：

```text
{
  "seekdb": {
    "ok": true,
    "error": null,
    "database": "litmemory",
    "collection": "litmemory_notes",
    "count": 16,
    "dimension": 512
  },
  "powercontext": {
    "ok": true,
    "scope": "project:litmemory:demo",
    "readiness": {
      "status": "ready",
      "checks": {
        "runtime": "ready"
      }
    }
  },
  "embedding": {
    "backend": "fastembed",
    "model": "BAAI/bge-small-zh-v1.5",
    "dim": 512,
    "fallback_reason": null
  }
}
[PASS] seekdb reachable — litmemory_notes
[PASS] PowerContext reachable — project:litmemory:demo
[PASS] demo corpus seeded — 16 notes
       demo memories added: 0
[PASS] hybrid search returns hits — engine=seekdb-hybrid elapsed=22.5ms
       query: 如何在有限上下文预算内复用研究记忆？
       - 0.0328 · 研究问题 · 如何在不膨胀上下文的前提下复用研究记忆
       - 0.032 · MemGPT: Towards LLMs as Operating Systems
       - 0.0318 · 导师反馈 · 不要只堆模型
[PASS] memory written to PowerContext — mem_ent_eb196d3df77643c5b4a03711428615fd
[PASS] recall returns the new memory — mode=fts bytes=1364
[PASS] weekly report rendered — 4994 chars, {'candidates': 16, 'papers': 10, 'notes': 6, 'memories': 7}

All checks passed.
Open the UI at http://127.0.0.1:8765 and the API docs at http://127.0.0.1:8765/docs
```

> 说明：验证脚本会写入一条带时间戳的「验证记忆」以证明读写闭环。验证完成后该条目已 retire，
> 演示数据恢复为 6 条有效记忆；因此下文周报统计为 6 条记忆。

## 3. 关键证据

### 3.1 健康检查

```json
{
  "app": "ok",
  "seekdb": {"ok": true, "database": "litmemory", "collection": "litmemory_notes", "count": 16, "dimension": 512},
  "powercontext": {"ok": true, "scope": "project:litmemory:demo", "readiness": {"status": "ready"}},
  "embedding": {"backend": "fastembed", "model": "BAAI/bge-small-zh-v1.5", "dim": 512, "fallback_reason": null}
}
```

### 3.2 seekdb 混合检索

查询：`如何在有限上下文预算内复用研究记忆`，`top_k=5`，无标签过滤。

| 排名 | 类型 | 标题 | RRF 分数 |
| --- | --- | --- | --- |
| 1 | 笔记 | 研究问题 · 如何在不膨胀上下文的前提下复用研究记忆 | 0.0328 |
| 2 | 论文 | MemGPT: Towards LLMs as Operating Systems | 0.0320 |
| 3 | 笔记 | 导师反馈 · 不要只堆模型 | 0.0318 |
| 4 | 论文 | Reflexion: Language Agents with Verbal Reinforcement Learning | 0.0313 |
| 5 | 论文 | A-MEM: Agentic Memory for LLM Agents | 0.0303 |

`engine=seekdb-hybrid`，单次检索约 10–140 ms（含本地 embedding）。
混合检索的 `distances` 是 RRF 融合相关度，**越高越相关**；应用在响应中同时保留 `score` 与原始 `distance`，
并在检索页展示引擎、数据库、集合、嵌入模型与耗时，便于复核。

### 3.3 PowerContext 上下文召回

```json
{
  "mode": "fts",
  "hits": 1,
  "prepared": {"status": "ready", "content_bytes": 726},
  "query": "本周研究目标与已定结论"
}
```

`prepared.content` 为可直接注入提示词的 `BEGIN_POWERCONTEXT_PREPARED_CONTEXT_V1` 上下文块，
包含 `memory_ref`、`entry_id` 与条目正文。中文查询走 FTS 时按字与二元组建 token，能够命中中文记忆。

### 3.4 组会周报

```json
{
  "chars": 4890,
  "stats": {"candidates": 16, "papers": 10, "notes": 6, "memories": 6}
}
```

周报由 seekdb 条目与 PowerContext 记忆确定性渲染，包含 `## 二、阅读与关键发现` 与 `证据索引`，
每条要点可回指条目 id 或 `entry_id`。

## 4. 界面回归

五张截图均为 2026-10-28 01:45 从公网演示地址实际访问后截取（1440px 宽）：

| 截图 | 验证内容 |
| --- | --- |
| `screenshots/01-dashboard.png` | 服务状态、16 条知识、16 个向量、6 条记忆；最近检索与记忆日志 |
| `screenshots/02-library.png` | 文献库 16 条，类型/年份/标签元信息 |
| `screenshots/03-search.png` | `seekdb-hybrid`、证据栏、RRF 分数与原始 distance |
| `screenshots/04-memory.png` | 6 条有效记忆、写入表单、`prepare_context` 上下文块 |
| `screenshots/05-report.png` | 2026-10-25 ~ 10-31 周报、统计与证据索引 |

## 5. 降级路径

- **seekdb**：`hybrid_search` 失败 → 纯向量 `query`（`engine=seekdb-vector`）→ 本地扫描（`engine=local-scan`）。
  响应中的 `engine` 始终为实际执行路径，日志同步记录。
- **embedding**：本地 BGE 模型不可用时回退到 512 维确定性哈希嵌入（`fallback_reason` 会写明原因），
  检索仍可用，语义质量下降。
- **PowerContext**：服务不可用时文献检索与周报仍可工作，记忆页显示降级提示。

## 6. 复现方式

Docker：

```bash
cd qoder/litmemory
cp .env.example .env         # 修改 SEEKDB_PASSWORD
docker compose up -d --build
python scripts/verify.py --base http://127.0.0.1:8765
```

原生部署（Linux）：

```bash
cd qoder/litmemory
python3.12 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env         # 填写 seekdb 与 PowerContext 地址
.venv/bin/powercontext server run &          # 默认 127.0.0.1:8000
uvicorn main:app --app-dir app --host 0.0.0.0 --port 8765
```

首次启动会自动写入 16 条示例文献/笔记与 6 条研究记忆；也可在界面点击「载入/刷新示例数据」。
