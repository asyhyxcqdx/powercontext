# 运行与复现说明

## 1. 环境、组件、依赖

- Dify Cloud Chatflow（作品使用 2026-10-27 的 Cloud 界面构建；具体云端内部版本由平台维护，未独立确认）；也可使用可导入本项目 DSL 的兼容 Dify 版本。
- LLM：原作品为 GPT-5 Chat；评审须在 Dify 工作区配置可用的聊天模型及额度。若原模型不可用，可选兼容模型并重新验证输出格式。
- OceanBase seekdb：官方 D0 管理服务，通过 `https://d0.seekdb.ai/api/v1/query` 调用结构化 SQL；D0 底层精确数据库版本由云端维护，未独立确认。未安装向量模型、Embedding、Rerank，也不需要 Dify 插件。
- 初始化客户端：Windows PowerShell 5.1+；联网访问 `d0.seekdb.ai`。
- 运行网络：Dify Cloud 所在环境必须能够向 D0 HTTPS SQL API 发出 POST；评审自己的浏览器能访问 D0 并不代表 Dify 云端也可达。

## 2. 从干净环境初始化数据库

在一个**不用于 Git 提交**的私有工作副本中打开 PowerShell，进入同时包含 `cases.json` 和三个 `.ps1` 的目录。运行：

```powershell
cd 'C:\YOUR_PRIVATE_WORKDIR\cybercourt'
powershell -NoProfile -ExecutionPolicy Bypass -File .\create_d0.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File .\seed_d0_http.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File .\verify_d0_http.ps1
```

`create_d0.ps1` 每次只创建一个新 D0 试用实例，会生成 **仅留在本地的 `.env`**。若 `.env` 已存在，脚本会拒绝覆盖；不要误删已用实例凭据。`seed_d0_http.ps1` 会创建表并导入 36 条虚构判例。核查 `verify_d0_http.ps1` 输出 `total_cases = 36`，以及包含 JF-xxx 的记录。此步骤有真实读写数据库，不是假数据演示。

**不要将 `.env`、SQL API 认证请求日志或数据库密码上传到 GitHub。**

## 3. 导入正式 DSL 并连接服务

1. 在 Dify Studio 选择导入/创建自 DSL，导入同目录 `cybercourt.yml`（此文件由参赛者从实际线上应用导出后加入）。
2. 检查节点顺序应为：`USER INPUT → CODE → HTTP Request → LLM → ANSWER`。移除任何遗留的临时测试节点。
3. 在应用 ENV 中配置 `D0_INSTANCE_ID`（普通字符串）和 `D0_PASSWORD`（Secret）。提交版 DSL 为安全起见将两项值都清空。将 `.env` 的 `D0_INSTANCE_ID` 填给前者，将 `.env` 的 `SEEKDB_PASSWORD` 填给后者。注意本地名称与 Dify 名称不完全相同。
4. HTTP Request 节点设置：`POST https://d0.seekdb.ai/api/v1/query`，Header `Content-Type: application/json`；Body 使用**Dify 变量选择器**构造：

```json
{
  "instance_id": "<ENV.D0_INSTANCE_ID 变量标签>",
  "password": "<ENV.D0_PASSWORD 变量标签>",
  "sql": "<CODE.sql_select 变量标签>"
}
```

以上尖括号仅为文档占位，不可原样粘贴到 Dify。不要在请求中多输入 `}`；D0 解析会失败。

5. 在 LLM SYSTEM 提示词确认引用 `HTTP Request → body`，并要求模型仅引用真实返回的 JF-xxx 记录；答案由 `ANSWER` 输出 `LLM.text`。
6. 确认 LLM 的当前会话 Memory 已开启，以支持“我要上诉”。本项目不声称跨会话持久记忆；DSL 中 Memory 的窗口限制开关关闭不代表会话记忆关闭。
7. 配置可用模型和模型服务凭据，执行 Preview 测试；成功后 Publish 获取公开 Web App 链接。

## 4. 验收与故障排查

请执行 [VALIDATION.md](VALIDATION.md) 中的初审/上诉样例。必须检验 HTTP Request 的**实际响应 `body`**包含 `columns/rows`，并至少有与类别匹配的 JF 判例；不可把节点的绿色 SUCCESS 单独当成数据库成功。

- `total_cases` 不等于 36：检查 `seed_d0_http.ps1`；数据库若过期，先创建新 D0 并重做初始化。
- Dify 请求 503：先确认 `SELECT 1 AS ok` 在 HTTP 节点的真实 POST/JSON 中执行成功，并检查括号、空格、变量标签；继续区分网络层与 API 错误。
- LLM 不显示引用编号：检查 SYSTEM 中已插入 HTTP Request 的 `body` 标签，而非字面量占位符。
- 上诉忘记前案：检查 LLM 的 Memory 设置以及是否在**同一会话**中连续输入。
- 云端公开体验不可用：检查 D0 免费实例的到期时间、Dify 工作区模型额度和公开发布状态；评委可使用上述步骤创建新实例并导入 DSL 复现。

## 5. 已知限制

判例均为原创虚构娱乐材料；判决及法条不是真实法律建议。分类规则为固定关键词匹配，不承诺语义向量检索。当前正式工作流只读查询判例，不承诺向 `cyber_case_plays` 写入游戏日志；导出 DSL 的实际连线与已发布版本应保持一致。D0 实例有短期有效期且云服务版本可能变化。

## 6. 导出 DSL 核验与清理说明

- 实际导出应用名：赛博离谱法庭；DSL schema `version: 0.7.0`（**不是** Dify Cloud 服务端版本号）。
- 工作流：5 个节点、4 条边；仅有一个正式 HTTP Request 节点，无独立排障节点。
- Marketplace 依赖：`langgenius/openai`，导出标识版本 `1.0.8`。具体能否使用 GPT-5 取决于评委 Dify 工作区模型提供商配置。
- 为防泄露，本提交版 DSL 将 `D0_INSTANCE_ID` 的实际值清空；`D0_PASSWORD` 原始导出已为空，未导出明文密码。
- 移除了只供 Cloudflare 排障时使用、且没有任何实际节点引用的 `COURT_TOKEN` ENV；**没有修改 5 个节点或其连接/SQL/提示词**。
- 仅连接了 SQL `SELECT`。虽然 Code 节点同时生成 `sql_log`，但没有任何节点执行它；不应声称写入了审理日志。
- 项目未使用插件、自定义后端或 Cloudflare Worker；本目录中也无需安装上述内容。
- 建议从导入的全新 Dify 工作区执行样例 A、B，并保存 HTTP Request 的 `OUTPUT`，确认返还 JF-xxx（单纯 `SUCCESS` 不够）。
