import { EdgeLibrary } from './library.js';
const $ = id => document.getElementById(id);
const records = []; let busy = false; let opened = false;
function log(message, data) { records.push({ at: new Date().toISOString(), message, data }); $('log').textContent = records.slice(-12).map(r => `${r.at.slice(11,19)}  ${r.message}${r.data ? '\n' + JSON.stringify(r.data) : ''}`).join('\n'); }
function status(text, error = false) { $('status').textContent = text; $('status').className = error ? 'error' : ''; }
const library = new EdgeLibrary(event => {
  if (event.type === 'error') { status(event.message, true); log('Worker 错误', { error: event.message }); }
  if (event.type === 'progress') { status(`加载模型：${event.progress.file || event.progress.status}`); if (Number.isFinite(event.progress.progress)) $('progress').value = event.progress.progress; }
  if (event.type === 'embedding') { status(`浏览器向量化：${event.completed} / ${event.total}`); $('progress').value = event.completed * 100 / event.total; }
  if (event.type === 'backend') { $('backend').textContent = `${event.backend.toUpperCase()} · ${event.dtype.toUpperCase()}`; if (event.fallbackReason) log('自动降级到 WASM', { reason: event.fallbackReason }); }
});
function selection() { return { library: $('library').value.trim(), dtype: $('dtype').value, backend: $('device').value }; }
function controls() {
  for (const id of ['open','library','dtype','device','batch','files','benchmark']) $(id).disabled = busy;
  for (const id of ['import','sample','search']) $(id).disabled = busy || !opened;
}
async function work(fn) {
  if (busy) return;
  busy = true; controls();
  try { await fn(); } catch (error) { status(error.message, true); log('失败', { error: error.message }); }
  finally { busy = false; controls(); }
}
function timing(values) {
  $('timings').replaceChildren();
  for (const [label, value] of Object.entries(values)) { const el = document.createElement('span'); el.className = 'metric'; el.textContent = `${label} ${Number(value).toFixed(1)} ms`; $('timings').append(el); }
}
function download(data, name) {
  const url = URL.createObjectURL(new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' }));
  const a = document.createElement('a'); a.href = url; a.download = name; a.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
}
for (const id of ['library','dtype','device']) $(id).addEventListener('change', () => { opened = false; $('results').replaceChildren(); controls(); status('配置已改变，请重新打开知识库'); });
$('open').onclick = () => work(async () => {
  opened = false;
  const config = selection(); const result = await library.open(config.library, config.dtype, config.backend);
  opened = true; localStorage.setItem('edge-library-selection', JSON.stringify(config));
  $('count').textContent = `${result.collection.name} · ${result.collection.count} 个文档块`;
  $('backend').textContent = `${result.model.backend.toUpperCase()} · ${config.dtype.toUpperCase()}`;
  status(result.model.fallbackReason ? `已打开。${result.model.fallbackReason}，已自动使用 WASM。` : '知识库已打开，可连续导入或搜索');
  timing({ '模型加载': result.model.loadMs }); log('打开知识库', result);
});
async function ingest(documents) {
  const result = await library.import(documents, Number($('batch').value));
  $('count').textContent = `${selection().library} · ${result.count} 个文档块`;
  timing({ '文档向量化': result.embedMs, '写入': result.writeMs, '索引刷新': result.refreshMs, '总耗时': result.totalMs });
  status(`已导入 ${documents.length} 块并刷新索引，现有 ${result.count} 块；重复文件按内容 ID 更新。`); log('导入完成', result);
}
$('import').onclick = () => work(async () => ingest(await library.fileDocuments([...$('files').files])));
$('sample').onclick = () => work(async () => ingest((await (await fetch('/data/evaluation.json')).json()).documents));
$('search-form').onsubmit = event => { event.preventDefault(); if (!opened) return; work(async () => {
  const query = $('query').value.trim(); if (!query) throw new Error('请输入搜索问题');
  const result = await library.search(query); $('results').replaceChildren();
  for (const [i, entry] of result.results.entries()) {
    const article = document.createElement('article'); article.className = 'result';
    const title = document.createElement('h4'); title.textContent = `${i + 1}. ${entry.metadata?.title || entry.id}`;
    const text = document.createElement('p');
    const titlePrefix = `${entry.metadata?.title || ''}\n`;
    text.textContent = entry.text?.startsWith(titlePrefix) ? entry.text.slice(titlePrefix.length) : entry.text;
    const source = document.createElement('div'); source.className = 'source'; source.textContent = `文档 ${entry.id} · ${entry.metadata?.dtype || ''} · 数据库返回顺序`;
    article.append(title, text, source); $('results').append(article);
  }
  if (!result.results.length) $('results').textContent = '此集合暂无匹配结果，请先导入资料。';
  timing({ '查询向量化': result.queryEmbedMs, '数据库检索': result.dbMs, '端到端': result.e2eMs }); status(`找到 ${result.results.length} 条结果`); log('查询完成', { query, ...result });
}); };
$('export').onclick = () => download(records, 'edge-library-log.json');
$('benchmark').onclick = () => work(async () => {
  const config = selection(); opened = false;
  const result = await library.benchmark({ ...config, library: `bench_${Date.now()}`, batchSize: Number($('batch').value) });
  download(result, `benchmark-${config.dtype}-${result.opened.model.backend}.json`);
  library.selection = null; $('count').textContent = '实验已完成，请重新打开自己的知识库';
  status('实验完成，原始 JSON 已导出；实验使用独立集合'); log('实验完成', { library: result.config.library });
});
try { const saved = JSON.parse(localStorage.getItem('edge-library-selection')); if (saved) for (const key of ['library','dtype']) $(key).value = saved[key]; } catch {}
library.api('libraries').then(({ names }) => { for (const name of [...new Set(names.map(n => n.replace(/^edge_/, '').replace(/_(q8|fp16|fp32)$/, '')))]) { const option = document.createElement('option'); option.value = name; $('known-libraries').append(option); } }).catch(error => status(`数据库连接失败：${error.message}`, true));
// The test runner uses the same browser module as the UI, without Node inference.
window.edgeLibrary = library;
controls();
