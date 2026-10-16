#!/usr/bin/env python3
"""Build the shared Tauri portable GUI (the CLI remains OpenWrt-Installer.py)."""
from pathlib import Path
import subprocess
import sys

TOP=Path(__file__).resolve().parents[1]
subprocess.run([sys.executable,str(TOP/'installer/build.py'),*sys.argv[1:]],cwd=TOP,check=True)
