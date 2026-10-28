# 端侧书房 · StepFun × seekdb

浏览器本地生成文档和查询向量，seekdb 保存原文、元数据和向量，并在数据库内执行全文 + HNSW + RRF 混合检索。Node 服务只提供静态文件、写入与检索接口，不调用任何推理服务。模型为公开的 Apache-2.0 `Xenova/all-MiniLM-L6-v2`，固定版本 `751bff37182d3f1213fa05d7196b954e230abad9`。

## 启动

需要 Node.js 24+、Python 3 和现代 Chrome / Edge。默认使用 seekdb 嵌入式模式，无需 Docker。seekdb 官方原生包支持 Linux x64/arm64、macOS arm64、Windows x64；实测环境见 `artifacts/`。

在本目录执行：

```bash
npm ci
python3 scripts/download-models.py
npm start
```

打开 <http://127.0.0.1:8787>。下载脚本固定模型版本，并核验三份 ONNX 文件的 SHA-256。默认全部模型与浏览器资源从应用自己的 HTTP 服务加载；首次启动 seekdb SDK 会下载官方原生运行库。

本目录 `.npmrc` 关闭自动 peer 依赖和依赖安装脚本：应用显式关闭 seekdb 自动向量化，仅使用 Transformers.js 浏览器 bundle，不需要 `@seekdb/default-embed`、`onnxruntime-node` 的原生推理文件或 sharp 的安装脚本。`npm ci` 使用提交的 lockfile。

如果服务器已有 HTTP/HTTPS 代理和系统证书，需要让 Node 的 fetch 使用它们，可使用：

```bash
NODE_OPTIONS='--use-system-ca --use-env-proxy' npm start
```

不需要关闭 TLS 证书校验。

## 操作

1. 输入知识库名，选择 INT8、FP16 或 FP32，以及自动 / WASM / 显式 WebGPU，点击“打开 / 创建知识库”。自动模式优先请求 WebGPU；无适配器、模型加载或执行失败时转为 WASM，并在界面记录原因。显式 WebGPU 模式失败时直接报告错误，便于确认硬件路径。
2. 导入 TXT / Markdown，或导入 32 篇示例文档。原文按最多 900 个 Unicode 字符分块，相邻块重叠 100 个字符；模型仍受其 tokenizer 最大序列长度限制。本模型及固定评测集主要面向英文，不承诺中文检索质量。
3. 输入问题，查看数据库返回的排序结果、原文、文档 ID 和标题。界面显示向量化、写入、刷新、查询与端到端耗时。
4. 连续导入、切换知识库或重新打开浏览器均使用持久化集合。文件名和正文的 SHA-256 决定块 ID，重复导入相同文件会 upsert；修改后的文件是新内容，旧内容不会自动删除。切换精度使用独立集合，需要重新导入。
5. “导出运行记录”保存实际交互；“复现实验”使用独立实验集合，不污染当前知识库。

模型文件、依赖、数据库与测试浏览器均在 `.cache/`、`.data/`、`node_modules/`，不提交。Linux 启动器仅为子进程预留原生库静态 TLS，并关闭冲突的 SIGUSR1 调试器辅助线程；不改变系统配置。服务等待数据库恢复完成后才监听，重启可能需要约一分钟。服务默认只监听本机；通过 SSH 端口转发访问远程服务器时，浏览器仍在访问者设备计算。若部署远程前端，应使用 HTTPS 以启用 WebGPU；该本地演示服务不提供多用户身份认证。

## 数据层

SDK 1.4.0 的混合检索验证器会误拒绝引号中的 `update` 等正常搜索词；`sdk-compat.mjs` 对引用内容做词法遮罩供原有只读验证器分析，并拒绝可执行注释。`npm test` 覆盖正常搜索及真实危险语句。

每个知识库与精度对应一个 `edge_<name>_<dtype>` 集合：384 维、cosine HNSW 向量索引，IK smart 全文索引；元数据包含标题、模型 ID、固定 revision、精度与导入时间。`embeddingFunction: null` 禁止数据库 SDK 自动生成向量。

写入使用 `upsert`，一批最多 128 块，完成后调用 `refresh_index()`；浏览器向量化批大小可设为 1、8、16。检索使用一次 `collection.hybridSearch()`，由 `DBMS_HYBRID_SEARCH` 生成、执行全文与向量的融合 SQL；不在 Node 或浏览器合并两路结果。SDK 混合检索涉及 SQL 会话变量，服务端串行执行数据库操作，避免多标签页请求交错导致串库。请求须携带明确集合和精度。

可连接已有 seekdb server（先创建指定数据库），不需要修改源码：

```bash
SEEKDB_HOST=127.0.0.1 SEEKDB_PORT=2881 SEEKDB_DATABASE=test \
SEEKDB_USER=root SEEKDB_PASSWORD='本地配置的密码' npm start
```

## 验证和性能实验

安装仅用于本地验收的浏览器并执行：

```bash
PLAYWRIGHT_BROWSERS_PATH=.cache/browsers npx playwright install chromium
npm test
npm run test:browser
npm run benchmark
node scripts/browser-check.mjs --gpu
node scripts/summarize.mjs
```

以上后两项需要先启动服务。运行记录保存在 `artifacts/`，包含浏览器版本、硬件、实际后端、冷启动/预热样本、每条查询结果 ID 与质量值。`data/evaluation.json` 是本项目原创的 32 篇英文文本和 12 条人工标注查询，相关性标注不由模型生成；它是有限规模的可复现实验，不能代表通用检索效果。

矩阵分别测 FP32/WASM/批 1、INT8/WASM/批 1、INT8/WASM/批 8、INT8/WebGPU/批 8，每种配置重复 3 次。比较批处理只对比同为 INT8/WASM 的两项，避免把精度或后端差异误归因于批处理。冷模型加载与首次推理单列；后续重复请求报告中位数。Linux 无头 WebGPU 通过 Chromium 官方建议的 Vulkan 参数启用，脚本拒绝将 SwiftShader / llvmpipe 的软件适配器当作硬件 GPU 结果。

真实验证结果与一页技术说明见 `TECHNICAL.md`；其中数据来自本版本实际运行，保留原始记录。

## 文件

- `server.mjs`：HTTP 接口和 seekdb 数据访问。
- `public/embed-worker.js`：浏览器 Web Worker 内推理、批处理和降级。
- `public/library.js`、`public/app.js`：知识库会话、交互与同源 API。
- `scripts/download-models.py`：固定模型下载与校验。
- `scripts/browser-check.mjs`：真实浏览器全流程、增量、隔离、持久化检查。
- `scripts/benchmark.mjs`：同数据集的精度、后端与批处理实验。
- `data/`：原创语料、人工相关性标注和确定性生成脚本。

参考：[官方赛题](https://oceanbase.yuque.com/org-wiki-obtech-vh7w9r/hc3pio/kw9wfx4bu9pyvat9)、[seekdb-js](https://github.com/oceanbase/seekdb-js)、[模型](https://huggingface.co/Xenova/all-MiniLM-L6-v2)、[Chromium 无头 GPU](https://chromium.googlesource.com/chromium/src.git/+/main/docs/gpu/using-gpu-hardware-in-headless-chrome.md)。
