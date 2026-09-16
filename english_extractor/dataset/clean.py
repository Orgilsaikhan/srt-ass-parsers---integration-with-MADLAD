"""English line cleaning (copied from src/dataset/clean.py, plan §9).

Every extracted English line is classified as `clean`, `review` or `rejected`
with a list of `reasons`.  Only the single-line checks of the original are kept;
the checks that compared an English line with its Mongolian counterpart are gone.
Thresholds live in `CleanConfig`.  Exact and near duplicates are removed
corpus-wide (first occurrence wins).
"""
from __future__ import annotations

import argparse
import json
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Iterator, Optional

import regex

from english_extractor import DEFAULT_OUTPUT
from english_extractor.dataset.textutil import cyrillic_ratio, has_control_chars, word_count

_ASS_TAG = regex.compile(r"\{[^}]*\}|\\[Nnh]|\\(?:an?|pos|move|fad|fade|b|i|u|s|c|fs|fn|k[fo]?|K|p)\d*")
_BRACES = regex.compile(r"[{}]")
_HTML = regex.compile(r"</?[A-Za-z][^<>]*>")
_URL = regex.compile(r"https?://|www\.|\.(?:com|net|org|mn)\b", regex.I)
_CREDIT = regex.compile(
    r"\b(?:subtitles?|subs|sub)\s+by\b|\bsynced\b|\bcorrected by\b|\btranslated by\b|\bresync\b|"
    r"\bopensubtitles\b|\bsubscene\b|\baddic7ed\b|\bencoded by\b|\bripped by\b|"
    r"орчуулсан|орчуулагч|орчуулга\s*[:：]|хадмал\s*[:：]|хадмалыг",
    regex.I,
)
_PUNCT_ONLY = regex.compile(r"^[\s\p{P}\p{S}]*$")
_MOJIBAKE = regex.compile(r"[ÐÑ][-¿Ѐ-џ]|Ã[-¿]|Â[-¿]|â€")
_NORMALISE = regex.compile(r"[\p{P}\p{S}\s]+")


@dataclass
class CleanConfig:
    reject_cyrillic: float = 0.5          # line looks Mongolian (wrong-language file)
    max_chars: int = 600                  # above -> review
    dedupe: bool = True
    near_dedupe: bool = True
    # on-screen captions/signs: "(...)" / "[...]" wrapped or mostly-uppercase line -> review
    flag_captions: bool = True
    caption_uppercase_ratio: float = 0.8
    caption_min_words: int = 3


@dataclass
class CleanResult:
    clean: list[dict] = field(default_factory=list)
    review: list[dict] = field(default_factory=list)
    rejected: list[dict] = field(default_factory=list)
    reason_counts: Counter = field(default_factory=Counter)

    @property
    def total(self) -> int:
        return len(self.clean) + len(self.review) + len(self.rejected)


def is_caption(text: str, uppercase_ratio: float = 0.8, min_words: int = 3) -> bool:
    """Whole text wrapped in (...) / [...], or mostly uppercase letters with >= min_words words."""
    t = text.strip()
    if not t:
        return False
    if (t[0] == "(" and t[-1] == ")") or (t[0] == "[" and t[-1] == "]"):
        return True
    letters = [ch for ch in t if ch.isalpha()]
    if letters and word_count(t) >= min_words:
        upper = sum(1 for ch in letters if ch.isupper())
        return upper / len(letters) >= uppercase_ratio
    return False


def normalise_for_dedupe(text: str) -> str:
    return _NORMALISE.sub("", text.lower())


def classify_line(text: str, config: Optional[CleanConfig] = None) -> tuple[str, list[str]]:
    """Return (status, reasons) for one English line; status in {'clean','review','rejected'}."""
    cfg = config or CleanConfig()
    reject: list[str] = []
    review: list[str] = []
    t = (text or "").strip()

    if not t:
        return "rejected", ["empty_text"]
    if _PUNCT_ONLY.match(t):
        reject.append("punctuation_only")
    if "�" in t:
        reject.append("replacement_char")
    if has_control_chars(t):
        reject.append("control_chars")
    if _MOJIBAKE.search(t):
        reject.append("mojibake")
    if _ASS_TAG.search(t) or _BRACES.search(t):
        reject.append("residual_ass_tags")
    if _HTML.search(t):
        reject.append("html_tags")
    if _URL.search(t) or _CREDIT.search(t):
        reject.append("credit_or_url")
    if cyrillic_ratio(t) >= cfg.reject_cyrillic:
        reject.append("cyrillic_text")

    if len(t) > cfg.max_chars:
        review.append("very_long")
    if cfg.flag_captions and is_caption(t, cfg.caption_uppercase_ratio, cfg.caption_min_words):
        review.append("caption")

    if reject:
        return "rejected", reject
    if review:
        return "review", review
    return "clean", []


