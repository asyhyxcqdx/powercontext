# Qoder 开发记录 · LitMemory

> 本文记录 LitMemory 从选题到部署的完整过程，用于赛题「Qoder 开发记录」提交项。
> 截图与录屏放在 `docs/screenshots/`。

## 1. 基本信息

| 项目 | 内容 |
| --- | --- |
| 作品名 | LitMemory · 有记忆的科研文献助手 |
| 开发者 | nick5715534520（Qoder 账号） |
| Qoder 账号 UID | `01a17e3a-4ffd-730f-9e0f-674f529ac857` |
| 开发时间 | 2026-10-27 ~ 2026-10-28 |
| 代码位置 | `qoder/litmemory/`（基于 `2026-competition-ecosystem` 分支） |
| 项目官网 | https://litmemory-c8a8093w5oo.qoder.zone（Qoder Sites，公开访问） |
| 在线演示 | `https://rebates-summer-tale-solely.trycloudflare.com`（Cloudflare Quick Tunnel，临时域名，以提交时为准） |
| 验证记录 | `docs/verification.md` |

## 2. 选题过程

需求是「用 Qoder 做一个让学习、科研或工作更高效的项目」，并要求实际用上 seekdb / PowerContext。

在 Qoder 中对比了三个方向：

1. 文献管理 + AI 摘要：同质化严重，且核心价值依赖大模型，seekdb 容易被当成普通存储；
2. 知识图谱可视化：展示效果好，但与「效率提升」的因果链较弱；
3. **科研文献助手 + 跨会话研究记忆**：检索与记忆分别落在 seekdb 和 PowerContext 的能力边界上，且能形成「读文献 → 记录结论 → 下周直接复用」的闭环。

最终选择 3，并把产品边界收窄为：**不做通用聊天助手，只做检索、记忆、周报三件事**。

## 3. Qoder 承担的工作

| 阶段 | 在 Qoder 中的操作 | 产出 |
| --- | --- | --- |
| 仓库探索 | 让 Qoder 阅读 `2026-competition-ecosystem` 与 `archive/powercontext-main`，确认生态分支是脚手架、真实实现位于 archive 分支 | 技术选型与依赖安装方式 |
| 环境探查 | 通过终端检查服务器 Docker、seekdb 版本、端口、磁盘 | 复用已有 seekdb，独立库 `litmemory` |
| 数据层 | 生成 `store.py`：Schema、HNSW、IK 全文索引、混合检索与三级降级 | seekdb 读写闭环 |
| 记忆层 | 生成 `memory.py`：封装 PowerContext 的 remember/search/prepare/list | 跨会话记忆闭环 |
| 业务层 | 生成 `report.py`、`seed.py`、`main.py` | 周报与 API |
| 前端 | 生成原生 SPA：五个页面、检索证据面板、记忆召回面板 | 可演示界面 |
| 联调 | 用 Qoder 终端完成依赖安装、服务启动、`verify.py` 全链路验证 | 实测输出 |

## 4. 关键提示词（摘录）

- 「基于 powercontext 仓库，设计一个科研文献助手：seekdb 负责文献混合检索，PowerContext 负责跨会话研究记忆，不要用大模型也能跑通。」
- 「检索必须真实走 seekdb 的 hybrid_search（向量 + 全文 + RRF），失败时按 vector → local scan 降级，并在响应里返回实际 engine。」
- 「周报要确定性生成，每条结论能回指 seekdb 条目或 PowerContext entry_id。」
- 「前端不要构建步骤，原生 HTML/CSS/JS，学术纸张风格，检索结果要有分数、距离、耗时和引擎。」

## 5. 开发与排错记录

1. **Docker 不可用**：本机 Docker daemon 未启动，改为在 Linux 服务器上用 venv 原生部署。
2. **pyseekdb 嵌入模式**：Windows 下提示 `pylibseekdb not available, Linux only`，因此服务端部署到 Linux，并复用已有 seekdb 实例。
3. **PowerContext 安装**：上游无 `main` 分支的旧安装命令失败，改为 `@archive/powercontext-main`。
4. **服务器磁盘 99%**：经确认后清理 `/root/.cache/bazel`，释放约 33G。
5. **端口与安全组**：云安全组仅放行 SSH，8765 无法公网直达；改用 Cloudflare Quick Tunnel 暴露演示地址，同时保留 SSH 端口转发用于调试。
6. **嵌入模型下载**：HuggingFace 直连失败（DNS 污染 / Xet 401），改用 `HF_ENDPOINT=https://hf-mirror.com` 与 `HF_HUB_DISABLE_XET=1` 下载 `BAAI/bge-small-zh-v1.5`。
7. **混合分数方向**：pyseekdb 的 hybrid `distances` 实际是 RRF 相关度（越大越相关），初版按距离换算导致排序颠倒，已修正并保留原始 distance 供复核。
8. **验证数据清理**：`scripts/verify.py` 写入的验证记忆在截图前已 retire，并清理审计日志中的测试行，保证演示数据干净。

## 6. 与赛题技术要求的对应

| 要求 | 实现 |
| --- | --- |
| 使用 seekdb | `litmemory_notes` 集合，HNSW cosine + IK 全文 + 标量过滤；检索日志记录 engine/耗时/命中 |
| 使用 PowerContext | 五类记忆写入/检索/准备上下文；周报引用 entry_id |
| 两者协同 | 周报同时聚合 seekdb 条目与 PowerContext 记忆；检索页与记忆页共享同一研究叙事 |
| Qoder Sites | 公开项目官网 https://litmemory-c8a8093w5oo.qoder.zone（介绍、架构、演示、仓库、体验入口） |
| 可复现 | Docker Compose + `scripts/verify.py` |

## 7. 截图索引

文件位于 `docs/screenshots/`，均从公网演示地址实际访问后截取（2026-10-28 01:45，1440px 宽）：

| 截图 | 内容 |
| --- | --- |
| `01-dashboard.png` | 工作台、服务状态、最近检索与记忆操作、研究闭环 |
| `02-library.png` | 文献库 16 条，类型与标签元信息 |
| `03-search.png` | seekdb 混合检索结果、证据栏、RRF 分数 |
| `04-memory.png` | 研究记忆 6 条、写入表单、召回上下文块 |
| `05-report.png` | 组会周报、统计与证据索引 |

终端验证输出见 `docs/verification.md`。
