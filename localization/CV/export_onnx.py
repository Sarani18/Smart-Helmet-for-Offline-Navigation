"""
Smart Helmet — Export ONNX Model
--------------------------------------
Exports the trained PyTorch LRASPP segmentation model to ONNX format 
so it can be integrated into the Android mobile app.

Usage:
    python3 export_onnx.py --checkpoint models/best.pth --output models/helmet_model.onnx
"""

import argparse
from pathlib import Path

import torch
import torch.nn as nn
from torchvision.models.segmentation import lraspp_mobilenet_v3_large

NUM_CLASSES = 27
IMG_SIZE = 320

def load_model(checkpoint: str, device: torch.device) -> nn.Module:
    """Loads the trained LRASPP model."""
    model = lraspp_mobilenet_v3_large(weights=None)
    low_in = model.classifier.low_classifier.in_channels
    high_in = model.classifier.high_classifier.in_channels
    model.classifier.low_classifier = nn.Conv2d(low_in, NUM_CLASSES, 1)
    model.classifier.high_classifier = nn.Conv2d(high_in, NUM_CLASSES, 1)

    ckpt = torch.load(checkpoint, map_location=device, weights_only=False)
    model.load_state_dict(ckpt["model_state_dict"])
    model.to(device).eval()
    return model

def main():
    parser = argparse.ArgumentParser(description="Export PyTorch model to ONNX")
    parser.add_argument("--checkpoint", default="models/best.pth", help="Path to trained PyTorch checkpoint")
    parser.add_argument("--output", default="models/helmet_model.onnx", help="Path to save ONNX model")
    parser.add_argument("--opset", type=int, default=14, help="ONNX opset version (14 recommended for Android)")
    args = parser.parse_args()

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    # Use CPU for export to ensure maximum ONNX compatibility
    device = torch.device("cpu")
    print(f"🔄 Loading checkpoint from {args.checkpoint}...")
    model = load_model(args.checkpoint, device)

    print(f"⚙️ Exporting model to ONNX (opset {args.opset})...")
    
    # Create dummy input of the correct shape (Batch, Channels, Height, Width)
    dummy_input = torch.randn(1, 3, IMG_SIZE, IMG_SIZE, device=device)

    # Export
    torch.onnx.export(
        model,
        dummy_input,
        str(out_path),
        export_params=True,
        opset_version=args.opset,
        do_constant_folding=True,
        input_names=["input"],
        output_names=["output"],
        dynamic_axes={
            "input": {0: "batch_size"},
            "output": {0: "batch_size"}
        }
    )

    print(f"✅ Successfully exported ONNX model to: {out_path}")
    print(f"📊 Input shape: {dummy_input.shape}")
    print(f"Ready for Android integration!")

if __name__ == "__main__":
    main()
