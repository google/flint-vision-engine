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

"""Main entry point to launch the FLINT Vision Engine interactive Web UI."""

import os
import socket
import sys
import webbrowser

# On Windows, configure console output to UTF-8 and enable ANSI escape codes
if sys.platform == "win32":
  if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
  if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
  try:
    os.system("")  # Enables VT100 / ANSI escape processing on Windows cmd
  except Exception:
    pass


def ensure_pip():
  """Ensures pip is installed and functioning for sys.executable before any install is attempted."""
  import subprocess
  import shutil

  # Refresh user site-packages into sys.path
  import site
  if hasattr(site, "getusersitepackages"):
    user_site = site.getusersitepackages()
    if user_site not in sys.path and os.path.exists(user_site):
      sys.path.insert(0, user_site)

  try:
    subprocess.check_call([sys.executable, "-m", "pip", "--version"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return True
  except Exception:
    pass

  print("📦 'pip' is not detected for Python interpreter:", sys.executable)
  print("⚡ Automatically bootstrapping pip before installing dependencies...")

  # 1. On Linux, automatically install system packages (python3-pip, python3-venv, etc.)
  if sys.platform.startswith("linux"):
    try:
      py_ver = f"{sys.version_info.major}.{sys.version_info.minor}"
      if shutil.which("apt-get"):
        print("⚡ Installing system packages (python3-pip, python3-venv) via apt-get...")
        pkgs = ["python3-pip", "python3-venv", f"python{py_ver}-venv", "python3-full"]
        if shutil.which("sudo"):
          res = subprocess.run(["sudo", "apt-get", "install", "-y", *pkgs], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=60)
          if res.returncode != 0:
            subprocess.run(["sudo", "apt-get", "update", "-y"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=60)
            subprocess.run(["sudo", "apt-get", "install", "-y", *pkgs], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=120)
        else:
          res = subprocess.run(["apt-get", "install", "-y", *pkgs], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=60)
          if res.returncode != 0:
            subprocess.run(["apt-get", "update", "-y"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=60)
            subprocess.run(["apt-get", "install", "-y", *pkgs], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=120)
    except Exception:
      pass

    try:
      subprocess.check_call([sys.executable, "-m", "pip", "--version"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
      print("✅ Initialized pip via system packages.")
      return True
    except Exception:
      pass

  # 2. Try python built-in ensurepip
  try:
    subprocess.check_call([sys.executable, "-m", "ensurepip", "--default-pip"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.check_call([sys.executable, "-m", "pip", "--version"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    print("✅ Initialized pip via ensurepip.")
    return True
  except Exception:
    pass

  # 3. Try bundled get-pip.py or fetch from PyPA
  import tempfile
  tmp_script = None
  try:
    local_get_pip = os.path.join(os.path.dirname(os.path.abspath(__file__)), "get-pip.py")
    if os.path.exists(local_get_pip):
      script_to_run = local_get_pip
    else:
      import urllib.request
      print("⬇️ Fetching official PyPA get-pip.py bootstrap script...")
      with tempfile.NamedTemporaryFile(suffix=".py", delete=False) as tf:
        tmp_script = tf.name
      script_to_run = tmp_script
      req = urllib.request.Request("https://bootstrap.pypa.io/get-pip.py", headers={"User-Agent": "Mozilla/5.0"})
      with urllib.request.urlopen(req, timeout=15) as resp:
        with open(tmp_script, "wb") as f:
          f.write(resp.read())

    # Try install with fallback flags (including PEP 668 bypass --break-system-packages)
    flag_combos = [
        ["--user", "--break-system-packages", "--no-warn-script-location"],
        ["--break-system-packages", "--no-warn-script-location"],
        ["--no-warn-script-location"],
        ["--user", "--no-warn-script-location"],
        ["--user"],
        [],
    ]
    for flags in flag_combos:
      try:
        subprocess.check_call([sys.executable, script_to_run, *flags], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if hasattr(site, "getusersitepackages"):
          user_site = site.getusersitepackages()
          if user_site not in sys.path and os.path.exists(user_site):
            sys.path.insert(0, user_site)
        subprocess.check_call([sys.executable, "-m", "pip", "--version"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        print("✅ Successfully bootstrapped pip.")
        return True
      except Exception:
        continue

  except Exception as e:
    print(f"⚠️ Automatic pip bootstrap was unable to complete: {e}")
  finally:
    if tmp_script and os.path.exists(tmp_script):
      try:
        os.remove(tmp_script)
      except Exception:
        pass

  return False


def ensure_dependencies():
  """Checks and automatically attempts to install required pip packages if missing."""
  import site
  import importlib.util
  if hasattr(site, "getusersitepackages"):
    user_site = site.getusersitepackages()
    if user_site not in sys.path and os.path.exists(user_site):
      sys.path.insert(0, user_site)

  required_pkgs = [
      ("torch", "torch"),
      ("torchvision", "torchvision"),
      ("transformers", "transformers"),
      ("huggingface_hub", "huggingface_hub"),
      ("PIL", "Pillow"),
      ("pillow_heif", "pillow-heif"),
      ("cv2", "opencv-python-headless"),
      ("sklearn", "scikit-learn"),
  ]
  missing_pip = []
  for mod, pkg in required_pkgs:
    try:
      spec = importlib.util.find_spec(mod)
      if spec is None:
        missing_pip.append(pkg)
    except Exception:
      missing_pip.append(pkg)

  if not missing_pip:
    return

  # Automatically bootstrap pip BEFORE attempting pip install
  ensure_pip()

  print(f"📦 Installing required dependencies via pip: {', '.join(missing_pip)}...")
  import subprocess

  in_venv = (sys.prefix != getattr(sys, "base_prefix", sys.prefix))
  base_flags = ["--retries", "5", "--timeout", "60", "--no-warn-script-location"]

  # If torch or torchvision is missing, install torch pre-requisites first to avoid index issues with cuda-toolkit
  if "torch" in missing_pip or "torchvision" in missing_pip:
    pre_reqs = ["filelock", "typing-extensions", "sympy", "networkx", "jinja2", "fsspec", "mpmath"]
    try:
      subprocess.run([sys.executable, "-m", "pip", "install", *base_flags, *pre_reqs], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
      pass

    # Attempt torch install: CPU index first, or --no-deps fallback to bypass 403 cuda-toolkit wheel
    torch_attempts = [
        [sys.executable, "-m", "pip", "install", *base_flags, "torch", "torchvision", "--extra-index-url", "https://download.pytorch.org/whl/cpu"],
        [sys.executable, "-m", "pip", "install", *base_flags, "--no-deps", "torch", "torchvision"],
        [sys.executable, "-m", "pip", "install", *base_flags, "torch", "torchvision"],
    ]
    for cmd in torch_attempts:
      try:
        res = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if res.returncode == 0:
          break
      except Exception:
        continue

  # Only install packages that are actually missing rather than forcing full requirements.txt,
  # preventing Windows [WinError 5] file lock collisions on already installed C-extensions (like cv2.pyd).
  target_args = missing_pip

  install_attempts = []
  if in_venv:
    install_attempts.append([sys.executable, "-m", "pip", "install", *base_flags, *target_args])
    install_attempts.append([sys.executable, "-m", "pip", "install", *base_flags, *target_args, "--break-system-packages"])
  else:
    install_attempts.append([sys.executable, "-m", "pip", "install", *base_flags, *target_args, "--break-system-packages"])
    install_attempts.append([sys.executable, "-m", "pip", "install", *base_flags, *target_args, "--user", "--break-system-packages"])
    install_attempts.append([sys.executable, "-m", "pip", "install", *base_flags, *target_args, "--user"])
    install_attempts.append([sys.executable, "-m", "pip", "install", *base_flags, *target_args])

  installed = False
  for cmd in install_attempts:
    try:
      res = subprocess.run(cmd)
      if res.returncode == 0:
        installed = True
        import importlib
        importlib.invalidate_caches()
        print("✅ Dependencies installed successfully.")
        break
    except Exception:
      continue

  if not installed:
    # Final check: did the imports actually succeed despite non-zero pip return code?
    still_missing = []
    for mod, pkg in required_pkgs:
      try:
        __import__(mod)
      except ImportError:
        still_missing.append(pkg)
    if not still_missing:
      print("✅ Required packages are imported successfully.")
      return

    print("")
    print("=" * 60)
    print("❌ Could not automatically install dependencies: " + ", ".join(still_missing))
    print("Please verify network connectivity or run manually:")
    print("   pip install -r requirements.txt")
    print("=" * 60)
    print("")
    sys.exit(1)

  # Refresh user site-packages in sys.path so new imports succeed immediately
  if hasattr(site, "getusersitepackages"):
    user_site = site.getusersitepackages()
    if user_site not in sys.path and os.path.exists(user_site):
      sys.path.insert(0, user_site)


def ensure_baseline_models(models_dir=None):
  """Checks and downloads baseline models (CLIP ViT-B/32 and SigLIP Base) if missing."""
  if models_dir is None:
    models_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "models")
  os.makedirs(models_dir, exist_ok=True)

  baseline_targets = [
      ("clip-vit-b-32", "clip-vit-b-32", "openai/clip-vit-base-patch32"),
      ("siglip-base", "siglip-base", "google/siglip-base-patch16-224"),
  ]

  for key, dirname, repo_id in baseline_targets:
    target_path = os.path.join(models_dir, dirname)
    has_weights = (
        os.path.exists(target_path)
        and len(os.listdir(target_path)) > 0
        and any(f.endswith((".bin", ".safetensors", ".json")) for f in os.listdir(target_path))
    )
    if not has_weights:
      print(f"⬇️ Initializing baseline model '{key}' from {repo_id}...")
      os.makedirs(target_path, exist_ok=True)
      try:
        from huggingface_hub import snapshot_download
        dl_kwargs = {"local_dir": target_path}
        if sys.platform == "win32":
          dl_kwargs["local_dir_use_symlinks"] = False
        snapshot_download(repo_id, **dl_kwargs)
        print(f"✅ Baseline model '{key}' successfully downloaded to {target_path}")
      except Exception as e:
        print(f"⚠️ Note: Could not auto-download model '{key}': {e}. You can download it anytime from the Web UI Settings tab.")


def find_free_port(start_port=8080, host="127.0.0.1"):
  port = start_port
  while port < 65535:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
      if s.connect_ex((host, port)) != 0:
        return port
      port += 1
  return start_port


if __name__ == "__main__":
  ensure_dependencies()
  ensure_baseline_models()

  from flint.web.server import run_server

  host = "127.0.0.1"
  default_port = 8080

  if len(sys.argv) > 1:
    try:
      default_port = int(sys.argv[1])
    except ValueError:
      pass

  port = find_free_port(start_port=default_port, host=host)

  url = f"http://{host}:{port}"
  print("=" * 60)
  print(f"⚡ Launching FLINT Vision Engine UI at: {url}")
  print("=" * 60)

  import threading
  import time

  def _open_browser():
    time.sleep(1.2)
    try:
      webbrowser.open(url)
    except Exception:
      pass

  threading.Thread(target=_open_browser, daemon=True).start()

  run_server(host=host, port=port)
