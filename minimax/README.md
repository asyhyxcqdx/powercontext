# MiniMax × OceanBase: Spec-Driven Development Context (20-point acceptance)

> 本目录为可运行的比赛参赛项目源码，须放在**比赛要求的 `2026-competition-ecosystem` 分支**的 `minimax/` 下。它不会覆盖同仓库的 `src/`、`dify/` 等其它项目。**初始交付是待运行的基线，不是声称已经通过全部 6 项验收的证据。**

## 1. 题目与验收样例

- 任务 ID：`inventory-min-stock-2026`；任务说明 `task.json`。
- 业务工程：`workshop/inventory.py`，`filter_products(products, category=None, min_stock=None)`。
- 新功能：`min_stock` 为包含边界（`stock >= min_stock`），`0` 是有效筛选条件；`None` 不筛选。
- 不可改变：`category` 大小写不敏感、两个筛选条件取交集、原顺序、新列表、不修改输入对象、函数签名。
- 规则 `specs/inventory_filter.md`：`SDD-STOCK-001` 和 `SDD-COMPAT-002`。
- 目标功能测试：`tests/test_feature_min_stock.py`（修改前必须因断言不成立而失败）。
- 原有行为回归：`tests/test_regression.py`（修改前后都须通过）。
- 业务代码初始故意有局部功能缺口：函数接收了 `min_stock`，却还没有实际应用。**不要先手工改成正确实现**，应由真实 MiniMax API 输出目标文件。

| 必要来源 | 路径 | 选择方式 |
| --- | --- | --- |
| 适用规格 | `specs/inventory_filter.md` | seekdb SQL 召回、含 hash |
| 目标代码 | `workshop/inventory.py` | seekdb SQL 召回、含函数名称及 hash |
| 功能测试 | `tests/test_feature_min_stock.py` | seekdb SQL 召回、含 hash |
| 兼容测试 | `tests/test_regression.py` | seekdb SQL 召回、含 hash |
| 已办/待办/验证 | PowerContext Memory / PreparedContext | 独立服务器写入、重启后读取 |

## 2. 技术使用及约束

- Python `>=3.11`；推荐 Ubuntu 22.04 x86_64 服务器。Windows 原生不支持本文选定的嵌入式 `pylibseekdb` 模式。
- `pylibseekdb==1.4.0.post1` + `PyMySQL==1.1.1`：嵌入式真实 seekdb 数据库，默认目录 `minimax/runtime/seekdb.db`；可用 `OB_*` 变量切换外部 seekdb/OceanBase SQL 实例。
- `powercontext[cli,server]==1.4.1`：官方独立 Server，使用 HTTP API `/v1/scopes`、`/v1/memory/remember`、`/v1/atomic-memory/list`、`/v1/atomic-memory/search`、`/v1/context/prepare`；使用持久化的 `POWERCONTEXT_HOME` 而不是把 JSON 文件伪装成 PowerContext。
- MiniMax：`https://api.minimax.io/v1/text/chatcompletion_v2`；`MiniMax-M2.5` 为示例模型，使用真实的 `MINIMAX_API_KEY` 及 HTTP 请求生成新的目标 Python 文件。
- 不把 API Key、数据库密码、PowerContext token、模型私有思维链写入 Git。API 调用日志保留消息上下文、实际内容、模型信息、用量及关联 diff。
- `test_sddflow_unit.py` 测试运行逻辑；不能代替实际数据库、MiniMax 与 PowerContext 的在线证据。

