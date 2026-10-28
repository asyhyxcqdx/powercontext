import { mkdir, writeFile } from 'node:fs/promises';
import os from 'node:os';
import { browser, pageFor } from './browser-common.mjs';
const configs = [
  { dtype: 'fp32', backend: 'wasm', batchSize: 1 },
  { dtype: 'q8', backend: 'wasm', batchSize: 1 },
  { dtype: 'q8', backend: 'wasm', batchSize: 8 },
  { dtype: 'q8', backend: 'webgpu', batchSize: 8 },
];
await mkdir('artifacts', { recursive: true });
for (const [i, config] of configs.entries()) {
  const instance = await browser(config.backend === 'webgpu');
  try {
    const page = await pageFor(instance);
    const configWithLibrary = { ...config, library: `eval_${Date.now()}_${i}`, repetitions: 3 };
    console.log('Benchmark:', JSON.stringify(config));
    const result = await page.evaluate(config => window.edgeLibrary.benchmark(config), configWithLibrary);
    result.host = { platform: os.platform(), release: os.release(), architecture: os.arch(), cpu: os.cpus()[0]?.model, browser: instance.version() };
    const adapter = JSON.stringify(result.opened.model.adapterInfo || {});
    if (config.backend === 'webgpu' && !result.opened.model.adapterInfo?.vendor) throw new Error('WebGPU hardware identity was not exposed; cannot certify this run as hardware evidence');
    if (config.backend === 'webgpu' && /swiftshader|llvmpipe|software/i.test(adapter)) throw new Error(`WebGPU uses a software adapter, not hardware: ${adapter}`);
    await writeFile(`artifacts/benchmark-${config.dtype}-${config.backend}-b${config.batchSize}.json`, JSON.stringify(result, null, 2));
    console.log('Saved', config.dtype, config.backend, result.opened.model.adapterInfo);
  } finally { await instance.close(); }
}
