#!/usr/bin/env python3
"""
Column profiler for the BioGRID CSV/TSV files (works on files of any size, streams line by line).

For every column it reports:
  - filled / empty count  (empty = "", "-", "NA", "N/A", "null", "None")
  - inferred data type    (int, float, bool, text) and how mixed it is
  - value range           (min/max for numbers, min/max length for text)
  - number of distinct values and the most common ones
  - multi-value columns   (values containing "|") and common prefixes ("pubmed:", "uniprot/swiss-prot:", ...)
  - a verdict: EMPTY / CONSTANT / ID-like / ... so you can see which columns are useless

Usage:
  python3 analyze_csv.py FILE                       # profile all columns
  python3 analyze_csv.py FILE --limit 100000        # only the first 100k rows (quick look at huge files)
  python3 analyze_csv.py FILE --json report.json    # also save the report as JSON
  python3 analyze_csv.py FILE --drop-useless OUT    # write a copy without EMPTY/CONSTANT columns

Only the Python standard library is used - no pip install needed.
"""

import argparse
import json
import re
import sys
import time
from collections import Counter

EMPTY_VALUES = {"", "-", "na", "n/a", "null", "none", "nan"}
BOOL_VALUES = {"true", "false", "yes", "no"}
INT_RE = re.compile(r"^[+-]?\d+$")
FLOAT_RE = re.compile(r"^[+-]?(\d+\.\d*|\.\d+|\d+)([eE][+-]?\d+)?$")
PREFIX_RE = re.compile(r"^([A-Za-z][\w /.-]{0,40}):")  # e.g. "entrez gene/locuslink:", "PUBMED:"

DISTINCT_CAP = 200_000  # stop tracking new distinct values per column beyond this (memory guard)
TOP_N = 5


class ColumnStats:
    def __init__(self, name):
        self.name = name
        self.filled = 0
        self.empty = 0
        self.types = Counter()
        self.num_min = None
        self.num_max = None
        self.len_min = None
        self.len_max = None
        self.counter = Counter()
        self.distinct_overflow = False
        self.multi_valued = 0
        self.max_parts = 1
        self.prefixes = Counter()

    def add(self, raw):
        v = raw.strip()
        if v.lower() in EMPTY_VALUES:
            self.empty += 1
            return
        self.filled += 1

        # distinct values (capped)
        if v in self.counter or len(self.counter) < DISTINCT_CAP:
            self.counter[v] += 1
        else:
            self.distinct_overflow = True

        # length
        n = len(v)
        if self.len_min is None or n < self.len_min:
            self.len_min = n
        if self.len_max is None or n > self.len_max:
            self.len_max = n

        # multi-valued ("a|b|c")
        if "|" in v:
            self.multi_valued += 1
            parts = v.count("|") + 1
            if parts > self.max_parts:
                self.max_parts = parts

        # prefix like "pubmed:123" (look at the first part only)
        first = v.split("|", 1)[0]
        m = PREFIX_RE.match(first)
        if m:
            self.prefixes[m.group(1) + ":"] += 1

        # type
        if INT_RE.match(v):
            self.types["int"] += 1
            self._num(int(v))
        elif FLOAT_RE.match(v):
            self.types["float"] += 1
            self._num(float(v))
        elif v.lower() in BOOL_VALUES:
            self.types["bool"] += 1
        else:
            self.types["text"] += 1

    def _num(self, x):
        if self.num_min is None or x < self.num_min:
            self.num_min = x
        if self.num_max is None or x > self.num_max:
            self.num_max = x

    # ---- derived ------------------------------------------------------------

    @property
    def total(self):
        return self.filled + self.empty

    @property
    def distinct(self):
        return len(self.counter)

    def dominant_type(self):
        if not self.types:
            return "none"
        t = self.types
        if t["text"] == 0 and t["bool"] == 0:
            return "float" if t["float"] else "int"
        if t["text"] == 0 and t["int"] == 0 and t["float"] == 0:
            return "bool"
        return "text"

    def type_purity(self):
        """Share of filled values that match the dominant type (int counts as float)."""
        if not self.filled:
            return 1.0
        d = self.dominant_type()
        if d == "float":
            ok = self.types["float"] + self.types["int"]
        elif d == "text":
            ok = self.filled  # everything fits in text
        else:
            ok = self.types[d]
        return ok / self.filled

    def sql_type(self):
        d = self.dominant_type()
        if d == "int":
            big = max(abs(self.num_min or 0), abs(self.num_max or 0)) > 2_147_483_647
            return "BIGINT" if big else "INTEGER"
        if d == "float":
            return "DOUBLE PRECISION"
        if d == "bool":
            return "BOOLEAN"
        if d == "none":
            return "-"
        if self.multi_valued:
            return "TEXT  (multi-valued, consider own table)"
        return f"VARCHAR({self.len_max})" if self.len_max and self.len_max <= 255 else "TEXT"

    def verdict(self):
        if self.filled == 0:
            return "EMPTY - drop"
        if self.distinct == 1 and not self.distinct_overflow:
            if self.empty == 0:
                return "CONSTANT - drop"
            return "CONSTANT or empty - probably drop"
        notes = []
        if not self.distinct_overflow and self.distinct == self.filled and self.empty == 0:
            notes.append("unique (ID / key candidate)")
        elif self.distinct <= 20 and not self.distinct_overflow:
            notes.append("categorical")
        if self.empty / self.total > 0.95:
            notes.append(f"{self.empty / self.total:.1%} empty")
        if self.multi_valued:
            notes.append(f"multi-valued (up to {self.max_parts} parts)")
        if self.type_purity() < 1.0 and self.dominant_type() != "text":
            notes.append("mixed types")
        return ", ".join(notes) or "ok"

    def to_dict(self):
        return {
            "name": self.name,
            "rows": self.total,
            "filled": self.filled,
            "empty": self.empty,
            "type": self.dominant_type(),
            "type_counts": dict(self.types),
            "sql_type": self.sql_type(),
            "min": self.num_min,
            "max": self.num_max,
            "min_length": self.len_min,
            "max_length": self.len_max,
            "distinct": self.distinct,
            "distinct_is_lower_bound": self.distinct_overflow,
            "multi_valued_rows": self.multi_valued,
            "max_parts": self.max_parts,
            "prefixes": dict(self.prefixes.most_common(TOP_N)),
            "top_values": self.counter.most_common(TOP_N),
            "verdict": self.verdict(),
        }


