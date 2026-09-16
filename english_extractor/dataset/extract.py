"""Extract translatable English dialogue lines from subtitle files (replaces align.py).

For every file in the discover manifest:
1. keep dialogue events with translatable text -- drop signs / karaoke /
   drawings / letter-less lines, styles matching `skip_style_pattern` and events
   with a non-empty Effect (the same filter align.py applied before matching);
2. strip override tags and put the text on one line;
3. sort by start time and attach the previous / next extracted line as context.

Output: one `<episode id>.jsonl` per file plus `extract_summary.json`.
"""
from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Sequence

import regex

from english_extractor import DEFAULT_OUTPUT
from english_extractor.ass.models import Event
from english_extractor.dataset.textutil import has_override_tags, is_translatable, load_dialogues, plain_text


@dataclass
class ExtractConfig:
    skip_style_pattern: str = (
        r"(?i)(?:^|[^a-z])(?:signs?|op|ed|opening|ending|karaoke|titles?|credits?|songs?|"
        r"lyrics?|typeset(?:ting)?|ts|notes?|caption|logo)(?:$|[^a-z])"
    )
    skip_nonempty_effect: bool = True


@dataclass
class Line:
    index: int                        # event position in the original file
    start: float
    end: float
    text: str
    style: str
    name: str
    has_tags: bool = False            # raw text carried {...} overrides (e.g. <i> -> {\i1})


def extract_lines(events: Sequence[Event], config: Optional[ExtractConfig] = None) -> tuple[list[Line], dict]:
    """Translatable lines sorted by start time, plus counts of what was dropped and why."""
    cfg = config or ExtractConfig()
    pat = regex.compile(cfg.skip_style_pattern) if cfg.skip_style_pattern else None
    dropped = {"not_translatable": 0, "skipped_style": 0, "skipped_effect": 0, "bad_timestamp": 0}
    lines: list[Line] = []
    for ev in events:
        if not ev.is_dialogue or not is_translatable(ev.text):
            dropped["not_translatable"] += 1
            continue
        if pat and pat.search(ev.style or ""):
            dropped["skipped_style"] += 1
            continue
        if cfg.skip_nonempty_effect and (ev.effect or "").strip():
            dropped["skipped_effect"] += 1
            continue
        text = plain_text(ev.text)
        if not text:
            dropped["not_translatable"] += 1
            continue
        try:
            start, end = ev.start_seconds, ev.end_seconds
        except ValueError:
            dropped["bad_timestamp"] += 1
            continue
        lines.append(Line(ev.index, start, max(start, end), text, ev.style, ev.name, has_override_tags(ev.text)))
    lines.sort(key=lambda s: (s.start, s.index))
    return lines, dropped


def to_records(lines: list[Line], movie_id: str) -> list[dict]:
    """JSONL-ready dicts with the neighbouring lines as context."""
    records = []
    for k, ln in enumerate(lines):
        records.append({
            "movie_id": movie_id,
            "text": ln.text,
            "context_before": lines[k - 1].text if k > 0 else "",
            "context_after": lines[k + 1].text if k + 1 < len(lines) else "",
            "speaker": ln.name if ln.name.strip() else None,
            "style": ln.style,
            "start": round(ln.start, 3),
            "end": round(ln.end, 3),
            "event_index": ln.index,
            "has_tags": ln.has_tags,
        })
    return records


def write_records_jsonl(records: list[dict], movie_id: str, out_dir: str | Path) -> Path:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{movie_id}.jsonl"
    with open(path, "w", encoding="utf-8") as fh:
        for rec in records:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return path


def run_extraction(manifest: dict, out_dir: str | Path, config: Optional[ExtractConfig] = None) -> dict:
    cfg = config or ExtractConfig()
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    summary: dict = {"movies": {}, "total_lines": 0, "dropped": {}, "failed": []}
    for f in manifest.get("files", []):
        try:
            events = load_dialogues(f["path"])
        except Exception as exc:  # keep going on a bad file
            summary["failed"].append({"id": f["id"], "error": repr(exc)})
            continue
        lines, dropped = extract_lines(events, cfg)
        write_records_jsonl(to_records(lines, f["id"]), f["id"], out_dir)
        summary["movies"][f["id"]] = {"path": f["path"], "dialogue_events": len(events),
                                      "extracted": len(lines), **dropped}
        summary["total_lines"] += len(lines)
        for k, v in dropped.items():
            summary["dropped"][k] = summary["dropped"].get(k, 0) + v
    (out_dir / "extract_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Extract English dialogue lines from discovered subtitle files.")
    ap.add_argument("manifest", nargs="?", default=str(DEFAULT_OUTPUT / "files.json"),
                    help="files.json from english_extractor.dataset.discover")
    ap.add_argument("--out", default=str(DEFAULT_OUTPUT / "extracted"))
    args = ap.parse_args(argv)

    manifest = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
    summary = run_extraction(manifest, args.out)
    print(f"episodes: {len(summary['movies'])}  lines: {summary['total_lines']}  "
          f"dropped: {summary['dropped']}  failed: {len(summary['failed'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
