"""English-only subtitle dataset extractor, separated from src/dataset (no Mongolian side, no alignment).

    python -m english_extractor.dataset.pipeline "Raw Files"
"""
from pathlib import Path

#: Default output root. Every stage writes below it, so the project's data/ and reports/ are never touched.
DEFAULT_OUTPUT = Path(__file__).resolve().parent / "output"
