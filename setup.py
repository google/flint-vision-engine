#!/usr/bin/env python3
# Copyright 2026 Google LLC
# Licensed under Apache 2.0

from setuptools import setup, find_packages

setup(
    name="image-correlation-suite",
    version="1.0.0",
    description="Enterprise Forensic Vision Intelligence Platform & CAS Media Vault",
    packages=find_packages(include=["sympics", "sympics.*"]),
    python_requires=">=3.10",
)
