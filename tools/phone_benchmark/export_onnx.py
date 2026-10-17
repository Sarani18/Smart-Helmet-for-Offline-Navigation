"""Export the road-segmentation checkpoint to ONNX and check it matches PyTorch.

    python3 tools/phone_benchmark/export_onnx.py [out_path]
"""
import sys
from pathlib import Path

import numpy as np
import onnxruntime as ort
import torch
from torchvision.models.segmentation import lraspp_mobilenet_v3_large

REPO = Path(__file__).resolve().parents[2]
CKPT = REPO / "localization/CV/models/best.pth"


class SegOut(torch.nn.Module):
    def __init__(self, model):
        super().__init__()
        self.model = model

    def forward(self, x):
        return self.model(x)["out"]


def main() -> int:
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).parent / "seg.onnx"
    model = lraspp_mobilenet_v3_large(weights=None, num_classes=27)
    state = torch.load(CKPT, map_location="cpu", weights_only=False)
    for key in ("model_state_dict", "state_dict", "model"):
        if isinstance(state, dict) and isinstance(state.get(key), dict):
            state = state[key]
            break
    missing = model.load_state_dict(state, strict=False).missing_keys
    if missing:
        raise SystemExit(f"checkpoint incomplete, missing e.g. {missing[:3]}")

    # The wrapper must be in eval mode: the exporter restores the module's
    # original training flag afterwards, which would switch BatchNorm to batch stats.
    net = SegOut(model).eval()
    x = torch.randn(1, 3, 320, 320)
    torch.onnx.export(net, x, str(out), input_names=["input"], output_names=["out"],
                      opset_version=17, dynamo=False)
    net.eval()

    sess = ort.InferenceSession(str(out), providers=["CPUExecutionProvider"])
    for trial in range(3):
        x = torch.randn(1, 3, 320, 320)
        with torch.no_grad():
            ref = net(x).numpy()
        got = sess.run(None, {"input": x.numpy()})[0]
        agree = float((got.argmax(1) == ref.argmax(1)).mean())
        print(f"trial {trial}: max abs diff {np.abs(got - ref).max():.2e}, argmax agreement {agree:.4f}")
        if agree < 0.999:
            raise SystemExit("ONNX output does not match PyTorch")
    print(f"wrote {out} ({out.stat().st_size / 1e6:.1f} MB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
