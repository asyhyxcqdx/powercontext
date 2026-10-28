# 比赛提交前检查

**本目录已包含真实导出且已脱敏的 `cybercourt.yml`**。正式提交前仍应在评委可用的独立 Dify 工作区重新导入、配置 ENV 与模型，并复现样例。

1. 确认本目录 `cybercourt.yml` 已脱敏，并保留 `INPUT → CODE → HTTP → LLM → ANSWER` 5 节点主链。
2. 在新 Dify 工作区导入该 YAML，重新配置两项环境变量与模型，按 `RUNBOOK.md` 复验。
3. 复现 README / RUNBOOK / VALIDATION 的步骤。不要声称已实现 INSERT 日志，除非确实新增并验证节点。
4. 用 GitHub 网页或 Git 在团队私有仓库的官方 `2026-competition-ecosystem` 分支中，放入官方指定的 dify 目录。此预备包展示 `dify/cybercourt/`，若该分支中的指定目录位置不同，以官方已有目录为准。
5. 只上传源文件、数据、说明、脱敏证据；绝对不要上传 `.env`、数据库密码、模型 API Key 或 Token。
6. Commit 完成后复制**完整 40 位 SHA**，在比赛平台填写该 SHA 和 `2026-competition-ecosystem`。确认 GitHub 网页切到相同分支时能看到新增文件、DSL，且 README 的体验地址可访问。
