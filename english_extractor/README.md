# english_extractor

English-only subtitle dataset extractor, separated from `src/dataset`. It reads
`.srt` / `.ass` / `.ssa` files and writes clean English dialogue lines as JSONL.
There is no Mongolian side and no alignment.

Nothing else in the project was changed. This folder only holds copies (and
English-only adaptations) of the modules the extractor needs.

## Run

From the project root:

```powershell
python -m pip install -r english_extractor/requirements.txt   # only `regex` (+ pytest)
$env:PYTHONIOENCODING = "utf-8"
python -m english_extractor.dataset.pipeline "Raw Files"
# several folders at once (byte-identical files are kept once)
python -m english_extractor.dataset.pipeline "Raw Files" "Unpaired/English"
python -m pytest english_extractor/tests -q
```

Options: `--out DIR` (default `english_extractor/output/`), `--seed`, `--ratios TRAIN VAL TEST`,
`--test-movies ID ...`, `--no-dedupe` (keep repeated lines such as "Yeah.").

## Stages

| # | Stage | Module | Output (under `--out`) |
|---|---|---|---|
| 1 | Find English files. Language from the filename/folder, always double-checked against the text's script, so Mongolian files are skipped even in an `English/` folder. Byte-identical copies are kept once. | `dataset/discover.py` | `files.json` |
| 2 | Statistics | `dataset/statistics.py` | `reports/dataset_stats.md` / `.json` |
| 3 | Extract dialogue lines. Drops sign/OP/ED/karaoke styles, drawings, Effect lines and letter-less lines, strips tags, sorts by time and adds the previous/next line as context. | `dataset/extract.py` | `extracted/<episode>.jsonl`, `extract_summary.json` |
| 4 | Clean. Rejects empty, corrupted, leftover-tag, credit/URL, Mongolian and duplicate lines; sends captions and very long lines to review. | `dataset/clean.py` | `cleaned/clean.jsonl`, `review.jsonl`, `rejected.jsonl`, `reports/cleaning_report.md` |
| 5 | Split by episode (80/10/10 by line count) | `dataset/split.py` | `train/`, `validation/`, `test/`, `split_manifest.json` |

Episode id = filename without the language token (`yani_07_EN.ass` -> `yani_07`).

## Record format

`extracted/*.jsonl` and `cleaned/*.jsonl` (cleaned rows add `status` and `reasons`), example:

```json
{"movie_id": "yani_07", "text": "Where are you going?", "context_before": "Wait!", "context_after": "Home.",
 "speaker": null, "style": "Default", "start": 83.4, "end": 85.1, "event_index": 42, "has_tags": false}
```

`train/`, `validation/` and `test/` rows keep `text`, `context_before`, `context_after`, `speaker`,
`movie_id`, `start`, `end`.

## Where the files came from

| Here | Copied from | Changes |
|---|---|---|
| `ass/models.py`, `parser.py`, `tags.py`, `validator.py` | `src/ass/` | import paths / docstring only |
| `ass/srt.py` | `src/ass/srt.py` | `srt_to_ass` removed (it needed the writer) |
| `ass/__init__.py` | `src/ass/__init__.py` | writer exports removed |
| `dataset/textutil.py` | `src/dataset/textutil.py` | import paths only |
| `dataset/discover.py` | `src/dataset/pair_files.py` | pairing removed; English only; text check always on; several input folders |
| `dataset/extract.py` | line filter + context of `src/dataset/align.py` | no alignment |
| `dataset/clean.py` | `src/dataset/clean.py` | single-line checks only (regexes unchanged) |
| `dataset/statistics.py`, `split.py`, `pipeline.py` | `src/dataset/` | English-only |
| `tests/` | `tests/` | adapted to the above; `test_extract.py`, `test_discover.py`, `test_pipeline.py` are new |

Not copied: `align.py`, `ass/writer.py`, translation / training / evaluation code.
