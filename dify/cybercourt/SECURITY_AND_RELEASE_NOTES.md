# 提交版安全与发布核对

- DSL 从实际 Dify Cloud 导出；已清空 D0 实例 ID、密码及不再使用的 Worker Token。
- 代码和文件不含 `.env`。旧版原始截图曾显示过数据库密码或 Token 的一部分；建议更新凭据后再公开更多截图，切勿上传未脱敏的 PROCESS DATA。
- 本地的 36 条案例可用初始化脚本复现；当前流程只有 SELECT，`cyber_case_plays` 表仅作预留。
- 原始模型是 GPT-5，通过 Dify 的 `langgenius/openai` 提供商；评委须有相应额度或使用兼容聊天模型测试。
- Dify DSL schema 标注 `0.7.0`，与实际云端服务端版本不是同一个概念。
- D0 短期实例可能到期，不能仅依赖作者的在线实例。
- 此处检查了 **静态文件和脱敏**，没有登录评委环境或执行新实例网络验证，也没有上传 GitHub。
- 需确认官方仓库 `2026-competition-ecosystem` 中已有的 `dify` 具体相对路径，再合入 `cybercourt` 目录。