# ---- reading --------------------------------------------------------------

def detect_delimiter(header_line, forced):
    if forced:
        return "\t" if forced in ("tab", "\\t") else forced
    for d in ("\t", ";", ","):
        if d in header_line:
            return d
    return "\t"


def profile(path, delimiter=None, limit=None):
    start = time.time()
    with open(path, encoding="utf-8", errors="replace", newline="") as f:
        header_line = f.readline().rstrip("\r\n")
        delim = detect_delimiter(header_line, delimiter)
        names = [h.strip() for h in header_line.lstrip("#").split(delim)]
        cols = [ColumnStats(n) for n in names]
        ncols = len(cols)
        bad_rows = 0
        rows = 0

        for line in f:
            line = line.rstrip("\r\n")
            if not line:
                continue
            fields = line.split(delim)
            if len(fields) != ncols:
                bad_rows += 1
                fields = (fields + [""] * ncols)[:ncols]
            for col, val in zip(cols, fields):
                col.add(val)
            rows += 1
            if rows % 500_000 == 0:
                print(f"  ... {rows:,} rows ({time.time() - start:.0f}s)", file=sys.stderr)
            if limit and rows >= limit:
                break

    return {
        "file": path,
        "delimiter": "TAB" if delim == "\t" else delim,
        "rows": rows,
        "columns": len(cols),
        "rows_with_wrong_field_count": bad_rows,
        "limited": bool(limit and rows >= limit),
        "seconds": round(time.time() - start, 1),
    }, cols


# ---- output ---------------------------------------------------------------

def short(v, width=60):
    s = str(v)
    return s if len(s) <= width else s[: width - 3] + "..."


