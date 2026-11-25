#!/usr/bin/env python3
"""
Download pairwise orthologs from OMA (https://omabrowser.org) and write them as CSV with Entrez Gene IDs.

This is the scripted equivalent of https://omabrowser.org/oma/genomePW/ -> "Get Pairs" (that page is behind a
Cloudflare browser check, so it cannot be scripted). Instead this uses:
  - the OMA REST API            /api/pairs/<GENOME1>/<GENOME2>/   (the orthologous pairs)
  - the OMA bulk mapping file   /All/oma-entrez.txt.gz            (OMA ID -> Entrez Gene ID)

Why Entrez Gene IDs: BioGRID (both the tab3 and the mitab files) identifies genes by Entrez Gene ID
("Entrez Gene Interactor A/B" resp. "entrez gene/locuslink:<id>"), and the essentiality data ("Gene ID") uses
them as well - so Entrez is the ID that joins all our data sets.

One OMA protein can map to several Entrez IDs (e.g. E. coli has an old and a new NCBI gene ID). In that case one
row per Entrez combination is written, so the Entrez columns can be joined on directly. Pairs whose protein has no
Entrez ID are kept with an empty Entrez column.

Usage:  python3 oma_pairs.py OUT_DIR HUMAN RATNO ECOLI      (first genome = species 1, paired with each of the rest)

Only the Python standard library is used.
"""

import csv
import gzip
import json
import os
import re
import sys
import tempfile
import time
import urllib.request

API = "https://omabrowser.org/api"
ENTREZ_MAP_URL = "https://omabrowser.org/All/oma-entrez.txt.gz"
USER_AGENT = "biogrid-school-project/1.0 (python urllib)"
PER_PAGE = 10000


def get_json(url, retries=6):
    """GET url and parse JSON. Retries on errors, including connections that drop while reading."""
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=300) as resp:
                return json.loads(resp.read()), resp.headers
        except Exception as e:  # noqa: BLE001 - network errors of all kinds -> retry
            if attempt == retries - 1:
                sys.exit(f"Error: request to {url} failed {retries} times ({e}).")
            wait = 5 * (attempt + 1)
            print(f"    request failed ({e}), retrying in {wait}s ...", file=sys.stderr)
            time.sleep(wait)


def download_file(url, dest, retries=6):
    """Download url to dest. Resumes (HTTP Range) after dropped connections and checks the size."""
    for attempt in range(retries):
        have = os.path.getsize(dest) if os.path.exists(dest) else 0
        headers = {"User-Agent": USER_AGENT}
        if have:
            headers["Range"] = f"bytes={have}-"
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=300) as resp:
                if have and resp.status != 206:  # server ignored Range -> start over
                    have = 0
                length = resp.headers.get("Content-Length")
                expected = have + int(length) if length else None
                with open(dest, "ab" if have else "wb") as f:
                    while chunk := resp.read(1 << 20):
                        f.write(chunk)
            size = os.path.getsize(dest)
            if expected is None or size == expected:
                return
            print(f"    incomplete download ({size:,} of {expected:,} bytes), resuming ...", file=sys.stderr)
        except Exception as e:  # noqa: BLE001 - network errors of all kinds -> retry
            print(f"    download interrupted ({e}), resuming ...", file=sys.stderr)
        time.sleep(5 * (attempt + 1))
    sys.exit(f"Error: could not download {url} after {retries} attempts.")


def load_entrez_map(genomes, tmp_dir):
    """OMA ID (e.g. HUMAN00001) -> [Entrez IDs], only for the requested genomes (~55 MB download)."""
    print(f"==> Downloading OMA -> Entrez mapping (only keeping {', '.join(genomes)}) ...")
    gz_path = os.path.join(tmp_dir, "oma-entrez.txt.gz.part")
    download_file(ENTREZ_MAP_URL, gz_path)
    prefixes = tuple(genomes)
    mapping = {}
    try:
        with gzip.open(gz_path) as gz:
            for raw in gz:
                line = raw.decode("utf-8", "replace")
                if not line.startswith(prefixes):
                    continue
                oma_id, _, entrez = line.rstrip("\n").partition("\t")
                if entrez:
                    mapping.setdefault(oma_id, []).append(entrez)
    except (EOFError, OSError) as e:
        sys.exit(f"Error: the downloaded mapping file is corrupt ({e}). Please run the script again.")
    finally:
        os.remove(gz_path)
    print(f"    {len(mapping):,} proteins with Entrez IDs")
    return mapping


def fetch_pairs(g1, g2):
    url = f"{API}/pairs/{g1}/{g2}/?per_page={PER_PAGE}"
    page = 0
    while url:
        page += 1
        data, headers = get_json(url)
        total = headers.get("X-Total-Count", "?")
        link = headers.get("Link", "")
        print(f"    page {page}: {len(data):,} pairs (total {total})")
        yield from data
        m = re.search(r'<([^>]+)>;\s*rel="next"', link)
        url = m.group(1) if m else None


def write_pairs(out_dir, g1, g2, entrez):
    path = os.path.join(out_dir, f"OMA-Pairs-{g1}-{g2}.csv")
    tmp = path + ".part"
    print(f"==> Downloading orthologous pairs {g1} <-> {g2} ...")
    pairs = rows = 0
    with open(tmp, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow([
            f"Entrez Gene {g1}", f"Entrez Gene {g2}",
            f"OMA ID {g1}", f"OMA ID {g2}",
            f"Canonical ID {g1}", f"Canonical ID {g2}",
            "Orthology Type", "OMA Group", "Distance", "Score",
        ])
        for p in fetch_pairs(g1, g2):
            pairs += 1
            e1, e2 = p["entry_1"], p["entry_2"]
            ids1 = entrez.get(e1["omaid"]) or [""]
            ids2 = entrez.get(e2["omaid"]) or [""]
            for a in ids1:
                for b in ids2:
                    w.writerow([
                        a, b,
                        e1["omaid"], e2["omaid"],
                        e1.get("canonicalid", ""), e2.get("canonicalid", ""),
                        p.get("rel_type", ""), p.get("oma_group", "") or "",
                        p.get("distance", ""), p.get("score", ""),
                    ])
                    rows += 1
    os.replace(tmp, path)
    print(f"    {path}: {pairs:,} pairs -> {rows:,} rows")


def main():
    if len(sys.argv) < 4:
        sys.exit(__doc__)
    out_dir, base, others = sys.argv[1], sys.argv[2], sys.argv[3:]
    os.makedirs(out_dir, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp_dir:
        entrez = load_entrez_map([base] + others, tmp_dir)
    for other in others:
        write_pairs(out_dir, base, other, entrez)


if __name__ == "__main__":
    main()
