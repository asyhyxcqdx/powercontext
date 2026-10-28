import { pipeline, env } from '/vendor/transformers/transformers.js';
import { MODEL, DTYPES } from './config.js';

env.allowRemoteModels = false;
env.allowLocalModels = true;
env.localModelPath = '/models/';
env.backends.onnx.wasm.wasmPaths = '/vendor/ort/';
env.backends.onnx.wasm.numThreads = Math.min(4, navigator.hardwareConcurrency || 1);
let extractor;
let settings;
let queue = Promise.resolve();
const report = (id, event) => postMessage({ id, event });
async function init(id, { dtype = 'q8', backend = 'auto' }) {
  if (!DTYPES.includes(dtype) || !['auto', 'webgpu', 'wasm'].includes(backend)) throw new Error('无效推理配置');
  if (extractor && settings.dtype === dtype && settings.requestedBackend === backend) return { ...settings, cachedPipeline: true, loadMs: 0 };
  if (extractor) { await extractor.dispose(); extractor = null; }
  const start = performance.now();
  let device = backend === 'wasm' ? 'wasm' : 'webgpu';
  let fallbackReason = null;
  let adapterInfo = null;
  if (device === 'webgpu') {
    let adapter = await navigator.gpu?.requestAdapter({ powerPreference: 'high-performance' });
    // Some Chromium/Dawn builds transiently return null during first GPU startup.
    if (!adapter && navigator.gpu) adapter = await navigator.gpu.requestAdapter({ powerPreference: 'high-performance' });
    if (adapter) { adapterInfo = { vendor: adapter.info?.vendor, architecture: adapter.info?.architecture, device: adapter.info?.device, description: adapter.info?.description }; }
    else {
      if (backend === 'webgpu') throw new Error('明确要求 WebGPU，但当前浏览器没有可用适配器');
      fallbackReason = '浏览器未提供 WebGPU 适配器'; device = 'wasm';
    }
  }
  const load = () => pipeline('feature-extraction', MODEL.id, {
    dtype, device, revision: MODEL.revision,
    progress_callback: progress => report(id, { type: 'progress', progress }),
  });
  try { extractor = await load(); }
  catch (error) {
    if (device !== 'webgpu' || backend !== 'auto') throw error;
    fallbackReason = `WebGPU 模型加载失败：${error.message}`;
    device = 'wasm'; extractor = await load();
  }
  settings = { dtype, backend: device, requestedBackend: backend, fallbackReason, adapterInfo, model: MODEL.id, revision: MODEL.revision, loadMs: performance.now() - start, cachedPipeline: false, resources: performance.getEntriesByType('resource').filter(e => e.name.includes('/models/')).map(e => ({ name: e.name.replace(location.origin, ''), durationMs: e.duration, transferSize: e.transferSize, decodedBodySize: e.decodedBodySize })) };
  report(id, { type: 'backend', ...settings });
  return settings;
}
async function run(id, payload) {
  if (payload.type === 'init') return init(id, payload);
  if (payload.type !== 'embed' || !extractor) throw new Error('请先加载模型');
  if (!Array.isArray(payload.texts) || !payload.texts.length || !payload.texts.every(t => typeof t === 'string' && t.trim())) throw new Error('没有有效文本');
  const batchSize = payload.batchSize ?? 8;
  if (!Number.isInteger(batchSize) || batchSize < 1 || batchSize > 32) throw new Error('批大小范围为 1–32');
  const start = performance.now();
  const embeddings = [];
  for (let offset = 0; offset < payload.texts.length; offset += batchSize) {
    const texts = payload.texts.slice(offset, offset + batchSize);
    let output;
    try { output = await extractor(texts, { pooling: 'mean', normalize: true, truncation: true }); }
    catch (error) {
      if (settings.backend !== 'webgpu' || settings.requestedBackend !== 'auto') throw error;
      await extractor.dispose(); extractor = null;
      const previousReason = `WebGPU 执行失败：${error.message}`;
      await init(id, { dtype: settings.dtype, backend: 'wasm' });
      settings.fallbackReason = previousReason;
      report(id, { type: 'backend', ...settings });
      output = await extractor(texts, { pooling: 'mean', normalize: true, truncation: true });
    }
    embeddings.push(...output.tolist());
    output.dispose?.();
    report(id, { type: 'embedding', completed: embeddings.length, total: payload.texts.length });
  }
  return { embeddings, embedMs: performance.now() - start, backend: settings.backend, dtype: settings.dtype, batchSize };
}
self.onmessage = ({ data: { id, ...payload } }) => {
  queue = queue.then(async () => {
    try { postMessage({ id, result: await run(id, payload) }); }
    catch (error) { postMessage({ id, error: error.message }); }
  });
};
