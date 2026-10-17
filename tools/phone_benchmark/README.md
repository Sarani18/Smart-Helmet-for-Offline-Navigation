# On-phone segmentation benchmark

Measures latency, memory and battery drain of the road-segmentation model on the
companion smartphone (Table VII of the INDICON 2026 paper).

## Setup

```bash
python3 tools/phone_benchmark/export_onnx.py        # writes seg.onnx, checks it matches PyTorch
cd tools/phone_benchmark
npm pack onnxruntime-web@1.20.1 && tar xzf onnxruntime-web-1.20.1.tgz
cp package/dist/ort.wasm.min.js package/dist/ort.webgpu.min.js package/dist/ort-wasm-simd-threaded*.{mjs,wasm} .
openssl req -x509 -newkey rsa:2048 -nodes -keyout key.pem -out cert.pem -days 3 \
  -subj "/CN=<mac-lan-ip>" -addext "subjectAltName=IP:<mac-lan-ip>"
python3 server.py 8766                               # HTTPS, cross-origin isolated
```

Open `https://<mac-lan-ip>:8766/<page>` on the phone (same Wi-Fi) and accept the certificate warning.
Results are POSTed back and appended to `results.jsonl`.

| Page | What it measures |
|---|---|
| `v2.html` | 1-thread CPU and WebGPU latency, with a per-pixel check of GPU output against CPU |
| `mt.html` | 4-thread CPU latency |
| `power.html?mode=idle`, `power.html` | 30 min battery drain idle vs. continuous GPU inference |
| `index.html` | first version over plain HTTP |

Plain-HTTP pages are not a secure context, so Safari runs WebAssembly in a much slower mode;
the three `index.html` runs in `results_iphone17promax.json` (about 1.9 s per inference) show
this and were not used in the paper.

`results_iphone17promax.json` holds the recorded iPhone 17 Pro Max runs (local IPs removed).
