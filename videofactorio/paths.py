"""Portable paths for source and frozen Windows distributions."""
from pathlib import Path
import sys

APP_ROOT = Path(sys.executable).resolve().parent if getattr(sys, 'frozen', False) else Path(__file__).resolve().parents[1]
BUNDLE_ROOT = Path(getattr(sys, '_MEIPASS', APP_ROOT))
