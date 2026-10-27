# Qoder 目录说明

本目录提交 Qoder × OceanBase 2026 参赛作品 **LitMemory · 有记忆的科研文献助手**。

- 项目官网（Qoder Sites，公开访问）：https://litmemory-c8a8093w5oo.qoder.zone
- 在线体验（临时隧道，可直接打开完整应用）：https://rebates-summer-tale-solely.trycloudflare.com
- 项目源码与运行说明：[litmemory/](litmemory/README.md)
- 技术栈：seekdb（混合检索）+ PowerContext（跨会话研究记忆）+ FastAPI + 原生 SPA
- 开发记录：[litmemory/docs/qoder-devlog.md](litmemory/docs/qoder-devlog.md)
- 实测验证：[litmemory/docs/verification.md](litmemory/docs/verification.md)

快速启动：

```bash
cd litmemory
cp .env.example .env      # 填写 SEEKDB_PASSWORD
docker compose up -d --build
# 打开 http://localhost:8765
```
