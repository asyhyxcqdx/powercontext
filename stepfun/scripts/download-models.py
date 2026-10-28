"""Download the fixed, public Apache-2.0 ONNX files. No inference is run here."""
import hashlib
import json
import pathlib
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor

ROOT = pathlib.Path(__file__).resolve().parents[1]
MODEL = 'Xenova/all-MiniLM-L6-v2'
REVISION = '751bff37182d3f1213fa05d7196b954e230abad9'
FILES = {
    'onnx/model.onnx': '759c3cd2b7fe7e93933ad23c4c9181b7396442a2ed746ec7c1d46192c469c46e',
    'onnx/model_fp16.onnx': '2cdb5e58291813b6d6e248ed69010100246821a367fa17b1b81ae9483744533d',
    'onnx/model_quantized.onnx': 'afdb6f1a0e45b715d0bb9b11772f032c399babd23bfc31fed1c170afc848bdb1',
    'config.json': None, 'tokenizer.json': None, 'tokenizer_config.json': None,
    'special_tokens_map.json': None,
}

def download(item):
    name, expected = item
    target = ROOT / '.cache' / 'models' / MODEL / name
    target.parent.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
    cached = target.exists() and (not expected or hashlib.sha256(target.read_bytes()).hexdigest() == expected)
    if not cached:
        temporary = target.with_suffix(target.suffix + '.partial')
        for attempt in range(3):
            try:
                with urllib.request.urlopen(f'https://huggingface.co/{MODEL}/resolve/{REVISION}/{name}', timeout=90) as source, temporary.open('wb') as out:
                    while chunk := source.read(1024 * 1024):
                        out.write(chunk)
                if expected and hashlib.sha256(temporary.read_bytes()).hexdigest() != expected:
                    raise ValueError(f'SHA-256 mismatch: {name}')
                temporary.replace(target)
                break
            except Exception:
                if attempt == 2: raise
                time.sleep(2)
    record = {'file': name, 'bytes': target.stat().st_size, 'sha256': hashlib.sha256(target.read_bytes()).hexdigest(), 'downloadMs': 1000 * (time.perf_counter() - started), 'cached': cached}
    print(json.dumps(record), flush=True)
    return record

if __name__ == '__main__':
    with ThreadPoolExecutor(max_workers=3) as pool:
        results = list(pool.map(download, FILES.items()))
    artifact = ROOT / '.cache' / 'model-download.json'
    artifact.write_text(json.dumps({'model': MODEL, 'revision': REVISION, 'files': results}, indent=2))
