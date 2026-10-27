# Qoder 目录说明

本目录提交 Qoder × OceanBase 2026 参赛作品 **LitMemory · 有记忆的科研文献助手**。

## 提交材料索引

| 提交项 | 位置 |
| --- | --- |
| 项目官网（Qoder Sites） | https://litmemory-c8a8093w5oo.qoder.zone |
| 在线体验（完整应用） | https://rebates-summer-tale-solely.trycloudflare.com（临时隧道，失效时按下方 README 本地启动） |
| 代码仓库 / 分支 | https://github.com/asyhyxcqdx/powercontext/tree/2026-competition-ecosystem （作品位于 `qoder/`） |
| 运行说明 | [litmemory/README.md](litmemory/README.md)（Docker Compose 或 venv 原生部署） |
| 验证样例 | [litmemory/docs/verification.md](litmemory/docs/verification.md)（7 项检查、真实输出、复现命令） |
| Qoder 开发记录 | [litmemory/docs/qoder-devlog.md](litmemory/docs/qoder-devlog.md)（提示词、排错、截图索引、账号 UID） |
| 使用效果数据 | 16 条知识 / 512 维向量 / 混合检索 22.5 ms / 6 条有效记忆 / 周报 4,890 字，详见验证记录 |

- 项目源码与运行说明：[litmemory/](litmemory/README.md)
- 技术栈：seekdb（混合检索）+ PowerContext（跨会话研究记忆）+ FastAPI + 原生 SPA

快速启动：

```bash
cd litmemory
cp .env.example .env      # 填写 SEEKDB_PASSWORD
docker compose up -d --build
# 打开 http://localhost:8765
```
