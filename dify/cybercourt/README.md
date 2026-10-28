# 赛博离谱法庭 | Cyber Court — Just for Fun

**赛事**：2026 OceanBase 数据库大赛 · Dify × OceanBase · Just for Fun

**在线体验**：https://udify.app/chat/X1hEBKJ87abPXRzX

## 创意与玩法

一款可上诉的 AI 搞笑法庭。用户输入一段生活中的离谱借口或小纠纷，Dify Chatflow 自动分类，查询 OceanBase seekdb D0 中的原创虚构判例，GPT-5 按照证据生成案件名称、离谱指数、趣味判决和专属称号。用户可以继续输入“我要上诉”并补充证据，AI 根据本会话上下文进行二审。

建议先输入：“我今天不想写作业，因为我的猫一直盯着我，感觉它在监视我。”
随后输入：“我要上诉，我的猫真的会按键盘！”

## 技术分工（以实际已完成流程为准）

Dify Chatflow：`USER INPUT → CODE (Python 3) → HTTP Request → LLM (GPT-5 Chat) → ANSWER`。

- **Dify**：输入、分类、工具编排、LLM、会话内连续上诉与回答。
- **OceanBase seekdb D0**：`cyber_case_catalog` 表存储 36 条原创虚构判例；由 Dify HTTP Request 节点调用 D0 HTTPS SQL API 实际 `SELECT`，结果注入 LLM Prompt 并用于判决。
- **未使用 PowerContext**；未声称跨会话长期记忆。
- **未使用自定义插件、Cloudflare Worker 或自建后端**：最终运行路线为 Dify 直连 D0；早期排障用的独立测试节点/Worker 不属于交付依赖。
- Code 节点也生成 `sql_log`，但当前对话流未连接 INSERT 节点，因此**不能把审理日志写入列为已完成功能**。

## 文件说明

- `cybercourt.yml`：已经包含来自实际 Dify Chatflow 的 DSL，提交前已脱敏实例 ID 和未使用的 Worker Token；评委须自行配置数据库凭据。
- `cases.json`：36 条原创虚构判例，非真实法律判例。
- `create_d0.ps1`：创建一个新的临时 D0 实例，并将私有凭据写入本地 `.env`。
- `seed_d0_http.ps1`：创建 `cyber_case_catalog`、`cyber_case_plays`，导入 36 条判例（重复运行时按主键更新）。
- `verify_d0_http.ps1`：只读 SQL 验证 `total_cases` 与判例记录。
- `dify_code_direct.py`：与当前 Dify Code 节点同类的分类/SQL 参考源码，实际运行以导出 DSL 为准。
- `RUNBOOK.md`：完整导入、参数绑定与重现步骤。
- `VALIDATION.md`：初审、上诉和真实 seekdb 查询的验收样例。
- `evidence/`：已附交互截图；已补充脱敏裁剪的 HTTP Request OUTPUT 截图（04_seekdb_query_rows_redacted.png，显示 JF-019/JF-020/JF-021）；仍建议在新应用中复验。

## 关键安全与期限限制

不要提交 `.env`、真实 API Key、数据库密码、完整带认证字段的 HTTP PROCESS DATA。DSL 与截图均须脱敏检查。D0 免费实例最长约 7 天，会到期；正式验收应使用 `create_d0.ps1` 初始化**新的有效实例**，并把新值填入评审自己的 Dify 环境变量。当前公开链接能否在评测日持续可用还取决于实例有效期和 Dify 工作区模型额度。

**完整步骤见 [RUNBOOK.md](RUNBOOK.md)，测试步骤见 [VALIDATION.md](VALIDATION.md)。**

## 最终提交版说明

已集成用户导出的真实 Dify DSL：`cybercourt.yml`，保留节点/连线/Prompt/SQL 逻辑；清空原有实例 ID，并删除未被节点引用的 `COURT_TOKEN`。请勿再将含有个人凭据的原始导出覆盖该文件。具体的 DSL 依赖、导入/配置方法见 `RUNBOOK.md`。
