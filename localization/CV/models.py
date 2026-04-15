import torch
import torch.nn as nn

# ── Scene classes ─────────────────────────────────────────────────────────────
SCENE_CLASSES = [
    "straight",       # 0
    "slight_left",    # 1
    "slight_right",   # 2
    "left_turn",      # 3
    "right_turn",     # 4
    "sharp_left",     # 5
    "sharp_right",    # 6
    "junction",       # 7
]

NUM_SCENE_CLASSES = len(SCENE_CLASSES)

class TinySceneCNN(nn.Module):
    """
    Tiny CNN for scene classification from road masks.
    
    Architecture:
        Conv(1→16, 3x3) → BN → ReLU → MaxPool(2)     → 32×32
        Conv(16→32, 3x3) → BN → ReLU → MaxPool(2)    → 16×16
        Conv(32→64, 3x3) → BN → ReLU → MaxPool(2)    → 8×8
        Conv(64→128, 3x3) → BN → ReLU → AdaptiveAvgPool → 1×1
        FC(128 → 8)
    
    Parameters: ~100K (very lightweight)
    """
    
    def __init__(self, num_classes=NUM_SCENE_CLASSES):
        super().__init__()
        
        self.features = nn.Sequential(
            # Block 1: 64×64 → 32×32
            nn.Conv2d(1, 16, 3, padding=1),
            nn.BatchNorm2d(16),
            nn.ReLU(inplace=True),
            nn.MaxPool2d(2),
            
            # Block 2: 32×32 → 16×16
            nn.Conv2d(16, 32, 3, padding=1),
            nn.BatchNorm2d(32),
            nn.ReLU(inplace=True),
            nn.MaxPool2d(2),
            
            # Block 3: 16×16 → 8×8
            nn.Conv2d(32, 64, 3, padding=1),
            nn.BatchNorm2d(64),
            nn.ReLU(inplace=True),
            nn.MaxPool2d(2),
            
            # Block 4: 8×8 → 1×1
            nn.Conv2d(64, 128, 3, padding=1),
            nn.BatchNorm2d(128),
            nn.ReLU(inplace=True),
            nn.AdaptiveAvgPool2d(1),
        )
        
        self.classifier = nn.Sequential(
            nn.Dropout(0.3),
            nn.Linear(128, num_classes),
        )
    
    def forward(self, x):
        x = self.features(x)
        x = x.view(x.size(0), -1)
        x = self.classifier(x)
        return x
