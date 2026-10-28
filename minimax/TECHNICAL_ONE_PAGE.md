# 一页技术说明：规有所依 / MiniMax SDD Context

**问题**：AI 开发助手在局部功能迭代时可能遗漏当前规格、相关测试和跨会话进度，导致改坏原有行为。**目标**：在真实业务变更前以工程资料构造可追溯上下文，驱动 MiniMax 改代码，并用不变的测试验证前后差异。

## 技术架构

```text
Task JSON: 自然语言任务 + 检索关键词 + 必要来源声明
    |
    v
Source indexer ---> seekdb / OceanBase SQL (持久化 specs/code/tests + SHA256)
    |                 |
    |           SQL SELECT 的真实检索行、路径与版本
    v                 v
ContextBuilder <--- PowerContext HTTP (/atomic-memory/list, /context/prepare)
    |                    ^
    |             (/memory/remember)
    v                    |
MiniMax API ---> 受限单文件代码替换 ---> 同一组目标/回归测试
    |                                     |
    +--- 模型请求/响应 + before/after + diff + exit code + sha ---+
                      |
            PowerContext 保存完成状态
                      |
                重启 Server/CLI
                      |
               读取历史并复用
```

## 模块与责任划分

| 部分 | 责任 | 可检验证据 |
| --- | --- | --- |
| `sddflow/db.py` | SQL 建表、工程资料入库、按任务词实时检索、校验 SHA，支持重新导入 | SQL、参数、查询行及哈希 |
| `sddflow/runner.py` | 将真实 SQL 行、规格/代码/测试及历史进度组成任务上下文；把 MiniMax 代码应用到单文件并运行不可更改的测试 | `context_latest.json`、run 目录、前后快照和 diff |
| `sddflow/minimax_client.py` | 使用 MiniMax 的真实 HTTP API 生成/修改 Python 业务代码 | 完整输入上下文、模型名称、返回代码、响应 ID、用量 |
| `sddflow/powercontext_client.py` | 将进度/结果写入官方 PowerContext Memory，读取/准备上下文，在新的服务进程重新读取 | 两次状态写入、服务重启后的列表与上下文 |
| `sddflow/cli.py` | 可复现 CLI 入口，提供数据初始化、查询、改码、重启验证和规格变更验证 | 命令、日志、退出状态 |

## 选择策略与规格变化

使用任务元数据关键词构造**参数化 SQL 查询**，`task_id` 隔离不同任务，对返回行做路径存在性和内容 SHA256 校验。必须返回 `specs/inventory_filter.md`、`workshop/inventory.py`、两份测试代码；缺一项拒绝构造开发上下文。文档重新导入会更新真实 SQL 内容；`verify-spec-refresh` 临时添加一项规格变更并再次检索证明不是硬编码。

## 具体开发任务与前后验证

任务：`filter_products` 增加 `stock >= min_stock` 包含边界的筛选；保持大小写不敏感分类筛选、输入顺序、原函数签名、不修改输入。修改前目标测试有预期的**业务断言失败**，不是依赖问题；兼容测试在两版均应通过。MiniMax 必须真正返回新代码，运行两套测试成功后才保留提交用 after 快照和模型开发证据。所有日志记录源代码 SHA 和测试文件 SHA，代码被修改时可定位对应版本。

## 版本、入口、可信性

Python 3.11+、seekdb `pylibseekdb==1.4.0.post1`、PyMySQL `1.1.1`、PowerContext `1.4.1` HTTP（项目隔离安装）、MiniMax 模型 `MiniMax-M2.5`（可覆盖）。入口：`python -m sddflow.cli context`，一键验证：`bash scripts/full_demo_server.sh`。真实密钥仅置于环境变量，不入库；原始代码和测试保持可追溯。**本地离线单测不能替代 MiniMax、seekdb 和 PowerContext 在线证据。**
