# FLINT Vision Engine - User Guide & Deployment Manual

FLINT Vision Engine is a high-performance, forensic-grade computer vision analysis platform optimized for macOS (Apple Silicon M-series & Intel) with native Metal Performance Shaders (MPS) hardware acceleration. It enables deep visual similarity matching, AI background-removed crop matching, natural language text searching, and fine-grained video keyframe forensic analysis across massive image and video archives.

---

## Table of Contents
1. [System Requirements & Architecture](#1-system-requirements--architecture)
2. [Quickstart: Deploying & Launching](#2-quickstart-deploying--launching)
3. [Foundational Vision Models Setup](#3-foundational-vision-models-setup)
4. [Workspace & Database Management](#4-workspace--database-management)
5. [Loading Known Files (Reference Targets)](#5-loading-known-files-reference-targets)
6. [Loading Unknown Files (Evidence Indexing)](#6-loading-unknown-files-evidence-indexing)
7. [Video Processing & Keyframe Extraction](#7-video-processing--keyframe-extraction)
8. [Matching Against Reference Targets](#8-matching-against-reference-targets)
9. [Targeted Crop Search & AI Background Removal](#9-targeted-crop-search--ai-background-removal)
10. [Natural Language Text String Search](#10-natural-language-text-string-search)
11. [Search Engines: Brute Force (Exact) vs. ANN (Approximate)](#11-search-engines-brute-force-exact-vs-ann-approximate)
12. [Score Aggregation: Max Score vs. Average Score](#12-score-aggregation-max-score-vs-average-score)
13. [Video Match Review Modal & Interactive Real-Time Filtering](#13-video-match-review-modal--interactive-real-time-filtering)
14. [Troubleshooting & Best Practices](#14-troubleshooting--best-practices)

---

## 1. System Requirements & Architecture

- **Operating System**: macOS Monterey (12.0) or later (macOS Sonoma / Sequoia recommended).
- **Architecture**: Apple Silicon (M1, M2, M3, M4 series) or Intel x86_64.
- **Hardware Acceleration**: Automatic Apple Silicon Metal Performance Shaders (`mps`) GPU acceleration with automatic fallback to CPU.
- **Python**: Python 3.10, 3.11, 3.12, or 3.13.
- **System Tools**: `ffmpeg` and `ffprobe` (recommended for high-speed video decoding; if not installed, FLINT automatically falls back to OpenCV).

---

## 2. Quickstart: Deploying & Launching

The deployment package `MacCurrent.zip` contains a clean, zero-database standalone installation.

### Step 1: Unpack the Archive
Unzip the deployment archive to your desired workspace directory:
```bash
unzip MacCurrent.zip
cd flint-vision-engine
```

### Step 2: Launch the Engine
You can start FLINT using the provided shell launcher:
```bash
chmod +x run.sh
./run.sh
```
Or directly using Python:
```bash
python3 app.py
```
To run on a custom port or listen on all network interfaces:
```bash
python3 app.py 8080 --host 0.0.0.0
```

### What `./run.sh` Does Automatically:
1. Checks for Python 3.10+ and verifies environment health.
2. Initializes an isolated local virtual environment (`.venv`) if one does not exist.
3. Automatically installs required dependencies (`torch`, `torchvision`, `transformers`, `opencv-python`, `pillow`, `scipy`, etc.).
4. Detects Apple Silicon hardware and binds PyTorch to `mps` (Metal) acceleration.
5. Launches the built-in HTTP server and displays the local UI link:
   ```
   🚀 FLINT Vision Engine listening on http://127.0.0.1:8080
   ```
Open **`http://127.0.0.1:8080`** in Safari, Chrome, or Firefox to access the UI.

---

## 3. Foundational Vision Models Setup

FLINT supports multiple vision model backends. Models are stored locally in the `models/` folder and operate completely offline once cached.

| Model Identifier | Architecture | Dimension | Primary Use Case |
| :--- | :--- | :--- | :--- |
| **`clip-vit-b-32`** *(Default)* | OpenAI CLIP ViT-B/32 | 512 | Fast general similarity, text search, high throughput. |
| **`siglip-base`** | Google SigLIP Base Patch16 | 768 | Superior semantic quality and multilingual text/image alignment. |
| **`siglip2-naflex`** | Google SigLIP 2 NaFlex | 768 | **Native Aspect Ratio** support; ideal for non-square crops and forensic detail. |
| **`dinov3`** | Meta DINOv3 Dense Patch | 1024 | Self-supervised structural correspondence, texture, and copy-move detection. |
| **`clip-vit-large`** | OpenAI CLIP ViT-L/14 | 768 | High-capacity representation for fine-grained classification. |

### Managing Models in the Web UI:
1. Navigate to the **Settings** tab (gear icon in the navigation bar).
2. Under **Foundational Models**, view the status of each model (`Ready`, `Not Downloaded`, or `Active`).
3. Click **Download / Activate** next to your desired model. If the model requires an authenticated HuggingFace token, enter it in the token prompt field.
4. Switching models is instantaneous once downloaded. All embeddings are keyed by model name in SQLite, allowing you to index and compare across multiple models within the same database.

---

## 4. Workspace & Database Management

FLINT utilizes clean, modular SQLite database archives. Each database stores file records, extracted keyframes, metadata hashes, and multi-model embedding vectors.

### Creating and Switching Databases:
1. In the sidebar or top navigation, click the **Database Archives** badge or menu.
2. **Create New Archive**: Enter a name (e.g., `Case_2026_Robbery`, `Surveillance_LotB`) and click **Create & Activate**.
3. **Switch Archives**: Select an existing `.sqlite` database from the dropdown to immediately switch contexts.
4. **Clean Baseline**: The deployment starts with an empty `databases/default.sqlite`. No evidence or paths from previous systems are included.

---

## 5. Loading Known Files (Reference Targets)

Reference targets represent the known subjects of interest (e.g., a specific suspect, weapon, stolen vehicle, piece of jewelry, or brand logo).

### Adding Targets:
1. Go to the **Known Targets** / **Reference** panel.
2. Click **Add Target Image** or drag and drop reference images into the upload zone.
3. Provide an optional **Target Label** (e.g., `Suspect Blue Jacket`, `Vehicle Red Sedan`).
4. Assign to a **Target Group** (e.g., `Suspects`, `Vehicles`, `Stolen Items`). Target groups allow you to match evidence against an entire group simultaneously.
5. Targets are saved in SQLite with their individual embedding vectors computed by the active model.

---

## 6. Loading Unknown Files (Evidence Indexing)

Unknown files constitute your pool of unvetted evidence (folders containing thousands of photos, surveillance camera dumps, drone footage, or bodycam videos).

### Indexing an Evidence Directory:
1. In the **Evidence Indexing** section, enter the absolute folder path to your media directory (e.g., `/Volumes/EvidenceDrive/CaseData/CCTV`).
2. Click **Index Directory**.
3. The engine recursively scans the directory for all supported media:
   - **Images**: `.jpg`, `.jpeg`, `.png`, `.webp`, `.bmp`, `.tiff`, `.heic`
   - **Videos**: `.mp4`, `.mov`, `.avi`, `.mkv`, `.wmv`, `.webm`, `.m4v`
4. **Smart Deduplication & Caching**: FLINT checks SHA-256 and modification timestamps. Files already indexed in SQLite are skipped instantly in `0.00s`.
5. Embeddings for newly discovered files and video keyframes are calculated using Apple Silicon GPU acceleration and written to the active database.

---

## 7. Video Processing & Keyframe Extraction

Videos cannot be effectively matched as a single monolithic file; FLINT breaks videos down into forensically meaningful keyframes.

### Extraction Modes (Configured in Settings):
1. **SSIM (Structural Similarity Index) Change Detection** *(Recommended)*:
   - Evaluates frame-to-frame perceptual differences.
   - Extracts a keyframe whenever the scene changes significantly (e.g. camera pan, subject enters frame, cut/edit).
   - Prevents redundant keyframes during static scenes, drastically reducing storage and search overhead.
2. **Uniform Interval Sampling**:
   - Extracts 1 frame every *N* seconds (e.g., 1 frame per 1.0 second).
3. **Fixed Count Sampling**:
   - Uniformly samples a predetermined number of frames (e.g., 50 frames distributed evenly) across the video duration.

Keyframe images are saved under `flint_keyframes/<hash>/` and timestamped in SQLite down to millisecond precision.

---

## 8. Matching Against Reference Targets

To find where your known targets appear in your unknown evidence:

1. Select **Visual Similarity Search** from the main dashboard.
2. Choose your query mode:
   - **Single Reference Target**: Match against one specific known image.
   - **Target Group**: Match against all images belonging to a group (e.g. all angles of a suspect).
   - **Direct Query Image**: Upload a one-off query image from your local drive.
3. Configure **Threshold**: Set the minimum similarity cutoff (e.g., `40%` or `0.40`).
4. Click **Run Match Search**.
5. Results appear ranked by confidence score, showing matched images and videos.

---

## 9. Targeted Crop Search & AI Background Removal

Standard whole-image embeddings can be polluted by irrelevant backgrounds (e.g. matching the background trees rather than the suspect's backpack). Crop Search solves this:

1. Select or upload an image in **Crop Search**.
2. **Draw Bounding Box**: Click and drag over the region of interest (e.g., an emblem on a shirt, a license plate, a shoe).
3. **AI Background Removal**: Toggle **"Remove Background"** to run automated subject isolation on the crop before embedding generation.
4. **Instant Vector Query**: FLINT immediately queries the active SQLite database vectors directly—no lengthy directory re-indexing required.
5. Supports aspect-ratio preserving models (`siglip2-naflex`) for maximum precision on tall or wide crops.

---

## 10. Natural Language Text String Search

FLINT's multimodal vision-language models allow you to search visual evidence using descriptive text prompts without needing any manual tagging or metadata.

1. Select **Text Search** in the query bar.
2. Enter descriptive queries such as:
   - `"red delivery van with roof rack"`
   - `"person wearing neon yellow construction vest"`
   - `"night surveillance footage person climbing fence"`
   - `"handgun on table"`
3. The engine encodes the text query into the shared multimodal embedding space using the active foundational model.
4. Returns all images and video keyframes whose visual contents match the semantic meaning of your text query, ranked by cosine similarity.

---

## 11. Search Engines: Brute Force (Exact) vs. ANN (Approximate)

FLINT offers two search backend modes selectable in the Search Configuration:

### Brute Force (Exact Flat Search):
- **How it works**: Computes the exact cosine similarity between the query vector and every single indexed vector in the database using vectorized linear algebra.
- **Accuracy**: **100% mathematical precision**. Zero false negatives due to algorithmic approximation.
- **When to use**: Highly recommended for forensic analysis, court evidence preparation, and datasets under 500,000 vectors. On Apple Silicon M-series hardware, FLINT can scan 100,000 vectors in under 50 milliseconds.

### ANN (Approximate Nearest Neighbors - HNSW):
- **How it works**: Traverses a Hierarchical Navigable Small World (HNSW) graph index to find nearest neighbors in logarithmic time `O(log N)`.
- **Accuracy**: Typically 95-99% recall depending on graph density (`M` and `efSearch` parameters).
- **When to use**: High-throughput searching across multi-million item archives where sub-second latency is required.

---

## 12. Score Aggregation: Max Score vs. Average Score

When matching evidence that contains multiple vectors—such as a video with 100 keyframes or a target group containing 5 reference photos—how should the overall match score be calculated?

### Max Score *(Forensic Default)*:
- Takes the **highest individual score** achieved across all keyframes or group members:
  $$	ext{Score}_{	ext{Video}} = \max(\{S_1, S_2, \dots, S_n\})$$
- **Why it matters**: If a suspect appears for only 2 seconds during a 2-hour video, the average similarity over the entire video would be less than 5%, hiding the match. **Max Score** ensures that high-confidence 2-second detection brings the video straight to the top of your results.

### Average Score:
- Computes the **arithmetic mean** of scores across all keyframes or group items:
  $$	ext{Score}_{	ext{Video}} = rac{1}{n}\sum_{i=1}^n S_i$$
- **Why it matters**: Useful for general scene similarity or detecting continuous, sustained presence throughout an entire video.

---

## 13. Video Match Review Modal & Interactive Real-Time Filtering

Whenever a video matches your search criteria, clicking the video result opens the **Video Match Review Modal**:

1. **Synchronized Video Player**:
   - Watch the video with full scrubbing and playback controls.
   - Jump directly to any matched keyframe by clicking its timestamp pill (e.g. `00:01:24.400`).
2. **Multi-Target Breakdown**:
   - When searching across multiple targets or target groups, the modal displays each known reference image side-by-side with its best matching video frame.
   - Shows the exact keyframe timestamp, similarity percentage, and target label.
3. **Interactive Threshold Slider**:
   - Adjust the real-time threshold slider (from `0%` to `100%`) directly inside the modal.
   - Keyframes below the threshold are instantly filtered out, letting you tune confidence on the fly without re-running the global search.
   - Quick preset buttons: **30%**, **40% (Default)**, **50%**, **60%**, **75%**.
4. **Full Keyframe Gallery**:
   - Scroll through all matching frames extracted from the video.
   - Inspect individual keyframe images at full resolution.

---

## 14. Troubleshooting & Best Practices

- **Port Conflict**: If port `8080` is already in use, launch on another port:
  ```bash
  python3 app.py 9000
  ```
- **Clearing a Search**: Click "Clear Filters" or reset the threshold slider to view all indexed media.
- **Hardware Acceleration Check**: Check the server log upon startup:
  ```
  [INFO] Active Model: clip-vit-b-32 | Acceleration: MPS
  ```
  If `MPS` appears, Apple Silicon GPU acceleration is fully active.
- **Offline Environments**: Download your required models while connected to the internet. Once cached in `models/`, FLINT runs with zero internet connectivity.