官方文档：[MiniMax 文本模型](https://www.minimax.io/models/text) · [seekdb](https://github.com/oceanbase/seekdb) · [PowerContext API](https://powercontext.oceanbase.io/en/docs/develop/api-quickstart/)。第三方开源软件版权归原项目，此目录只包含为赛题编写的最小业务样例和集成代码。

## 3. 在 Ubuntu 22.04 Linux 服务器准备

工作目录应在服务器 Linux 原生目录（如 `/root/projects/powercontext`），不要把嵌入式数据库放到 Windows 挂载路径。Ubuntu 22.04 自带 Python 常为 3.10，安装脚本通过 uv 独立安装 Python 3.12，不修改系统 Python。服务器专用逐步说明见 `SERVER_DEPLOYMENT.md`。进入**包含仓库 `.git` 的根目录**：

```bash
cd /root/projects/powercontext
printf 'branch=%s\n' "$(git branch --show-current)"
git branch --list '2026-competition-ecosystem'
```

本题指定分支为 `2026-competition-ecosystem`。必须核实该分支已从大赛提供的基线导入，不能将名字相似的 `2026-competition` 当作同一分支。如本机没有目标分支，先按比赛官方导入说明获取，不能基于其它分支自行冒充。将本 ZIP 内的 `minimax/` 原样复制到该分支的仓库根目录。

```bash
cd /root/projects/powercontext/minimax
bash scripts/verify_server_branch.sh
bash scripts/install_server.sh
cp .env.example .env
# 用编辑器在 .env 中填写自己的 MiniMax Key，不要把 .env 加入 Git
```

推荐两种配置方法。方式 A（最方便）是在 `.env` 中将 `MINIMAX_API_KEY=REPLACE...` 改成 `MINIMAX_API_KEY='your-key-here'`，其余保持默认。方式 B 是不使用 `.env`，在当前 Shell 里 `export MINIMAX_API_KEY='...'`。

本包会将 PowerContext 安装在 `minimax/.powercontext-venv/bin`；一键脚本自动使用该目录的可执行文件。`uv` 没安装时，参考 https://docs.astral.sh/uv/ 安装并重新执行 `scripts/install_server.sh`。本包通过 uv 创建 Python 3.12 虚拟环境，避免 Ubuntu 22.04 的 Python 3.10 限制。

## 4. 一次性跑完整真实验收流程

```bash
cd /root/projects/powercontext/minimax
bash scripts/full_demo_server.sh
bash scripts/check_ready_to_commit.sh
```

脚本确实调用真实 seekdb、MiniMax API、PowerContext Server，按以下顺序执行：

1. 恢复初始版本；启动独立 PowerContext Server；创建项目 Scope。
2. 将规格、代码、两组测试导入 seekdb，真实 `SELECT`，返回来源和 hash；确认新 Scope 里无历史进度。
3. 使用一组**未修改**的目标测试运行前测（期望目标行为断言失败、回归通过）。
4. 写入 PowerContext `baseline_failed`，重新检索 SQL 和进度，组合当前任务上下文。
5. 发送上下文给 MiniMax，使 MiniMax 生成 `workshop/inventory.py` 的完整更新版本。验证签名没变，执行同一组测试。失败则恢复初始文件且不生成成功证据。
6. 记录 MiniMax 的响应与 diff、修改前后快照及测试退出码；成功后把变更后的代码重新导入 seekdb。
7. PowerContext 保存 `validated` 状态、**真实退出并重启 Server 进程**，再次通过 HTTP 读取并确认阶段标记。
8. 暂改规格添加 v2 标记，重新导入 seekdb，再构造上下文验证查询返回新内容；最后恢复原规格、重建索引。
9. 利用原始 before 和 MiniMax 生成的 after 快照离线重跑一组未修改的测试，并打印提交材料审计状态。

最末一步期望为：`ALL SIX EVIDENCE CATEGORIES PRODUCED`，以及 `evidence/15_submission_audit.json` 的 `status=READY_FOR_REVIEW`。此状态表示证据文件齐全且满足脚本的审计断言，**不是评测平台自动判分**。

**如果曾经运行过本示例，需要演示从空状态开始**，先确保没有任何 PowerContext / seekdb 进程仍在使用目录，再执行（仅在 `minimax/` 下，不影响其他项目）：

```bash
cd /root/projects/powercontext/minimax
rm -rf runtime/powercontext-home runtime/seekdb.db runtime/powercontext_scope.json
python -m sddflow.cli reset-code
```

如果已经生成过真实 MiniMax 证据，清理 runtime **不会删除** `evidence/` 和 `snapshots/after/`，要保留其供提交。需要重新做全新取证时，先自行备份历史运行记录，避免覆盖。

## 5. 可单步验证与调用接口

本模块入口：`python -m sddflow.cli <command>`，工作目录 `minimax/`，需激活 `.venv`，PowerContext Server 会由一键脚本启动；CLI 每次是新的 Python 进程。

```bash
python -m sddflow.cli doctor
python -m sddflow.cli init-scope
python -m sddflow.cli ingest
python -m sddflow.cli state-read
python -m sddflow.cli baseline-test
python -m sddflow.cli state-write --stage baseline_failed --next implement_min_stock_with_MiniMax
python -m sddflow.cli context
python -m sddflow.cli model-apply
python -m sddflow.cli ingest
python -m sddflow.cli after-test
python -m sddflow.cli state-write --stage validated --next review_and_submit
python -m sddflow.cli state-read --require-stage validated
python -m sddflow.cli verify-spec-refresh
python -m sddflow.cli reproduce-offline
python -m sddflow.cli audit
```

| 命令 | 输入 | 输出 / 副作用 |
| --- | --- | --- |
| `ingest` | `task.json` 列出的真实文件 | seekdb 表 `sdd_documents`，返回真实 SQL 插入/核对记录 |
| `context` | `task.json` 查询/关键词 + PowerContext scope | JSON `task`、`source_provenance`、`sql_retrieval`、`powercontext_state` |
| `state-write` | `stage`、`next`、当前代码 hash | 调用 PowerContext 记忆写入 API，保留返回 Artifact 证据 |
| `state-read` | 当前 scope ID | 服务端 Memory list/search 返回历史状态，打印最近项 |
| `model-apply` | 当前检索上下文与真实 MiniMax Key | 更新 `workshop/inventory.py`、生成前后快照/diff/测试和调用记录 |
| `verify-spec-refresh` | 当前规格原始文件 | 临时修改、重新导入、真实查询并还原，输出证据 |
| `reproduce-offline` | 已由 MiniMax 生成的 after 快照 | 临时切换 before/after，保持测试不变，运行并复原工作文件 |

成功的 `context` 必须包含上表四个真实来源，其 `sha256` 与磁盘文件对应。若源文件在导入之后变化，模块明确拒绝过期索引，要求重新 `ingest`。

### 修改规格并重新导入（也可手动演示）

编辑 `specs/inventory_filter.md`，追加 `Version: 2.0 / new constraint for min_stock` 一类新条款，然后执行：

```bash
python -m sddflow.cli ingest
python -m sddflow.cli context
```

在输出的 `source_provenance` 中检查 `specs/inventory_filter.md` 的新条款与 hash 已更新。`verify-spec-refresh` 是自动化、可恢复的同等验证。

### 模块重启与实际状态复用

完整脚本会实际停止再重启 PowerContext Server，随后创建新 CLI 进程从服务端恢复 Memory。手动验证时，结束运行中的 `powercontext server run`，保持同一个 `POWERCONTEXT_HOME`，重新启动后执行 `state-read --require-stage validated`。不能用本地 `evidence/state_last_write.json` 当作读取结果；这个文件只是在线 API 响应的审计副本。

## 6. 供裁判复核的提交文件

完整真实运行后建议提交这些文件，**不要提交 `.env` 或 `runtime/`**：

- 源码：`sddflow/`、`workshop/`、`requirements.txt`、`scripts/`、`task.json`。
- 规格与样例：`specs/`、`tests/`、`snapshots/before/`、MiniMax 生成的 `snapshots/after/`。
- 模型开发记录：`evidence/runs/*_minimax_live/model_context.json`、`minimax_development_record.json`、`before.py`、`after.py`、`code.diff`、`summary.json`。
- 数据库查询及更新：`evidence/02_ingest.json`、`database_last_query.json`、`13_spec_refresh.json`。
- PowerContext 状态：`evidence/05_state_write.json`、`10_state_write_validated.json`、`11_state_after_server_restart.json`、`12_context_after_server_restart.json`。
- 代码测试：`evidence/04_before_test.json`、`09_after_test.json`、`14_offline_replay.json`，以及每次执行 `evidence/runs/*/feature.json` / `regression.json`（命令/退出码/代码 hash/测试 hash）。
- 一页技术说明：`TECHNICAL_ONE_PAGE.md`。

运行后：

```bash
cd /root/projects/powercontext
# 再次确认同名目标分支及改动范围
git branch --show-current
git status --short
git add minimax
git diff --cached --stat
git diff --cached --check
git commit -m 'feat(minimax): complete SDD context demo with real MiniMax, seekdb and PowerContext evidence'
git rev-parse HEAD
git push origin 2026-competition-ecosystem
```

向评测平台填写**该提交的完整 40 位 commit SHA** 和**确实包含此 SHA 的分支**。不要提前提交只有空日志的初始基线版本参与 MiniMax 题测评。

## 7. 本目录初始交付的已知限制

- 当前生成压缩包的环境不包含用户的 MiniMax Key、seekdb wheel 或运行中的 PowerContext Server，因此初始包**尚未包含实际在线调用成功的记录**，不能声称 20 分已通过；初始基线的离线断言失败与回归测试是已实测的。
- 正式验收推荐 Ubuntu 22.04 x86_64 服务器；纯 Windows 不适配嵌入式 seekdb，本交付以 Linux 服务器为准。
- 使用固定官方 API 路径；如 MiniMax 订阅对应模型 ID 不同，可在 `.env` 覆写 `MINIMAX_MODEL`，仍须真实完成改码。
- 在线调用失败、无 Key、数据库断线、PowerContext 状态未写成功时会返回非零错误码；不使用静态 JSON 模拟通过。
