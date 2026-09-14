<!--
Copyright 2026 Google LLC

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
-->

# Search Backends & Score Aggregation Architecture

## 1. Search Backends: Brute Force (Exact) vs. Approximate Nearest Neighbors (ANN)

Querying an archive evaluates similarity between query vector `q ∈ ℝᵈ` and stored media matrix `X ∈ ℝᴺˣᵈ`. FLINT provides two complementary execution backends:

### Brute Force Matching (Exact Search)
Brute Force performs an exhaustive linear scan across the entire contiguous embedding matrix `X`.
* **Algorithmic Mechanism**: Executes a single Level-3 BLAS matrix-vector product (`s = X · qᵀ`). Hardware-accelerated across GPU tensor cores and vectorized AVX-512 CPU execution units.
* **100% Absolute Recall**: Evaluates every stored record without heuristic pruning. Guarantees zero false negatives due to algorithmic approximation.
* **Deterministic Defensibility**: Essential for audits, verification pipelines, and scientific rigor where probabilistic omissions cannot be tolerated.
* **Performance Profile**: Scanning 100,000 768-dimensional vectors completes in under 15 ms. Recommended as default for repositories under 500,000 files.

### Approximate Nearest Neighbors (ANN via Clustered IVF)
For multi-million-record archives requiring sub-10 ms latency, FLINT implements a Clustered Inverted File (`FlintANNIndex`) architecture.
* **IVF Cluster Scaling Formula**: Rather than hardcoding fixed caps, cluster count `k` scales dynamically with repository volume `N`:
  * `k = clip(4√N, 16, 4096)`
  * `n_probe = clip(⌊√k⌋, 1, 64)`
* **Scalability Analysis**: In a 1,000,000-image repository, hardcoding `k = 128` leaves ~7,812 vectors per cluster, forcing a multi-probe of 42 clusters to scan >320,000 vectors (32% of the database). With `k = 4096`, each bucket averages ~244 vectors; probing `n_probe = 64` inspects just 15,616 vectors—evaluating **1.56%** of the database (pruning **98.44%**) while sustaining >98% recall.
* **Multi-Probe Candidate Retrieval**: Identifies the `n_probe` nearest centroids to query `q`, concatenates candidate IDs from those posting lists, and runs exact matrix multiplication exclusively across that subset.

**Example (Pocket Classifiers)**: Complex activity and demographic recognition typically requires massive labeled training datasets. With FLINT, a user selects a small seed set of representative images (e.g., an elderly person pitching a baseball) to establish a localized vector cluster. The vision backbone naturally isolates subtle postures, age markers, and contextual cues, allowing zero-shot retrieval to separate the target subset from lookalikes without bespoke classifier training.

---

## 2. Score Aggregation: Max Matching vs. Average Matching

Visual triage frequently involves entities represented by **multiple feature vectors** rather than isolated pairs:
* **Temporal Dimension (Video Keyframe Sequences)**: Aggregating scores across dozens or hundreds of extracted video keyframes.
* **Spatial Dimension (Dense Patch & Sub-Region Analysis)**: Isolating localized sub-regions within an image (e.g., finding a coffee mug on a breakfast counter).
* **Perspective Dimension (Multi-Target Seed Sets)**: Querying against a target group of multiple reference images (e.g., an object captured under varying angles and lighting).

### Spatial Max Matching vs. Global Scene Averaging
Consider an unindexed photo of a kitchen counter set for breakfast: laden with pancakes, fruit bowls, juice glasses, and a specific blue ceramic mug. A user seeks this mug using a reference seed image taken of that same mug inside a dishwasher.
* **The Failure of Global Image Similarity**: Computing a global embedding for both images yields low cosine similarity (~34%). The counter photo is dominated by pancakes and fruit, while the seed photo is dominated by dishwasher racks. Global pooling averages out localized signals, causing the image to be missed.
* **The Power of Spatial Max Matching**: Decomposing the candidate image into localized sub-regions or dense patch tokens `p_s`:
  `Score_SpatialMax = max_{s ∈ {patches}} sim(q_mug, p_s)`
  The spatial max operator isolates the patch containing the mug, registering a 91% match while ignoring surrounding clutter.

### Mathematical Formulations & Operational Profiles
* **Max Score Matching (Peak Detection)**:
  `Score_Max = max_{j ∈ {1, ..., M}} sim(q_j, d_i)`
  *The "Needle in a Haystack" Principle*: If an object appears for 2 seconds in a 2-hour video, average matching dilutes the score near zero. Max matching isolates the peak frame, surfacing the file immediately.
* **Average Score Matching (Consensus & Sustained Presence)**:
  `Score_Avg = (1 / M) ∑_{j=1}^M sim(q_j, d_i)`
  *The "Continuous Presence" Principle*: Quantifies whether an environmental motif or theme persists throughout a clip, functioning as an outlier filter against brief transient false positives.

### Comparison Matrix

| Characteristic | Max Matching (`max`) | Average Matching (`mean`) |
| :--- | :--- | :--- |
| **Mathematical Objective** | Identifies peak instantaneous similarity | Identifies sustained visual consensus |
| **Spatial Application** | Isolates small objects in cluttered scenes | Evaluates full-image scene classification |
| **Video Application** | Detects fleeting appearances (1-2s events) | Verifies continuous setting / clip theme |
| **Multi-Target Query** | Matches if **any** reference target aligns | Requires alignment across **all** targets |
| **False Negative Risk** | Extremely Low (avoids background dilution) | High for transient or localized targets |
