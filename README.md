# FLINT Vision Engine & Image Correlation Suite

Welcome to the **FLINT Vision Engine** repository. This repository provides offline-first, foundational AI vision tools for zero-shot image similarity, natural-language semantic search, region-of-interest (crop) correlation, and video keyframe triage.

To support both rapid prototyping and large-scale production deployments, this repository is organized into **two standalone distributions**:

1. **[`flint/`](./flint/) — Lightweight Demo & Reference Framework**
2. **[`image-correlation-suite/`](./image-correlation-suite/) — Enterprise Media Correlation Platform (SYMPICS)**

---

## Which Version Should I Use?

| Feature / Capability | [`flint/`](./flint/) (Demo / Reference SDK) | [`image-correlation-suite/`](./image-correlation-suite/) (Enterprise Platform) |
| :--- | :--- | :--- |
| **Target Use Case** | Evaluation, research, lightweight scripts, and local demos | High-throughput production media archives, multi-case correlation, and team workflows |
| **Infrastructure Required** | Pure Python (No external database required) | PostgreSQL 16 + `pgvector` (HNSW indexing) + CAS Storage Vault |
| **User Interface** | CLI scripts & lightweight demo tool | Full Web Studio UI, REST API, & Read-Only SQL Sandbox (`Port 8080`) |
| **Storage Architecture** | Local folder / flat file paths | 2-Layer Content-Addressed Storage (CAS) Hex Vault (`65,536` buckets) with SHA-256 deduplication |
| **Supported Formats** | Standard images (`.jpg`, `.png`) & video files (`.mp4`) | Standard images, video keyframes, archives (`.zip`, `.tar`), & Camera RAW (`.CR3`, `.CR2`, `.NEF`, `.ARW`, `.DNG`, `.RAF`) |
| **AI Model Execution** | Single-model or script-driven inference | Multi-model ensemble (CLIP + SigLIP + SigLIP-2 NaFlex + DINOv3) with GPU/CPU hardware auto-scaling |
| **Integrity & Auditing** | Basic runtime execution | Simultaneous SHA-256/MD5/SHA-1 streaming, EXIF/GPS extraction, and anti-bit-rot vault scrubbing |

---

## Repository Structure

```text
flint-vision-engine/
├── flint/                         # [DEMO VERSION] Lightweight Python SDK, docs, & standalone examples
│   ├── docs/                      # Model architecture notes and benchmark documentation
│   ├── examples/                  # Standalone scripts (embeddings, text search, crop search, video triage)
│   ├── requirements.txt           # Minimal Python dependencies for the demo framework
│   └── README.md                  # FLINT Demo & SDK documentation
│
├── image-correlation-suite/       # [ENTERPRISE VERSION] Full-stack SYMPICS platform
│   ├── sympics/                   # Core Python package (CAS vault, AI ensemble, DB repos, controllers)
│   ├── database/                  # PostgreSQL + pgvector schemas, initializer, and tuning configs
│   ├── web/                       # Interactive Web Studio UI & REST API server
│   ├── scripts/                   # Intake daemons, parallel migration workers, and offline model downloader
│   ├── launchers/                 # 1-Click Windows batch launchers
│   ├── tests/                     # Automated unit and integration test suite
│   └── README.md                  # Enterprise installation, architecture, and operations guide
│
├── CONTRIBUTING.md                # Contribution guidelines
├── LICENSE                        # Apache 2.0 License
└── README.md                      # Repository overview and navigation guide (this file)
```

---

## Getting Started

> **Important Note on Offline AI Models:**  
> To ensure strict compliance with model provider terms and support air-gapped environments, neither version automatically downloads weights at runtime unless explicitly provisioned. All foundational vision models (such as **CLIP**, **SigLIP-2**, and **DINOv3**) run 100% locally on your hardware.

### Option 1: Running the Lightweight Demo (`flint/`)

Choose [`flint/`](./flint/) if you want to quickly test foundational vision embeddings, run standalone Python examples, or integrate the core inference wrapper into your own scripts without setting up PostgreSQL.

```bash
cd flint
pip install -r requirements.txt
```

* Read the full **[FLINT Demo & SDK Guide (`flint/README.md`)](./flint/README.md)** for model setup and example scripts (`01_compute_embeddings.py` through `04_video_triage.py`).

---

### Option 2: Deploying the Enterprise Suite (`image-correlation-suite/`)

Choose [`image-correlation-suite/`](./image-correlation-suite/) if you are deploying a persistent, scalable media vault with multi-model `pgvector` indexing, automated background ingestion daemons, Camera RAW extraction, and the web-based correlation studio.

```bash
cd image-correlation-suite
pip install -e .
python3 database/init_database.py
python3 web/server.py
```

* Read the full **[Enterprise Platform Guide (`image-correlation-suite/README.md`)](./image-correlation-suite/README.md)** for Windows 1-click setup scripts, air-gapped model provisioning, CAS vault initialization, and architecture details.

---

## License

This project is licensed under the **Apache License, Version 2.0**. See the [LICENSE](./LICENSE) file for details.
