# StepFun 一页技术说明：端侧书房

**实现**：文档、查询均在浏览器 Web Worker 内使用 Transformers.js 4.3.2 / ONNX Runtime Web 推理；Node 仅接收结果向量，不运行模型、不调用云端推理。默认请求 WebGPU，加载或推理失败自动切到 WASM并显示原因。显式 WebGPU 模式用于验证，不静默降级。WASM 使用最多 4 个线程。

**模型与量化**：Apache-2.0 的 Xenova/all-MiniLM-L6-v2，固定 revision `751bff37182d3f1213fa05d7196b954e230abad9`，384 维 mean pooling + L2 归一化。直接使用同一模型仓库公开的 ONNX FP32 / INT8 动态量化导出，下载脚本核验 SHA-256，不重新训练。文件体积统计 ONNX 权重与相同的四份 tokenizer/config 文件；实测 FP32 91.10 MB、INT8 23.69 MB，压缩比 3.85×。另提供 FP16 文件供兼容设备使用；本环境 WebGPU 未暴露 shader-f16，未把它列为已通过的 GPU 实验。

**seekdb**：seekdb-js 1.4.0 + 嵌入式 seekdb v1.4.0.0，cosine HNSW + IK smart。显式关闭自动 embedding，标题、原文、ID、精度与模型版本随向量持久化；完整问题向量和去常见虚词的关键词进入数据库的 DBMS_HYBRID_SEARCH，由数据库完成 RRF。不同知识库/精度使用独立集合；SHA-256 内容 ID 幂等 upsert，批后 refresh_index。SDK 会话变量相关操作串行执行，UI 忙碌期间锁定配置。1.4.0 对 SQL 引号中普通单词误报的兼容处理仅屏蔽字面量供验证，保留 SELECT、危险语句、单语句检查，并拒绝可执行 SQL 注释；有正反向回归测试。

**实测条件**：AMD EPYC 7K62 48-Core Processor；NVIDIA RTX 4090（浏览器报告 nvidia / lovelace）；linux 6.8.0-136-generic；Chrome for Testing 156.0.8078.4。应用和数据库在同一服务器，浏览器实际在此服务器执行；HTTP 是 loopback，端到端耗时包括浏览器 Worker、HTTP 和数据库，至结果可用于展示。原创 32 文档 / 12 人工标注查询；每配置 3 次，首次推理单列，表内为后 2 次（24 查询）的中位延迟和平均质量。模型加载为每配置一个新浏览器的首次观测，不冒充多次冷启动中位数。

| 精度 / 后端 / 批大小 | 模型 MB | 首次加载 ms | 预热后文档/秒 | 检索 ms | 查询端到端 ms | Recall@5 / nDCG@5 |
|---|---:|---:|---:|---:|---:|---:|
| FP32 / WASM / 1 | 91.10 | 2325 | 47.6 | 7.24 | 23.26 | 0.875 / 0.858 |
| Q8 / WASM / 1 | 23.69 | 1621 | 51.9 | 7.19 | 22.50 | 0.875 / 0.864 |
| Q8 / WASM / 8 | 23.69 | 1700 | 76.6 | 6.84 | 21.78 | 0.875 / 0.858 |
| Q8 / WEBGPU / 8 | 23.69 | 3095 | 18.6 | 8.32 | 234.89 | 0.875 / 0.864 |

**结论与限制**：同为 INT8/WASM，批 8 相对批 1 的文档吞吐提高 1.48×；INT8 的 Recall@5 与 FP32 相同，nDCG 变化约 0.0000。本语料短且规模小，INT8/WebGPU 实测比 WASM 慢，不宣称 GPU 加速收益；保留赛题要求的 GPU 优先策略，同时允许用户选择 WASM。质量仅反映这套有限英文语料，不代表中文或通用检索效果。

**证据与复现**：`npm ci` → `python3 scripts/download-models.py` → `npm start`；测试与矩阵见 README。`artifacts/benchmark-*.json` 保留所有首次/预热样本、模型资源下载、导入/刷新/查询阶段、每查询结果 ID 与指标；`model-download.json` 保留模型实际字节数和摘要；`browser-check-wasm.json`、`browser-check-webgpu.json` 与截图覆盖真实导入、重复写入、增量可见性、集合切换、页面重载、错误向量和无云端推理请求。
