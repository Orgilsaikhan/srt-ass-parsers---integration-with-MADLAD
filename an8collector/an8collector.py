r"""Move every event line with a {\an8} tag to the bottom of an .ass file's [Events] section.

Usage:
    python an8collector.py "Diamond no Ace 0302.ass"
    python an8collector.py ../mn-finished             # every .ass file in a folder
    python an8collector.py ../mn-finished --dry-run   # only report, don't write
"""

import argparse
import re
import sys
from pathlib import Path

# \an8 anywhere inside an override block, e.g. {\an8} or {\an8\i1} or {\i1\an8}
AN8_TAG = re.compile(rb"\{[^}]*\\an8[^}]*\}")
EVENT_LINE = re.compile(rb"^(Dialogue|Comment):")
BOM = b"\xef\xbb\xbf"


def collect_an8(path, output=None, dry_run=False):
    r"""Move {\an8} event lines to the end of the [Events] section.

    Moved lines keep their relative order, and so do the lines left in place.
    The file is handled as raw bytes, so the BOM, encoding and line endings
    stay exactly as they were. Writes to `output` if given, otherwise in place.

    Returns (number of {\an8} lines, whether the file content changed).
    """
    path = Path(path)
    data = path.read_bytes()
    lines = data.splitlines(keepends=True)

    start = next((i for i, l in enumerate(lines) if l.lstrip(BOM).strip() == b"[Events]"), None)
    if start is None:
        raise ValueError("no [Events] section")
    end = next((i for i in range(start + 1, len(lines)) if lines[i].lstrip().startswith(b"[")), len(lines))
    # Blank lines separating [Events] from the next section stay where they are.
    while end > start + 1 and not lines[end - 1].strip():
        end -= 1

    body = lines[start + 1:end]
    unterminated = bool(body) and not body[-1].endswith((b"\n", b"\r"))
    if unterminated:
        body[-1] += b"\r\n" if b"\r\n" in data else b"\n"

    is_an8 = [bool(EVENT_LINE.match(l) and AN8_TAG.search(l)) for l in body]
    new_body = [l for l, m in zip(body, is_an8) if not m] + [l for l, m in zip(body, is_an8) if m]
    if unterminated:
        new_body[-1] = new_body[-1].rstrip(b"\r\n")

    out = b"".join(lines[:start + 1] + new_body + lines[end:])
    if len(out) != len(data):
        raise RuntimeError("reordering changed the file size; nothing was written")

    changed = out != data
    if not dry_run and (changed or output):
        Path(output or path).write_bytes(out)
    return sum(is_an8), changed


def iter_ass_files(paths):
    for p in map(Path, paths):
        if p.is_dir():
            yield from sorted(p.glob("*.ass"))
        else:
            yield p


def main(argv=None):
    parser = argparse.ArgumentParser(description=r"Move {\an8} lines to the bottom of .ass subtitle files.")
    parser.add_argument("paths", nargs="+", help=".ass files, or folders containing them")
    parser.add_argument("-n", "--dry-run", action="store_true", help="report what would move without writing")
    args = parser.parse_args(argv)

    failed = False
    for file in iter_ass_files(args.paths):
        try:
            count, changed = collect_an8(file, dry_run=args.dry_run)
        except (OSError, ValueError, RuntimeError) as e:
            print(f"{file.name}: skipped ({e})", file=sys.stderr)
            failed = True
            continue
        if not count:
            print(f"{file.name}: no {{\\an8}} lines")
        elif not changed:
            print(f"{file.name}: {count} {{\\an8}} lines already at the bottom")
        else:
            verb = "would move" if args.dry_run else "moved"
            print(f"{file.name}: {verb} {count} {{\\an8}} lines to the bottom")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
