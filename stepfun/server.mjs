import http from 'node:http';
import { readFile, stat } from 'node:fs/promises';
import { createReadStream } from 'node:fs';
import { resolve, sep, extname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { SeekdbClient, Schema, VectorIndexConfig, FulltextIndexConfig } from 'seekdb';
import { fixHybridLiteralValidation } from './sdk-compat.mjs';
import { MODEL, collectionName, lexicalQuery } from './public/config.js';

const ROOT = fileURLToPath(new URL('.', import.meta.url));
const HOST = process.env.HOST || '127.0.0.1';
const PORT = Number(process.env.PORT || 8787);
process.env.SEEKDB_BINDINGS_CACHE_DIR ||= resolve(ROOT, '.cache/seekdb');
const connection = process.env.SEEKDB_HOST ? {
  host: process.env.SEEKDB_HOST, port: Number(process.env.SEEKDB_PORT || 2881),
  database: process.env.SEEKDB_DATABASE || 'test', user: process.env.SEEKDB_USER || 'root',
  password: process.env.SEEKDB_PASSWORD || '',
  ...(process.env.SEEKDB_TENANT ? { tenant: process.env.SEEKDB_TENANT } : {}),
} : { path: resolve(ROOT, process.env.SEEKDB_PATH || '.data/seekdb'), database: 'test' };
const client = new SeekdbClient(connection);
const collections = new Map();
// The SDK uses SQL session variables for hybridSearch. Keep its multi-statement
// operations together, including requests from different browser tabs.
let pending = Promise.resolve();
function serialized(fn) {
  const work = pending.then(fn);
  pending = work.catch(() => {});
  return work;
}
async function collection(library, dtype, create = false) {
  const name = collectionName(library, dtype);
  if (collections.has(name)) return collections.get(name);
  const options = { name, embeddingFunction: null, schema: new Schema({
    vectorIndex: new VectorIndexConfig({ hnsw: { dimension: MODEL.dimension, distance: 'cosine' }, embeddingFunction: null }),
    fulltextIndex: new FulltextIndexConfig('ik', { ik_mode: 'smart' }),
  }) };
  const value = create ? await client.getOrCreateCollection(options)
    : await client.getCollection({ name, embeddingFunction: null });
  const modes = await client.execute('SELECT @@sql_mode AS mode');
  fixHybridLiteralValidation(value, !String(modes?.[0]?.mode || '').split(',').includes('NO_BACKSLASH_ESCAPES'));
  collections.set(name, value);
  return value;
}
function vector(value) {
  if (!Array.isArray(value) || value.length !== MODEL.dimension || !value.every(Number.isFinite)) throw Object.assign(new Error('需要浏览器计算的 384 维有限数值向量'), { status: 400 });
  const norm = Math.hypot(...value);
  if (norm < 0.99 || norm > 1.01) throw Object.assign(new Error('向量必须做 L2 归一化'), { status: 400 });
  return value;
}
function json(response, status, data) {
  response.writeHead(status, { 'Content-Type': 'application/json; charset=utf-8', 'Cache-Control': 'no-store' });
  response.end(JSON.stringify(data));
}
async function body(request) {
  if (!request.headers['content-type']?.startsWith('application/json')) throw Object.assign(new Error('需要 application/json'), { status: 415 });
  const chunks = []; let bytes = 0;
  for await (const chunk of request) {
    bytes += chunk.length;
    if (bytes > 4 * 1024 * 1024) throw Object.assign(new Error('单次请求不能超过 4 MiB'), { status: 413 });
    chunks.push(chunk);
  }
  try { return JSON.parse(Buffer.concat(chunks)); }
  catch { throw Object.assign(new Error('JSON 格式错误'), { status: 400 }); }
}
async function api(request, response, pathname) {
  if (request.method === 'GET' && pathname === '/api/health') {
    const version = await client.execute('SELECT VERSION() AS version');
    return json(response, 200, { mode: connection.path ? 'embedded' : 'server', database: version?.[0]?.version, model: MODEL });
  }
  if (request.method === 'GET' && pathname === '/api/libraries') {
    const rows = await client.listCollections({ withEmbeddingFunction: false });
    const names = rows.map(c => c.name).filter(n => /^edge_[a-z][a-z0-9_]{0,39}_(fp32|fp16|q8)$/.test(n));
    return json(response, 200, { names });
  }
  if (request.method !== 'POST') return json(response, 404, { error: '未找到接口' });
  const data = await body(request);
  const { library, dtype } = data;
  try { collectionName(library, dtype); }
  catch (error) { error.status = 400; throw error; }
  if (pathname === '/api/open') {
    const c = await collection(library, dtype, true);
    return json(response, 200, { name: c.name, count: Number(await c.count()) });
  }
  if (pathname === '/api/import') {
    const docs = data.documents;
    if (!Array.isArray(docs) || !docs.length || docs.length > 128) throw Object.assign(new Error('每批导入 1–128 个文档块'), { status: 400 });
    for (const d of docs) {
      if (typeof d.id !== 'string' || !/^[a-zA-Z0-9_.:-]{1,160}$/.test(d.id) || typeof d.text !== 'string' || !d.text.trim() || d.text.length > 4000 || typeof d.title !== 'string' || d.title.length > 300) throw Object.assign(new Error('文档 ID、标题或正文无效'), { status: 400 });
      vector(d.embedding);
    }
    if (new Set(docs.map(d => d.id)).size !== docs.length) throw Object.assign(new Error('同一批文档 ID 不能重复'), { status: 400 });
    const c = await collection(library, dtype, true);
    const start = performance.now();
    await c.upsert({ ids: docs.map(d => d.id), documents: docs.map(d => `${d.title}\n${d.text}`), embeddings: docs.map(d => d.embedding),
      metadatas: docs.map(d => ({ title: d.title, model: MODEL.id, revision: MODEL.revision, dtype, importedAt: new Date().toISOString() })) });
    const writeMs = performance.now() - start;
    const refreshStart = performance.now();
    await c.refresh_index();
    return json(response, 200, { inserted: docs.length, count: Number(await c.count()), writeMs, refreshMs: performance.now() - refreshStart, refreshed: true });
  }
  if (pathname === '/api/search') {
    const embedding = vector(data.embedding);
    if (typeof data.query !== 'string' || !data.query.trim() || data.query.length > 2000) throw Object.assign(new Error('查询需为 1–2000 个字符'), { status: 400 });
    const k = data.k ?? 5;
    if (!Number.isInteger(k) || k < 1 || k > 20) throw Object.assign(new Error('k 须为 1–20 的整数'), { status: 400 });
    const c = await collection(library, dtype);
    const start = performance.now();
    // DBMS_HYBRID_SEARCH builds and executes the full-text + HNSW + RRF SQL.
    // There is no model, vector calculation, or result fusion on this server.
    const result = await c.hybridSearch({
      query: { whereDocument: { $contains: lexicalQuery(data.query) }, nResults: Math.max(k, 20) },
      knn: { queryEmbeddings: [embedding], nResults: Math.max(k, 20) },
      rank: { rrf: {} }, nResults: k, include: ['documents', 'metadatas', 'distances'],
    });
    const dbMs = performance.now() - start;
    return json(response, 200, { dbMs, name: c.name, results: result.ids[0].map((id, i) => ({
      id, text: result.documents?.[0]?.[i], metadata: result.metadatas?.[0]?.[i], score: result.distances?.[0]?.[i],
    })) });
  }
  return json(response, 404, { error: '未找到接口' });
}
const types = { '.html': 'text/html; charset=utf-8', '.js': 'text/javascript; charset=utf-8', '.mjs': 'text/javascript; charset=utf-8', '.css': 'text/css; charset=utf-8', '.json': 'application/json', '.wasm': 'application/wasm', '.onnx': 'application/octet-stream' };
async function serveFile(response, base, relative) {
  const basePath = resolve(ROOT, base);
  const path = resolve(basePath, relative);
  if (!path.startsWith(basePath + sep)) return json(response, 403, { error: '禁止访问' });
  const info = await stat(path);
  if (!info.isFile()) return json(response, 404, { error: '文件不存在' });
  response.writeHead(200, { 'Content-Type': types[extname(path)] || 'application/octet-stream', 'Content-Length': info.size,
    'Cache-Control': relative.endsWith('.onnx') ? 'public, max-age=31536000, immutable' : 'no-cache' });
  createReadStream(path).on('error', () => response.destroy()).pipe(response);
}
const server = http.createServer(async (request, response) => {
  response.setHeader('Cross-Origin-Opener-Policy', 'same-origin');
  response.setHeader('Cross-Origin-Embedder-Policy', 'require-corp');
  response.setHeader('X-Content-Type-Options', 'nosniff');
  try {
    const url = new URL(request.url, `http://${request.headers.host}`);
    if (url.pathname.startsWith('/api/')) {
      if (request.headers.origin && new URL(request.headers.origin).host !== request.headers.host) return json(response, 403, { error: '不接受跨站请求' });
      return await serialized(() => api(request, response, url.pathname));
    }
    if (request.method !== 'GET') return json(response, 405, { error: '只允许 GET' });
    const path = decodeURIComponent(url.pathname);
    if (path.startsWith('/vendor/transformers/')) return await serveFile(response, 'node_modules/@huggingface/transformers/dist', path.slice('/vendor/transformers/'.length));
    if (path.startsWith('/vendor/ort/')) return await serveFile(response, 'node_modules/onnxruntime-web/dist', path.slice('/vendor/ort/'.length));
    if (path.startsWith('/models/')) return await serveFile(response, '.cache/models', path.slice('/models/'.length));
    if (path.startsWith('/data/')) return await serveFile(response, 'data', path.slice('/data/'.length));
    return await serveFile(response, 'public', path === '/' ? 'index.html' : path.slice(1));
  } catch (error) {
    const status = error.status || (error.code === 'ENOENT' ? 404 : 500);
    if (status === 500) console.error(error.message);
    if (!response.headersSent) json(response, status, { error: error.message });
    else response.destroy();
  }
});
// Wait for embedded recovery before exposing HTTP endpoints.
for (let attempt = 0; ; attempt++) {
  try { await client.execute('SELECT 1'); break; }
  catch (error) {
    if (attempt >= 119 || !/another process|initializ/i.test(error.message)) throw error;
    if (attempt === 0) console.log('Waiting for seekdb startup or previous process shutdown...');
    await new Promise(resolve => setTimeout(resolve, 1000));
  }
}
server.listen(PORT, HOST, () => console.log(`Edge Library listening at http://${HOST}:${PORT}`));
async function stop() { server.close(); await pending; await client.close(); process.exit(0); }
process.on('SIGTERM', stop); process.on('SIGINT', stop);
