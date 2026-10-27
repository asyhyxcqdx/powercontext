# LitMemory · 有记忆的科研文献助手

LitMemory 面向科研过程中的真实痛点：论文读完就忘、笔记散落在各处、每次开新会话都要重新交代研究背景、组会前从零整理周报。

它把两件事拆开做扎实：

- **seekdb** 负责「知识」：论文、阅读笔记、实验记录统一入库，向量 + 全文 + 标量过滤混合检索，结果可追溯。
- **PowerContext** 负责「你」：研究偏好、已定结论、进行中事项、约束条件以记忆条目的形式持久化，跨会话可召回、可注入提示词。

> 赛题要求的技术栈不是装饰：检索页的每一次查询都实际走 seekdb 的 HNSW 向量索引 + IK 全文索引 + RRF 融合；研究记忆页的写入与召回都实际调用 PowerContext Server 的 Memory API。

- 项目官网：https://litmemory-c8a8093w5oo.qoder.zone
- 在线体验：https://rebates-summer-tale-solely.trycloudflare.com（临时隧道，失效时按本文档本地启动）
- 开发记录：[docs/qoder-devlog.md](docs/qoder-devlog.md) · 验证记录：[docs/verification.md](docs/verification.md)

---

## 一、功能

| 页面 | 能力 | 依赖 |
| --- | --- | --- |
| 工作台 | 服务健康、知识规模、最近检索与记忆审计、一键载入示例语料 | seekdb + PowerContext |
| 文献库 | 论文/笔记/记录 CRUD，类型与关键词过滤，写入即向量化 | seekdb |
| 语义检索 | 中文语义检索，类型/年份/标签过滤，展示引擎、耗时、分数、距离与命中片段 | seekdb |
| 研究记忆 | 五类记忆（偏好/结论/进行中/事实/约束）写入与列表，召回上下文并复制为提示词 | PowerContext |
| 组会周报 | 按周聚合资料 + 召回研究上下文，生成带证据索引的 Markdown 草稿，可复制/下载 | 两者 |

没有接入任何大模型也能完整运行：周报是**确定性拼装**，检索分数来自 seekdb，记忆来自 PowerContext，避免「编造式生成」。

## 二、架构

```text
┌──────────────────────────────┐
│  浏览器 SPA（原生 HTML/CSS/JS） │
│  工作台 / 文献库 / 检索 / 记忆  │
└──────────────┬───────────────┘
               │ HTTP JSON
┌──────────────▼───────────────┐
│        FastAPI (app/main.py)  │
│  /api/search /api/memories …  │
├───────────────┬──────────────┤
│               │              │
│  SeekdbStore  │  MemorySvc   │
│  embed + hybrid│  PowerContext│
└───────┬───────┴──────┬───────┘
        │              │
┌───────▼──────┐ ┌─────▼──────────┐
│   seekdb     │ │ PowerContext   │
│ :2881        │ │ Server :8000   │
│ 向量+全文+标量 │ │ SQLite 记忆库   │
└──────────────┘ └────────────────┘
        │
   data/logs/*.jsonl（检索/记忆审计）
```

要点：

1. **嵌入**：优先 `BAAI/bge-small-zh-v1.5`（fastembed / ONNX，512 维），模型不可用时自动降级为确定性哈希向量，检索链路不中断，并在界面标注降级原因。
2. **混合检索**：`hybrid_search(where_document=$contains, knn, rank=rrf)`；如果当前 seekdb 版本不支持该调用，则回退纯向量检索，再回退本地扫描，`engine` 字段会如实显示 `seekdb-hybrid / seekdb-vector / local-scan`。
3. **记忆**：调用 `remember_memory / search_memory / prepare_context / list_memory_entries`，scope 默认 `project:litmemory:demo`；PowerContext 不可用时记忆页降级提示，检索与周报仍可用。
4. **审计**：检索与记忆操作分别写入 `data/logs/retrieval_logs.jsonl`、`memory_logs.jsonl`，界面直接读取，方便复核「是否真的调用了」。

## 三、快速开始

### 方式 A：Docker Compose（推荐给评审）

```bash
cd qoder/litmemory
cp .env.example .env
# 修改 .env 中的 SEEKDB_PASSWORD
docker compose up -d --build
```

启动后：

