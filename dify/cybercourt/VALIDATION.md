# 验证样例与运行证据

## 初始状态

- 用 `create_d0.ps1` 申请新的 D0 实例（7 天临时服务），在私有 `.env` 中保存凭据。
- 用 `seed_d0_http.ps1` 导入 `cases.json` 中的 36 条判例。
- 用 `verify_d0_http.ps1` 确认 `total_cases = 36`。新实例的 `total_hearings = 0` 属正常，因为当前 Dify 流程未开启 INSERT 日志节点。
- 在新的 Dify 工作区导入已脱敏的 `cybercourt.yml`，设置 ENV，绑定聊天模型，打开 Preview 新会话。

## 样例 A：宠物监考初审

**输入：**

> 我今天不想写作业，因为我的猫一直盯着我，感觉它在监视我。

**应核验的事实，而非要求逐字一致的文本：**

1. Code 节点根据宠物/学习类关键词生成固定白名单分类与安全 SQL。
2. HTTP Request 对 D0 发出真实 POST，返回 `columns`、`rows`，包含可核对的 `case_id`。
3. LLM 判决具有案件名、事实认定、离谱指数、趣味裁决、专属称号，并标出一个在查询结果中实际存在的 JF-xxx 判例。现有演示命中 `JF-019`「猫咪监督学习过度案」；若排序或分类有变化，以本次真实响应为准。

## 样例 B：同会话上诉

**紧接样例 A 输入（不可新开会话）：**

> 我要上诉，我的猫真的会按键盘！

**预期：**识别为原案二审，讨论新增的键盘证据，给出维持或改判，说明关联判例并允许继续上诉。文本非确定性，不要求每次措辞相同。

## 样例 C：核对数据库真实作用

1. 在 Dify 的 HTTP Request 节点 LAST RUN 中检查查询结果而非仅看 SUCCESS 标签。
2. 运行 `verify_d0_http.ps1` 检查 `total_cases = 36`。
3. 将 LLM 给出的 JF 案号与 HTTP 返回中的真实 `case_id` 对比，防止模型编造数据库案例。

## 已有演示截图

- `evidence/01_first_hearing.png`：初审、真实引用 JF-019。
- `evidence/02_appeal.png`：上诉二审。
- `evidence/03_case_reference.png`：上诉引用真实判例。

- `evidence/04_seekdb_query_rows_redacted.png`：真实 Dify HTTP Request 输出正文，可核对 JF-019、JF-020、JF-021，共 3 条。截图已排除 HTTP Headers、Set-Cookie 和认证信息。

**如需进一步验证**：保存本次重新导入后的 `verify_d0_http.ps1` 输出，注意不要曝光 PROCESS DATA、密码、实例 ID、Header 令牌等。必要时录制 1 分钟从初审到上诉的演示。保存新导入应用的测试证据，不要只依赖旧截图。

## 重置

新开 Dify 会话可以清空本次对话上下文；判例数据库不会被读取操作修改。若需要完全独立的初始数据库，请在新工作目录运行 `create_d0.ps1` 和 `seed_d0_http.ps1`，绑定新的 D0 实例环境变量。
