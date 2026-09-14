#!/usr/bin/env python3
# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

# Copyright 2026 Google LLC
# Licensed under Apache 2.0

import argparse
import json
import os
import sys
import webbrowser

from flint.service import FlintService
from flint.web.server import run_server


def main():
  parser = argparse.ArgumentParser(
      description="FLINT Vision Engine - Edge-native multimodal visual similarity and triage system."
  )
  parser.add_argument(
      "--db",
      default="flint_database.sqlite",
      help="Path to SQLite vector database file (default: flint_database.sqlite)",
  )
  parser.add_argument(
      "--models-dir",
      default="models",
      help="Path to local models directory (default: ./models)",
  )
  parser.add_argument(
      "--model",
      default="clip-vit-b-32",
      help="Model to use (clip-vit-b-32, siglip-base, siglip2-base, siglip2-naflex, mobileclip, dinov3)",
  )

  subparsers = parser.add_subparsers(dest="command", help="Available subcommands")

  # 1. Visual Matcher
  p_vis = subparsers.add_parser("visual", help="Search unknown images/archive against known reference photo(s)")
  p_vis.add_argument("-k", "--known", required=True, help="Path to 1 known image or a directory of known reference images")
  p_vis.add_argument("-u", "--unknown", default=None, help="Path to directory of unknown images to search (or None to search full SQLite DB)")
  p_vis.add_argument("-t", "--threshold", type=float, default=0.0, help="Similarity threshold (0.0 to 1.0, default: 0.0, show all)")
  p_vis.add_argument("-m", "--metric", choices=["cosine", "dot", "euclidean"], default="cosine", help="Distance metric")
  p_vis.add_argument("-a", "--aggregation", choices=["max", "mean"], default="max", help="Aggregation for multiple known targets")
  p_vis.add_argument("--top-k", type=int, default=50, help="Max results to return (default: 50)")
  p_vis.add_argument("--no-recursive", action="store_true", help="Do not search subdirectories recursively")
  p_vis.add_argument("--no-videos", action="store_true", help="Skip processing video files in the unknown folder")
  p_vis.add_argument("--video-method", choices=["ssim", "interval", "uniform"], default="ssim", help="Keyframing method for videos")
  p_vis.add_argument("--video-interval", type=float, default=1.0, help="Time interval in seconds when using interval method (default: 1.0)")
  p_vis.add_argument("--video-ssim", type=float, default=0.65, help="SSIM sensitivity when using ssim method (default: 0.65)")
  p_vis.add_argument("--video-uniform", type=int, default=10, help="Number of frames when using uniform method (default: 10)")
  p_vis.add_argument("-o", "--output", default=None, help="Save report to file (.html, .csv, or .json)")

  # 2. Text Search
  p_text = subparsers.add_parser("text", help="Zero-shot natural language text-to-image search")
  p_text.add_argument("-q", "--query", required=True, help="Text query (e.g. 'red sports car', 'person with sunglasses')")
  p_text.add_argument("-u", "--unknown", default=None, help="Path to unknown directory (or None for full SQLite DB)")
  p_text.add_argument("-t", "--threshold", type=float, default=0.0, help="Similarity threshold (default: 0.0, show all)")
  p_text.add_argument("-o", "--output", default=None, help="Save report to file (.html, .csv, or .json)")

  # 3. Crop Search
  p_crop = subparsers.add_parser("crop", help="Targeted crop search with bounding box")
  p_crop.add_argument("-i", "--image", required=True, help="Source image path")
  p_crop.add_argument("-b", "--box", required=True, help="Bounding box coordinates 'x1,y1,x2,y2' (left, top, right, bottom)")
  p_crop.add_argument("-u", "--unknown", default=None, help="Path to unknown directory (or None for full SQLite DB)")
  p_crop.add_argument("-t", "--threshold", type=float, default=0.0, help="Similarity threshold (default: 0.0, show all)")
  p_crop.add_argument("-o", "--output", default=None, help="Save report to file (.html, .csv, or .json)")

  # 4. Video Triage
  p_vid = subparsers.add_parser("video", help="Extract keyframes and triage video against targets")
  p_vid.add_argument("-v", "--video", required=True, help="Video file path (.mp4, .mov, etc.)")
  p_vid.add_argument("-k", "--targets", required=True, help="Path to target image(s) or folder")
  p_vid.add_argument("--method", choices=["ssim", "interval", "uniform"], default="ssim", help="Keyframe extraction method")
  p_vid.add_argument("--interval", type=float, default=1.0, help="Time interval in seconds (default: 1.0)")
  p_vid.add_argument("--ssim", type=float, default=0.65, help="SSIM scene sensitivity (default: 0.65)")
  p_vid.add_argument("--uniform", type=int, default=10, help="Uniform frame count (default: 10)")
  p_vid.add_argument("-t", "--threshold", type=float, default=0.0, help="Target match similarity threshold (default: 0.0, show all)")
  p_vid.add_argument("-o", "--output", default=None, help="Save report to file (.html, .csv, or .json)")

  # 5. Index
  p_idx = subparsers.add_parser("index", help="Index a folder of media into the SQLite database")
  p_idx.add_argument("-f", "--folder", required=True, help="Folder path to index")
  p_idx.add_argument("--no-recursive", action="store_true", help="Do not index subdirectories")
  p_idx.add_argument("--no-videos", action="store_true", help="Skip video files")
  p_idx.add_argument("--video-method", choices=["ssim", "interval", "uniform"], default="ssim")
  p_idx.add_argument("--video-interval", type=float, default=1.0)
  p_idx.add_argument("--video-ssim", type=float, default=0.65)

  # 6. Database Stats
  subparsers.add_parser("stats", help="Show SQLite database media and vector statistics")

  # 7. Model Download
  p_dl = subparsers.add_parser("download", help="Download model weights locally from Hugging Face")
  p_dl.add_argument("--model", required=True, help="Model key (e.g. clip-vit-b-32, siglip-base, siglip2-naflex)")

  # 8. Web Server
  p_serve = subparsers.add_parser("serve", help="Launch the interactive Web UI")
  p_serve.add_argument("--host", default="127.0.0.1", help="Host to bind (default: 127.0.0.1)")
  p_serve.add_argument("--port", type=int, default=8080, help="Port to bind (default: 8080)")
  p_serve.add_argument("--no-open", action="store_true", help="Do not automatically open browser")

  args = parser.parse_args()

  if not args.command or args.command == "serve":
    host = getattr(args, "host", "127.0.0.1")
    port = getattr(args, "port", 8080)
    should_open = not getattr(args, "no_open", False)
    if should_open:
      try:
        webbrowser.open(f"http://{host}:{port}")
      except Exception:
        pass
    run_server(host=host, port=port, models_dir=args.models_dir, db_path=args.db)
    return

  service = FlintService(models_dir=args.models_dir, db_path=args.db, default_model=args.model)

  if args.command == "stats":
    stats = service.db.get_stats()
    print("==================================================")
    print("FLINT SQLite Database Statistics:")
    print("==================================================")
    for k, v in stats.items():
      print(f"  {k:20s}: {v}")
    print("==================================================")
    return

  if args.command == "download":
    from huggingface_hub import snapshot_download
    models = {m['key']: m for m in service.list_available_models()}
    if args.model not in models:
      print(f"Error: Unknown model '{args.model}'. Available: {list(models.keys())}")
      return
    cfg = models[args.model]
    print(f"Downloading {cfg['repo_id']} to {cfg['local_path']}...")
    snapshot_download(cfg['repo_id'], local_dir=cfg['local_path'])
    print("Download complete!")
    return

  if args.command == "index":
    print(f"Indexing media from {args.folder} into SQLite...")
    res = service.db.index_folder(
        args.folder,
        service.get_engine(),
        recursive=not args.no_recursive,
        include_videos=not args.no_videos,
        video_method=args.video_method,
        video_ssim_threshold=args.video_ssim,
        video_interval_seconds=args.video_interval,
        progress_callback=lambda p: print(f"  {p.get('status', '')}", end="\r"),
    )
    print(f"\nIndexing finished! Total: {res['total_files']} | Indexed: {res['indexed']} | Skipped: {res['skipped']}")
    return

  if args.command == "visual":
    print(f"Running Visual Similarity Search with model '{service.active_model_key}'...")
    res = service.search_known_vs_unknown(
        known_input=args.known,
        unknown_folder=args.unknown,
        threshold=args.threshold,
        metric=args.metric,
        aggregation=args.aggregation,
        top_k=args.top_k,
        recursive=not args.no_recursive,
        include_videos=not args.no_videos,
        video_method=args.video_method,
        video_ssim_threshold=args.video_ssim,
        video_interval_seconds=args.video_interval,
        video_uniform_count=args.video_uniform,
    )
    matches = res.get("matches", [])
    print(f"\nFound {len(matches)} matches in {res['duration_ms']} ms:")
    print("--------------------------------------------------------------------------------")
    for i, m in enumerate(matches, 1):
      score_pct = m.get('similarity_pct', round(m.get('score', 0) * 100, 2))
      target = f" (Matched: {m.get('best_target_label')})" if m.get('best_target_label') else ""
      print(f"[{i:02d}] {score_pct:6.2f}% | {m['file_path']}{target}")
    print("--------------------------------------------------------------------------------")

    if args.output:
      ext = os.path.splitext(args.output)[1].lower().lstrip(".") or "html"
      out_f = service.export_report(res, export_format=ext, output_path=args.output)
      print(f"Saved results report to: {out_f}")
    return

  if args.command == "text":
    print(f"Searching for text query: '{args.query}'...")
    res = service.search_text(
        query=args.query,
        unknown_folder=args.unknown,
        threshold=args.threshold,
    )
    matches = res.get("matches", [])
    print(f"\nFound {len(matches)} matches in {res['duration_ms']} ms:")
    for i, m in enumerate(matches, 1):
      score_pct = m.get('similarity_pct', round(m.get('score', 0) * 100, 2))
      print(f"[{i:02d}] {score_pct:6.2f}% | {m['file_path']}")

    if args.output:
      ext = os.path.splitext(args.output)[1].lower().lstrip(".") or "html"
      out_f = service.export_report(res, export_format=ext, output_path=args.output)
      print(f"Saved results to: {out_f}")
    return

  if args.command == "crop":
    box = tuple(int(x.strip()) for x in args.box.split(","))
    print(f"Searching for crop from '{args.image}' box={box}...")
    res = service.search_crop(
        image_path=args.image,
        bounding_box=box,
        unknown_folder=args.unknown,
        threshold=args.threshold,
    )
    matches = res.get("matches", [])
    print(f"\nFound {len(matches)} matches in {res['duration_ms']} ms:")
    for i, m in enumerate(matches, 1):
      score_pct = m.get('similarity_pct', round(m.get('score', 0) * 100, 2))
      print(f"[{i:02d}] {score_pct:6.2f}% | {m['file_path']}")

    if args.output:
      ext = os.path.splitext(args.output)[1].lower().lstrip(".") or "html"
      out_f = service.export_report(res, export_format=ext, output_path=args.output)
      print(f"Saved results to: {out_f}")
    return

  if args.command == "video":
    print(f"Triaging video '{args.video}' against targets '{args.targets}' using {args.method}...")
    res = service.triage_video(
        video_path=args.video,
        targets_input=args.targets,
        method=args.method,
        ssim_threshold=args.ssim,
        interval_seconds=args.interval,
        uniform_count=args.uniform,
        similarity_threshold=args.threshold,
    )
    events = res.get("events", [])
    print(f"\nDetected {len(events)} events in video ({res['keyframes_extracted']} keyframes indexed):")
    for i, ev in enumerate(events, 1):
      score_pct = ev.get('similarity_pct', round(ev.get('score', 0) * 100, 2))
      print(f"[{i:02d}] Timestamp: {ev['timestamp_seconds']:6.2f}s | {score_pct:6.2f}% match to '{ev['best_target_label']}' | Keyframe: {ev['file_path']}")

    if args.output:
      ext = os.path.splitext(args.output)[1].lower().lstrip(".") or "html"
      out_f = service.export_report(res, export_format=ext, output_path=args.output)
      print(f"Saved triage report to: {out_f}")
    return


if __name__ == "__main__":
  main()
