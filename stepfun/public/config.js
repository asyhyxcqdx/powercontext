export const MODEL = {
  id: 'Xenova/all-MiniLM-L6-v2',
  revision: '751bff37182d3f1213fa05d7196b954e230abad9',
  dimension: 384,
  license: 'Apache-2.0',
  files: {
    fp32: { name: 'model.onnx', bytes: 90387606, sha256: '759c3cd2b7fe7e93933ad23c4c9181b7396442a2ed746ec7c1d46192c469c46e' },
    fp16: { name: 'model_fp16.onnx', bytes: 45297825, sha256: '2cdb5e58291813b6d6e248ed69010100246821a367fa17b1b81ae9483744533d' },
    q8: { name: 'model_quantized.onnx', bytes: 22972370, sha256: 'afdb6f1a0e45b715d0bb9b11772f032c399babd23bfc31fed1c170afc848bdb1' },
  },
};
export const DTYPES = Object.keys(MODEL.files);
export function collectionName(library, dtype) {
  if (!/^[a-z][a-z0-9_]{0,39}$/.test(library)) throw new Error('知识库名须以小写字母开头，最多 40 位小写字母、数字、下划线');
  if (!DTYPES.includes(dtype)) throw new Error('不支持的模型精度');
  return `edge_${library}_${dtype}`;
}
export function splitText(text, size = 900, overlap = 100) {
  if (!Number.isInteger(size) || size <= overlap || overlap < 0) throw new Error('分块参数无效');
  const chars = Array.from(text.trim());
  const chunks = [];
  for (let start = 0; start < chars.length;) {
    let end = Math.min(start + size, chars.length);
    if (end < chars.length) {
      const lastBreak = chars.slice(start + Math.floor(size * 0.65), end).findLastIndex(c => /\s/.test(c));
      if (lastBreak >= 0) end = start + Math.floor(size * 0.65) + lastBreak + 1;
    }
    const value = chars.slice(start, end).join('').trim();
    if (value) chunks.push(value);
    if (end === chars.length) break;
    start = end - overlap;
  }
  return chunks;
}
export function retrievalMetrics(ids, relevant, k = 5) {
  const truth = new Set(relevant);
  if (!truth.size) throw new Error('质量评测缺少相关文档标注');
  const top = [...new Set(ids)].slice(0, k);
  const hits = top.filter(id => truth.has(id)).length;
  const dcg = top.reduce((sum, id, i) => sum + (truth.has(id) ? 1 / Math.log2(i + 2) : 0), 0);
  const ideal = Array.from({ length: Math.min(k, truth.size) }, (_, i) => 1 / Math.log2(i + 2)).reduce((a,b) => a+b, 0);
  return { recall: hits / truth.size, ndcg: dcg / ideal };
}

// Natural-language questions contain common function words that otherwise give
// generic passages an unfair second-channel RRF boost. This changes only the
// lexical query; the complete question is still embedded in the browser.
export function lexicalQuery(query) {
  const stop = new Set('a an the and or of to in on at for from with by as is are was were be been being do does did can could would should will how what which who when where why i we you it its this that these those my our your after before without'.split(' '));
  const words = query.match(/[\p{L}\p{N}_-]+/gu) || [];
  const terms = [...new Set(words.filter(w => !stop.has(w.toLowerCase())))];
  return terms.join(' ') || query.trim();
}
