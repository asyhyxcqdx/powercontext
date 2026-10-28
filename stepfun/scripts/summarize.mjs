import { readFile, writeFile } from 'node:fs/promises';
import { MODEL } from '../public/config.js';
const variants = [['fp32','wasm',1],['q8','wasm',1],['q8','wasm',8],['q8','webgpu',8]];
const median = a => { const v=[...a].sort((x,y)=>x-y); return (v[Math.floor((v.length-1)/2)]+v[Math.floor(v.length/2)])/2; };
const mean = a => a.reduce((x,y)=>x+y,0)/a.length;
const download = JSON.parse(await readFile('artifacts/model-download.json','utf8'));
const shared = download.files.filter(f=>!f.file.endsWith('.onnx')).reduce((s,f)=>s+f.bytes,0);
const summaries=[];
for (const [dtype, backend, batch] of variants) {
 const file=`benchmark-${dtype}-${backend}-b${batch}.json`;
 const data=JSON.parse(await readFile(`artifacts/${file}`,'utf8'));
 const warm=data.trials.slice(1), queries=warm.flatMap(t=>t.queries);
 const embedMs=median(warm.map(t=>t.ingestion.embedMs));
 summaries.push({ file, dtype, backend, batch, modelBytes:MODEL.files[dtype].bytes+shared, modelLoadMs:data.opened.model.loadMs, coldEmbedMs:data.trials[0].ingestion.embedMs, warmEmbedMs:embedMs, documentsPerSecond:32*1000/embedMs, writeMs:median(warm.map(t=>t.ingestion.writeMs)), refreshMs:median(warm.map(t=>t.ingestion.refreshMs)), queryEmbedMs:median(queries.map(q=>q.queryEmbedMs)), dbMs:median(queries.map(q=>q.dbMs)), e2eMs:median(queries.map(q=>q.e2eMs)), recall:mean(queries.map(q=>q.recall)), ndcg:mean(queries.map(q=>q.ndcg)), host:data.host });
}
const report={ measuredAt:new Date().toISOString(), dataset:{documents:32,queries:12,repetitions:3,warmRepetitions:2}, modelRevision:MODEL.revision, summaries };
await writeFile('artifacts/summary.json',JSON.stringify(report,null,2));
const rows=summaries.map(r=>`| ${r.dtype.toUpperCase()} / ${r.backend.toUpperCase()} / ${r.batch} | ${(r.modelBytes/1e6).toFixed(2)} | ${r.modelLoadMs.toFixed(0)} | ${r.documentsPerSecond.toFixed(1)} | ${r.dbMs.toFixed(2)} | ${r.e2eMs.toFixed(2)} | ${r.recall.toFixed(3)} / ${r.ndcg.toFixed(3)} |`).join('\n');
const [base,serial,batch,gpu]=summaries;
const hardware=base.host;
const note=`# StepFun 一页技术说明：端侧书房

**实现**：文档、查询均在浏览器 Web Worker 内使用 Transformers.js 4.3.2 / ONNX Runtime Web 推理；Node 仅接收结果向量，不运行模型、不调用云端推理。默认请求 WebGPU，加载或推理失败自动切到 WASM并显示原因。显式 WebGPU 模式用于验证，不静默降级。WASM 使用最多 4 个线程。

**模型与量化**：Apache-2.0 的 Xenova/all-MiniLM-L6-v2，固定 revision \`${MODEL.revision}\`，384 维 mean pooling + L2 归一化。直接使用同一模型仓库公开的 ONNX FP32 / INT8 动态量化导出，下载脚本核验 SHA-256，不重新训练。文件体积统计 ONNX 权重与相同的四份 tokenizer/config 文件；实测 FP32 ${(base.modelBytes/1e6).toFixed(2)} MB、INT8 ${(batch.modelBytes/1e6).toFixed(2)} MB，压缩比 ${(base.modelBytes/batch.modelBytes).toFixed(2)}×。另提供 FP16 文件供兼容设备使用；本环境 WebGPU 未暴露 shader-f16，未把它列为已通过的 GPU 实验。

**seekdb**：seekdb-js 1.4.0 + 嵌入式 seekdb v1.4.0.0，cosine HNSW + IK smart。显式关闭自动 embedding，标题、原文、ID、精度与模型版本随向量持久化；完整问题向量和去常见虚词的关键词进入数据库的 DBMS_HYBRID_SEARCH，由数据库完成 RRF。不同知识库/精度使用独立集合；SHA-256 内容 ID 幂等 upsert，批后 refresh_index。SDK 会话变量相关操作串行执行，UI 忙碌期间锁定配置。1.4.0 对 SQL 引号中普通单词误报的兼容处理仅屏蔽字面量供验证，保留 SELECT、危险语句、单语句检查，并拒绝可执行 SQL 注释；有正反向回归测试。

**实测条件**：${hardware.cpu}；NVIDIA RTX 4090（浏览器报告 nvidia / lovelace）；${hardware.platform} ${hardware.release}；Chrome for Testing ${hardware.browser}。应用和数据库在同一服务器，浏览器实际在此服务器执行；HTTP 是 loopback，端到端耗时包括浏览器 Worker、HTTP 和数据库，至结果可用于展示。原创 32 文档 / 12 人工标注查询；每配置 3 次，首次推理单列，表内为后 2 次（24 查询）的中位延迟和平均质量。模型加载为每配置一个新浏览器的首次观测，不冒充多次冷启动中位数。

| 精度 / 后端 / 批大小 | 模型 MB | 首次加载 ms | 预热后文档/秒 | 检索 ms | 查询端到端 ms | Recall@5 / nDCG@5 |
|---|---:|---:|---:|---:|---:|---:|
${rows}

**结论与限制**：同为 INT8/WASM，批 8 相对批 1 的文档吞吐提高 ${(batch.documentsPerSecond/serial.documentsPerSecond).toFixed(2)}×；INT8 的 Recall@5 与 FP32 相同，nDCG 变化约 ${(batch.ndcg-base.ndcg).toFixed(4)}。本语料短且规模小，INT8/WebGPU 实测比 WASM 慢，不宣称 GPU 加速收益；保留赛题要求的 GPU 优先策略，同时允许用户选择 WASM。质量仅反映这套有限英文语料，不代表中文或通用检索效果。

**证据与复现**：\`npm ci\` → \`python3 scripts/download-models.py\` → \`npm start\`；测试与矩阵见 README。\`artifacts/benchmark-*.json\` 保留所有首次/预热样本、模型资源下载、导入/刷新/查询阶段、每查询结果 ID 与指标；\`model-download.json\` 保留模型实际字节数和摘要；\`browser-check-wasm.json\`、\`browser-check-webgpu.json\` 与截图覆盖真实导入、重复写入、增量可见性、集合切换、页面重载、错误向量和无云端推理请求。
`;
await writeFile('TECHNICAL.md',note);
console.log(JSON.stringify(report,null,2));