- 应用：<http://localhost:8765>
- PowerContext：<http://localhost:8000>
- seekdb：`localhost:2881`

首次启动会自动建库建表、下载嵌入模型并写入示例语料（16 条科研资料 + 6 条研究记忆）。

> 首次构建需要拉取 `powercontext` 源码与 Python 依赖，耗时取决于网络。

### 方式 B：本地原生运行

前置：Python 3.12、一个可访问的 seekdb（默认 `127.0.0.1:2881`）、PowerContext Server。

```bash
cd qoder/litmemory
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env               # 填入 seekdb 密码
powercontext server run            # 终端 1，默认 127.0.0.1:8000
uvicorn main:app --app-dir app --host 0.0.0.0 --port 8765   # 终端 2
```

打开 <http://localhost:8765>，在「工作台」点「载入/刷新示例数据」。

### seekdb 准备

若使用已有 seekdb：

```sql
CREATE DATABASE IF NOT EXISTS litmemory DEFAULT CHARACTER SET utf8mb4;
```

应用启动时也会尝试通过 MySQL 协议自动创建该库（见 `app/store.py`），无权限时会给出明确错误。

## 四、配置

见 [.env.example](.env.example)。关键项：

| 变量 | 默认 | 说明 |
| --- | --- | --- |
| `SEEKDB_HOST/PORT` | `127.0.0.1:2881` | seekdb SQL 入口 |
| `SEEKDB_PASSWORD` | 空 | seekdb root 密码，仓库中不保存真实值 |
| `SEEKDB_DATABASE` | `litmemory` | 独立库，不触碰其他业务库 |
| `SEEKDB_COLLECTION` | `litmemory_notes` | 集合名 |
| `POWERCONTEXT_URL` | `http://127.0.0.1:8000` | PowerContext Server |
| `POWERCONTEXT_SCOPE` | `project:litmemory:demo` | 记忆作用域 |
| `LITMEMORY_EMBEDDING_MODEL` | `BAAI/bge-small-zh-v1.5` | 嵌入模型 |
| `LITMEMORY_AUTOSEED` | `1` | 空库时自动写入示例语料 |

## 五、API

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/api/health` | 三个组件的健康状态与嵌入信息 |
| GET | `/api/bootstrap` | 条目、类型字典、scope |
| GET/POST | `/api/notes` | 列表/新增 |
| GET/PUT/DELETE | `/api/notes/{id}` | 详情/更新/删除（同步向量） |
| POST | `/api/search` | 混合检索，返回引擎、耗时、命中、日志 |
| GET | `/api/retrieval-logs` | 检索审计 |
| GET/POST | `/api/memories` | 记忆列表/写入 |
| POST | `/api/memories/recall` | 命中 + 准备上下文 |
| GET | `/api/memory-logs` | 记忆审计 |
| POST | `/api/reports` | 生成周报 |
| POST | `/api/demo/seed` | 幂等写入示例语料 |
| GET | `/api/stats`、`/api/export` | 统计、完整证据导出 |

交互式文档：`/docs`。

## 六、验证

```bash
python scripts/verify.py --base http://127.0.0.1:8765
```

脚本会检查 seekdb/PowerContext 连通性、写入语料、执行检索、写入并召回一条记忆、生成周报；任一环节失败即退出非零。实测输出见 [docs/verification.md](docs/verification.md)。

## 七、目录

```text
qoder/litmemory/
├── app/
│   ├── main.py          # FastAPI 路由与生命周期
│   ├── config.py        # 环境变量
│   ├── embeddings.py    # fastembed + 哈希降级
│   ├── store.py         # seekdb 集合、混合检索、审计
│   ├── memory.py        # PowerContext 客户端封装
│   ├── report.py        # 确定性周报拼装
│   ├── seed.py          # 演示语料与研究记忆
│   ├── logs.py          # JSONL 审计
│   └── static/          # 单页前端
├── scripts/verify.py
├── docs/
├── Dockerfile
├── docker-compose.yml
└── requirements.txt
```

## 八、关于 Qoder

项目在 Qoder 中完成需求拆解、代码生成、联调与部署；开发过程记录见 [docs/qoder-devlog.md](docs/qoder-devlog.md)。

## 九、许可

代码遵循仓库根目录的 Apache-2.0 License；示例语料为论文公开摘要的改写，仅用于演示检索。
