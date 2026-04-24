# Vision Module Execution Guide

This guide provides step-by-step instructions on how to set up and run the Computer Vision (CV) module for the Smart Helmet Navigation system.

---

## 1. Prerequisites

Ensure you have Python 3.8+ installed. It is recommended to use a virtual environment.

### Install Dependencies
Install the required machine learning and web service libraries:

```bash
# From the localization/CV directory
pip install -r requirements.txt

# Additional service dependencies
pip install fastapi uvicorn pydantic httpx python-multipart
```

---

## 2. Model Preparation

The vision module requires two pre-trained models to be present in the `localization/CV/models/` directory:

1.  **`best.pth`**: The primary LRASPP segmentation model.
2.  **`scene_classifier.pth`**: The secondary CNN for junction and sharp turn detection.

If these are not present, you may need to download them or run the training scripts (`train.py` and `train_scene_classifier.py`).

---

## 3. Running the Vision Service (FastAPI)

The main way to run the vision module as part of the integrated helmet system is via the FastAPI microservice.

### Start the Service
Run the following command from the `localization/CV` directory:

```bash
python3 main.py
```

*   **Port:** 8001
*   **Video Source:** By default, it uses `sample_drive.mp4`.
*   **API Endpoints:**
    *   `POST /api/localization/control`: Start/Stop the inference loop.
    *   `POST /api/localization/nav-hint`: Receive hints from the Navigation module.

---

## 4. Running Standalone Analysis (CLI)

You can also run the vision module in standalone mode for testing and debugging.

### A. Analyze a Single Image
```bash
python3 scene_analyzer.py --image path/to/your_frame.jpg
```

### B. Analyze a Folder of Images (Batch Processing)
```bash
python3 scene_analyzer.py --folder path/to/images --out-dir output_folder
```

### C. Live Webcam Analysis
```bash
python3 scene_analyzer.py --webcam
```

---

## 5. Integration with Navigation

When the `main.py` service is running, it will automatically attempt to send **Visual Events** to the Navigation module at:
`http://localhost:8000/api/navigation/localization/visual-event`

Ensure the **Navigation Server** is running on port 8000 for full end-to-end integration:

```bash
# In the navigation directory
python3 server.py
```

---

## 6. Troubleshooting

*   **CUDA/MPS Errors:** The code automatically detects Apple Silicon (MPS) or CUDA. If you encounter errors, check if your PyTorch installation supports your hardware.
*   **Missing Video:** Ensure `sample_drive.mp4` is present in the `localization/CV` folder before running `main.py`.
*   **Port Conflicts:** If port 8001 is in use, change the `PORT` variable in `main.py`.
