import { MODEL, splitText, retrievalMetrics } from './config.js';
export class EdgeLibrary {
  constructor(onEvent = () => {}) {
    this.onEvent = onEvent;
    this.worker = new Worker(new URL('./embed-worker.js', import.meta.url), { type: 'module' });
    this.calls = new Map(); this.sequence = 0; this.selection = null; this.workerError = null;
    this.worker.onmessage = ({ data }) => {
      const pending = this.calls.get(data.id);
      if (!pending) return;
      if (data.event) return this.onEvent(data.event);
      this.calls.delete(data.id);
      if (data.error) pending.reject(new Error(data.error)); else pending.resolve(data.result);
    };
    this.worker.onerror = event => {
      this.workerError = new Error(event.message || '推理 Worker 加载失败，请检查浏览器控制台与模型资源');
      this.onEvent({ type: 'error', message: this.workerError.message });
      for (const pending of this.calls.values()) pending.reject(this.workerError);
      this.calls.clear();
    };
  }
  call(type, data) {
    if (this.workerError) return Promise.reject(this.workerError);
    return new Promise((resolve, reject) => {
      const id = ++this.sequence;
      this.calls.set(id, { resolve, reject }); this.worker.postMessage({ id, type, ...data });
    });
  }
  async api(path, payload) {
    const result = await fetch(`/api/${path}`, payload ? { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) } : undefined);
    const data = await result.json();
    if (!result.ok) throw new Error(data.error || `HTTP ${result.status}`);
    return data;
  }
  async open(library, dtype = 'q8', backend = 'auto') {
    this.selection = null;
    const model = await this.call('init', { dtype, backend });
    const collection = await this.api('open', { library, dtype });
    this.selection = { library, dtype, backend };
    return { model, collection };
  }
  async import(documents, batchSize = 8) {
    if (!this.selection) throw new Error('请先打开知识库');
    const selection = { ...this.selection };
    const start = performance.now();
    const { embeddings, ...timing } = await this.call('embed', { texts: documents.map(d => `${d.title}\n${d.text}`), batchSize });
    let writeMs = 0, refreshMs = 0, count = 0;
    for (let i = 0; i < documents.length; i += 128) {
      const result = await this.api('import', { ...selection, documents: documents.slice(i, i + 128).map((d, j) => ({ ...d, embedding: embeddings[i + j] })) });
      writeMs += result.writeMs; refreshMs += result.refreshMs; count = result.count;
    }
    return { ...timing, writeMs, refreshMs, count, documents: documents.length, totalMs: performance.now() - start };
  }
  async search(query, k = 5) {
    if (!this.selection) throw new Error('请先打开知识库');
    const selection = { ...this.selection };
    const start = performance.now();
    const embedded = await this.call('embed', { texts: [query], batchSize: 1 });
    const result = await this.api('search', { ...selection, query, embedding: embedded.embeddings[0], k });
    return { ...result, queryEmbedMs: embedded.embedMs, backend: embedded.backend, e2eMs: performance.now() - start };
  }
  async fileDocuments(files) {
    const documents = [];
    for (const file of files) {
      if (file.size > 2 * 1024 * 1024) throw new Error(`${file.name} 超过 2 MiB`);
      const text = await file.text();
      const digest = [...new Uint8Array(await crypto.subtle.digest('SHA-256', new TextEncoder().encode(file.name + '\n' + text)))].map(v => v.toString(16).padStart(2, '0')).join('');
      splitText(text).forEach((chunk, i) => documents.push({ id: `${digest}:${i}`, text: chunk, title: file.name.slice(0, 280) + ` #${i + 1}` }));
    }
    if (!documents.length) throw new Error('文件没有可导入的正文');
    return documents;
  }
  async benchmark({ library, dtype, backend, batchSize = 8, repetitions = 3 }) {
    const dataset = await (await fetch('/data/evaluation.json')).json();
    const device = { userAgent: navigator.userAgent, hardwareConcurrency: navigator.hardwareConcurrency, deviceMemory: navigator.deviceMemory, crossOriginIsolated };
    const opened = await this.open(library, dtype, backend);
    const trials = [];
    for (let trial = 0; trial < repetitions; trial++) {
      const ingestion = await this.import(dataset.documents, batchSize);
      const queries = [];
      for (const query of dataset.queries) {
        const result = await this.search(query.text, 5);
        queries.push({ query: query.text, ids: result.results.map(r => r.id), relevant: query.relevant, queryEmbedMs: result.queryEmbedMs, dbMs: result.dbMs, e2eMs: result.e2eMs, ...retrievalMetrics(result.results.map(r => r.id), query.relevant, 5) });
      }
      trials.push({ trial, phase: trial === 0 ? 'first-inference' : 'warm', ingestion, queries });
    }
    const resources = performance.getEntriesByType('resource').filter(e => e.name.includes('/models/')).map(e => ({ name: e.name.replace(location.origin, ''), durationMs: e.duration, transferSize: e.transferSize, decodedBodySize: e.decodedBodySize }));
    return { createdAt: new Date().toISOString(), model: MODEL, config: { dtype, backend, batchSize, repetitions, library }, device, opened, resources, trials };
  }
  close() { this.worker.terminate(); }
}
