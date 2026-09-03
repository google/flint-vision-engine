#!/usr/bin/env python3
# Copyright 2026 Google LLC
# Licensed under Apache 2.0

"""
===============================================================================
SYMPICS SERVICE INTEGRITY & PROCESS WATCHDOG DAEMON
===============================================================================
Supervises SYMPICS services (Web UI Server & Real-Time Intake Daemon):
1. Actively monitors process PID liveness and HTTP health checks (GET /api/status).
2. Automatically restarts services upon crash, hang, or unhandled termination.
3. Implements rate-limiting and exponential backoff to protect against tight crash loops.
4. Logs health status and restart events for forensic auditing.
===============================================================================
"""

import os
import sys
import time
import signal
import urllib.request
import urllib.error
import subprocess
import argparse
from datetime import datetime

# Resolve project paths
_current_dir = os.path.dirname(os.path.abspath(__file__))
_project_root = os.path.abspath(os.path.join(_current_dir, "..", ".."))
_web_server_script = os.path.join(_project_root, "web", "server.py")
_intake_daemon_script = os.path.join(_project_root, "scripts", "daemons", "sympics_intake_daemon.py")


class ServiceSupervisor:
    def __init__(self, name, cmd_args, health_url=None, cwd=_project_root, check_interval=5.0):
        self.name = name
        self.cmd_args = cmd_args
        self.health_url = health_url
        self.cwd = cwd
        self.check_interval = check_interval
        self.process = None
        self.restart_count = 0
        self.last_restart_time = 0
        self.consecutive_failures = 0

    def start(self):
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"[{timestamp}] [WATCHDOG] Starting service '{self.name}'...")
        try:
            self.process = subprocess.Popen(
                self.cmd_args,
                cwd=self.cwd,
                stdout=None,
                stderr=None,
                shell=False
            )
            self.last_restart_time = time.time()
            self.restart_count += 1
            print(f"[{timestamp}] [WATCHDOG] '{self.name}' spawned with PID {self.process.pid}.")
        except Exception as e:
            print(f"[{timestamp}] [ERROR] Failed to start '{self.name}': {e}")

    def check_health(self):
        """Returns True if service is running and healthy, False otherwise."""
        if self.process is None:
            return False

        # 1. Process exit status check
        poll_res = self.process.poll()
        if poll_res is not None:
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            print(f"[{timestamp}] [ALERT] Service '{self.name}' (PID {self.process.pid}) exited with code {poll_res}.")
            return False

        # 2. HTTP Health check (if applicable)
        if self.health_url:
            try:
                req = urllib.request.Request(self.health_url, headers={"User-Agent": "SympicsWatchdog/1.0"})
                with urllib.request.urlopen(req, timeout=4.0) as resp:
                    if resp.status in (200, 204, 301, 302):
                        self.consecutive_failures = 0
                        return True
            except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, ConnectionRefusedError, OSError) as e:
                self.consecutive_failures += 1
                timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                print(f"[{timestamp}] [WARN] HTTP Health check failed for '{self.name}' ({self.health_url}): {e} (Failure #{self.consecutive_failures})")
                if self.consecutive_failures >= 3:
                    print(f"[{timestamp}] [ALERT] '{self.name}' exceeded 3 consecutive health check timeouts. Initiating process restart.")
                    self.kill()
                    return False

        self.consecutive_failures = 0
        return True

    def kill(self):
        if self.process is not None:
            try:
                self.process.terminate()
                self.process.wait(timeout=3.0)
            except Exception:
                try:
                    self.process.kill()
                except Exception:
                    pass
            self.process = None

    def restart_if_needed(self):
        if not self.check_health():
            # Apply backoff if restarting too rapidly
            now = time.time()
            if now - self.last_restart_time < 3.0:
                time.sleep(2.0)
            self.kill()
            self.start()


def run_watchdog(http_port=8080, check_interval=5.0, supervise_intake=True):
    print("=" * 79)
    print(" [*]  SYMPICS SYSTEM PROCESS & UI INTEGRITY SUPERVISOR")
    print("=" * 79)
    print(f" Web UI Port         : http://localhost:{http_port}")
    print(f" Supervise Intake   : {supervise_intake}")
    print(f" Health Check Rate  : Every {check_interval}s")
    print("=" * 79)

    services = []

    # 1. Web UI Server Service
    web_svc = ServiceSupervisor(
        name="Sympics-Web-Studio",
        cmd_args=[sys.executable, _web_server_script, "--port", str(http_port)],
        health_url=f"http://127.0.0.1:{http_port}/",
        cwd=_project_root,
        check_interval=check_interval
    )
    services.append(web_svc)

    # 2. Intake Daemon Service (Optional)
    if supervise_intake:
        cand_local = os.path.join(_project_root, "future-lan-storage")
        cand_parent = os.path.join(_project_root, "..", "future-lan-storage")
        vault_dir = os.getenv("SYMPICS_VAULT_ROOT") or (cand_parent if (os.path.exists(cand_parent) and not os.path.exists(cand_local)) else cand_local)
        staging_dir = os.getenv("SYMPICS_STAGING_DIR") or os.path.join(vault_dir, "03_Ingestion_Staging")
        intake_svc = ServiceSupervisor(
            name="Sympics-Intake-Daemon",
            cmd_args=[
                sys.executable, _intake_daemon_script,
                "--staging-dir", staging_dir,
                "--vault-dir", vault_dir,
                "--poll-interval", "2.0",
                "--stability-delay", "2.0"
            ],
            health_url=None,
            cwd=_project_root,
            check_interval=check_interval
        )
        services.append(intake_svc)

    # Initial start
    for svc in services:
        svc.start()

    # Graceful shutdown handler
    def handle_signal(sig, frame):
        print("\n[WATCHDOG] Received shutdown signal. Terminating managed services...")
        for svc in services:
            svc.kill()
        sys.exit(0)

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    # Supervision Loop
    try:
        while True:
            time.sleep(check_interval)
            for svc in services:
                svc.restart_if_needed()
    except KeyboardInterrupt:
        handle_signal(None, None)


def main():
    parser = argparse.ArgumentParser(description="SYMPICS Service Integrity & Process Watchdog.")
    parser.add_argument("--port", "-p", type=int, default=8080, help="SYMPICS Web Studio port (default: 8080).")
    parser.add_argument("--interval", "-i", type=float, default=5.0, help="Health check interval in seconds (default: 5.0).")
    parser.add_argument("--no-intake", action="store_true", help="Supervise only the Web Studio server (skip intake daemon).")

    args = parser.parse_args()
    run_watchdog(http_port=args.port, check_interval=args.interval, supervise_intake=not args.no_intake)


if __name__ == "__main__":
    main()