def clean_records(records: Iterable[dict], config: Optional[CleanConfig] = None) -> CleanResult:
    """Classify all records; dedupe across the corpus keeping the first occurrence."""
    cfg = config or CleanConfig()
    result = CleanResult()
    seen_exact: set[str] = set()
    seen_near: set[str] = set()

    for rec in records:
        text = rec.get("text", "") or ""
        status, reasons = classify_line(text, cfg)

        if status != "rejected" and cfg.dedupe:
            exact = text.strip()
            near = normalise_for_dedupe(text)
            if exact in seen_exact:
                status, reasons = "rejected", ["duplicate_exact"]
            elif cfg.near_dedupe and near in seen_near:
                status, reasons = "rejected", ["duplicate_near"]
            else:
                seen_exact.add(exact)
                seen_near.add(near)

        out = dict(rec)
        out["text"] = text
        out["status"] = status
        out["reasons"] = reasons
        for r in reasons:
            result.reason_counts[r] += 1
        getattr(result, status).append(out)
    return result


# ---------------------------------------------------------------------------
# I/O
# ---------------------------------------------------------------------------

def iter_jsonl(path: str | Path) -> Iterator[dict]:
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                yield json.loads(line)


def iter_extracted(source: str | Path | Iterable[str | Path]) -> Iterator[dict]:
    """Records from a directory of *.jsonl, a single jsonl file, or an explicit list of files."""
    if isinstance(source, (str, Path)):
        src = Path(source)
        files = sorted(src.glob("*.jsonl")) if src.is_dir() else [src]
    else:
        files = [Path(f) for f in source]
    for f in files:
        yield from iter_jsonl(f)


def write_jsonl(records: Iterable[dict], path: str | Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        for r in records:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    return path


def render_report(result: CleanResult, config: CleanConfig) -> str:
    total = result.total or 1
    lines = [
        "# English cleaning report", "",
        "| Outcome | Count | Share |", "|---|---:|---:|",
        f"| clean | {len(result.clean)} | {len(result.clean) / total:.1%} |",
        f"| review | {len(result.review)} | {len(result.review) / total:.1%} |",
        f"| rejected | {len(result.rejected)} | {len(result.rejected) / total:.1%} |",
        f"| **total** | {result.total} | |", "",
        "## Counts per reason", "",
        "| Reason | Count |", "|---|---:|",
    ]
    for reason, n in result.reason_counts.most_common():
        lines.append(f"| {reason} | {n} |")
    lines += ["", "## Thresholds", "", "```text"]
    for k, v in vars(config).items():
        lines.append(f"{k} = {v}")
    lines.append("```")
    return "\n".join(lines) + "\n"


def run_clean(source: str | Path | Iterable[str | Path], out_dir: str | Path, report_path: str | Path,
              config: Optional[CleanConfig] = None) -> CleanResult:
    cfg = config or CleanConfig()
    result = clean_records(iter_extracted(source), cfg)
    out_dir = Path(out_dir)
    write_jsonl(result.clean, out_dir / "clean.jsonl")
    write_jsonl(result.review, out_dir / "review.jsonl")
    write_jsonl(result.rejected, out_dir / "rejected.jsonl")
    report_path = Path(report_path)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(render_report(result, cfg), encoding="utf-8")
    return result


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Clean extracted English subtitle lines.")
    ap.add_argument("source", nargs="?", default=str(DEFAULT_OUTPUT / "extracted"),
                    help="directory of extracted *.jsonl or a single jsonl file")
    ap.add_argument("--out", default=str(DEFAULT_OUTPUT / "cleaned"))
    ap.add_argument("--report", default=str(DEFAULT_OUTPUT / "reports" / "cleaning_report.md"))
    ap.add_argument("--no-dedupe", action="store_true")
    args = ap.parse_args(argv)

    cfg = CleanConfig(dedupe=not args.no_dedupe)
    res = run_clean(args.source, args.out, args.report, cfg)
    print(f"clean: {len(res.clean)}  review: {len(res.review)}  rejected: {len(res.rejected)}  "
          f"(total {res.total}) -> {args.out}, report {args.report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