def print_report(meta, cols):
    print(f"\nFile:      {meta['file']}")
    print(f"Rows:      {meta['rows']:,}" + ("  (limited sample)" if meta["limited"] else ""))
    print(f"Columns:   {meta['columns']}   delimiter: {meta['delimiter']}")
    if meta["rows_with_wrong_field_count"]:
        print(f"WARNING:   {meta['rows_with_wrong_field_count']:,} rows have a different number of fields than the header")
    print(f"Time:      {meta['seconds']}s")

    for i, c in enumerate(cols, 1):
        print("\n" + "-" * 78)
        print(f"[{i}] {c.name}")
        print(f"    verdict : {c.verdict()}")
        fill = c.filled / c.total if c.total else 0
        print(f"    filled  : {c.filled:,} / {c.total:,} ({fill:.1%})   empty: {c.empty:,}")
        if c.filled == 0:
            continue
        types = ", ".join(f"{k}={v:,}" for k, v in c.types.most_common())
        print(f"    type    : {c.dominant_type()}  ({types})  -> SQL: {c.sql_type()}")
        if c.num_min is not None:
            print(f"    range   : {c.num_min} .. {c.num_max}")
        print(f"    length  : {c.len_min} .. {c.len_max} chars")
        dist = f"{c.distinct:,}" + ("+ (capped)" if c.distinct_overflow else "")
        print(f"    distinct: {dist}")
        if c.multi_valued:
            print(f"    multi   : {c.multi_valued:,} rows contain '|' (max {c.max_parts} parts)")
        if c.prefixes:
            pre = ", ".join(f"{p} {n:,}" for p, n in c.prefixes.most_common(TOP_N))
            print(f"    prefixes: {pre}")
        print("    top     :")
        for val, n in c.counter.most_common(TOP_N):
            print(f"        {n:>10,}  {short(val)}")

    # summary
    print("\n" + "=" * 78)
    print("SUMMARY")
    print("=" * 78)
    w = min(max(len(c.name) for c in cols), 40)
    print(f"{'#':>3}  {'column':<{w}}  {'filled':>7}  {'distinct':>9}  {'type':<6}  verdict")
    for i, c in enumerate(cols, 1):
        fill = f"{c.filled / c.total:.0%}" if c.total else "-"
        dist = f"{c.distinct:,}" + ("+" if c.distinct_overflow else "")
        print(f"{i:>3}  {short(c.name, w):<{w}}  {fill:>7}  {dist:>9}  {c.dominant_type():<6}  {c.verdict()}")

    useless = [c.name for c in cols if is_useless(c)]
    if useless:
        print(f"\nColumns you can drop ({len(useless)}): " + ", ".join(useless))


def is_useless(c):
    return c.filled == 0 or (c.distinct == 1 and not c.distinct_overflow)


def drop_useless(path, out_path, meta, cols):
    keep = [i for i, c in enumerate(cols) if not is_useless(c)]
    delim = "\t" if meta["delimiter"] == "TAB" else meta["delimiter"]
    if meta["limited"]:
        print("Refusing --drop-useless together with --limit (the verdict is based on a sample only).", file=sys.stderr)
        return
    with open(path, encoding="utf-8", errors="replace", newline="") as src, \
         open(out_path, "w", encoding="utf-8", newline="") as dst:
        header = src.readline().rstrip("\r\n")
        hash_prefix = "#" if header.startswith("#") else ""
        fields = header.lstrip("#").split(delim)
        dst.write(hash_prefix + delim.join(fields[i] for i in keep) + "\n")
        n = len(fields)
        for line in src:
            line = line.rstrip("\r\n")
            if not line:
                continue
            f = (line.split(delim) + [""] * n)[:n]
            dst.write(delim.join(f[i] for i in keep) + "\n")
    print(f"\nWrote {out_path} with {len(keep)} of {len(cols)} columns.")


def main():
    ap = argparse.ArgumentParser(description="Profile the columns of a (large) CSV/TSV file.")
    ap.add_argument("file")
    ap.add_argument("-d", "--delimiter", help="field separator (default: auto-detect; use 'tab' for TAB)")
    ap.add_argument("-n", "--limit", type=int, help="only read the first N data rows")
    ap.add_argument("--json", metavar="OUT", help="also write the report as JSON")
    ap.add_argument("--drop-useless", metavar="OUT", help="write a copy of the file without EMPTY/CONSTANT columns")
    args = ap.parse_args()

    meta, cols = profile(args.file, args.delimiter, args.limit)
    print_report(meta, cols)

    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump({**meta, "column_stats": [c.to_dict() for c in cols]}, f, indent=2, ensure_ascii=False, default=str)
        print(f"\nJSON report written to {args.json}")

    if args.drop_useless:
        drop_useless(args.file, args.drop_useless, meta, cols)


if __name__ == "__main__":
    main()
