#!/usr/bin/env bash
#
# Downloads all data files this project needs (BioGRID, OMA orthology, essentiality).
#
# Our species: Rattus norvegicus, Escherichia coli K-12 (all K12 strains) and Homo sapiens.
#
#   1. Synthetic lethality: BIOGRID-SYSTEM-LATEST.tab3.zip     -> only the Synthetic_Lethality file
#   2. Interactions:        BIOGRID-ORGANISM-4.4.225.mitab.zip -> only the files for our organisms
#   3. Orthology:           OMA pairs Homo sapiens <-> Rattus norvegicus / E. coli K-12 (MG1655), CSV with
#                           Entrez Gene IDs (the ID BioGRID uses) -- done by oma_pairs.py
#   4. Essentiality:        G-HumanEssential.tsv (SNAP BioData)
#
# Only the needed files are extracted; the zips are deleted afterwards.
# BioGRID files get a ".csv" suffix appended (like the old txt_to_csv.sh); they stay TAB-separated.
#
# Usage:  ./install.sh            (run from anywhere; files land next to this script)
#         ./install.sh --force    (re-download even if the files already exist)
#
# Requirements: curl or wget, unzip, gzip, python3.  ~400 MB download, ~1.1 GB on disk (Homo sapiens alone is ~1 GB).

set -euo pipefail

BASE_URL="https://downloads.thebiogrid.org/Download/BioGRID"
# NOTE: the "/File/..." links on the website are HTML pages; the real zips live under "/Download/...".

SYSTEM_URL="$BASE_URL/Latest-Release/BIOGRID-SYSTEM-LATEST.tab3.zip"
SYSTEM_DIR="BIOGRID-SYSTEM-LATEST.tab3"
SYSTEM_PATTERNS=(
    "BIOGRID-SYSTEM-Synthetic_Lethality-*.tab3.txt"   # version number changes with each release
)

ORGANISM_VERSION="4.4.225"
ORGANISM_URL="$BASE_URL/Release-Archive/BIOGRID-$ORGANISM_VERSION/BIOGRID-ORGANISM-$ORGANISM_VERSION.mitab.zip"
ORGANISM_DIR="BIOGRID-ORGANISM-$ORGANISM_VERSION.mitab"
ORGANISM_PATTERNS=(
    "BIOGRID-ORGANISM-Rattus_norvegicus-*.mitab.txt"
    "BIOGRID-ORGANISM-Escherichia_coli_K12*.mitab.txt"   # K12, K12_MC4100_BW2952, K12_MG1655, K12_W3110
    "BIOGRID-ORGANISM-Homo_sapiens-*.mitab.txt"
)

# OMA genome codes (https://omabrowser.org/api/genome/<CODE>/). ECOLI = E. coli K-12 substr. MG1655.
OMA_DIR="OMA-Orthology"
OMA_BASE_GENOME="HUMAN"
OMA_OTHER_GENOMES=(RATNO ECOLI)

ESSENTIAL_URL="https://snap.stanford.edu/biodata/datasets/10033/files/G-HumanEssential.tsv.gz"
ESSENTIAL_DIR="Essentiality"
ESSENTIAL_FILE="G-HumanEssential.tsv"

FORCE=0
[[ "${1:-}" == "--force" || "${1:-}" == "-f" ]] && FORCE=1

cd "$(dirname "$0")"

# --- helpers ---------------------------------------------------------------

die() { echo "Error: $*" >&2; exit 1; }

for tool in unzip gzip python3; do
    command -v "$tool" >/dev/null 2>&1 || die "'$tool' is not installed."
done
if command -v curl >/dev/null 2>&1; then
    download() { curl -fL --retry 3 --progress-bar -o "$2" "$1"; }
elif command -v wget >/dev/null 2>&1; then
    download() { wget -q --show-progress -O "$2" "$1"; }
else
    die "neither 'curl' nor 'wget' is installed."
fi

TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

# already_present DIR PATTERN...  -> true if every pattern has a matching .csv file in DIR
already_present() {
    local dir="$1"; shift
    local p
    for p in "$@"; do
        compgen -G "$dir/$p.csv" >/dev/null || return 1
    done
}

# fetch NAME URL DIR PATTERN...
fetch() {
    local name="$1" url="$2" dir="$3"; shift 3

    if [[ $FORCE -eq 0 ]] && already_present "$dir" "$@"; then
        echo "==> $name: already present in $dir/ (use --force to re-download)"
        return
    fi

    local zip="$TMP_DIR/$name.zip"
    echo "==> Downloading $name ..."
    download "$url" "$zip"
    unzip -tq "$zip" >/dev/null 2>&1 || die "$url did not return a valid zip file."

    echo "==> Extracting needed files into $dir/ ..."
    mkdir -p "$dir"
    local extract="$TMP_DIR/$name"
    mkdir -p "$extract"
    unzip -o -j -q "$zip" "$@" -d "$extract" || die "expected files not found in $name.zip"

    local f
    for f in "$extract"/*; do
        mv -f "$f" "$dir/$(basename "$f").csv"
        echo "    $dir/$(basename "$f").csv"
    done
    rm -rf "$zip" "$extract"
}

# --- main ------------------------------------------------------------------

fetch "BIOGRID-SYSTEM-LATEST.tab3" "$SYSTEM_URL" "$SYSTEM_DIR" "${SYSTEM_PATTERNS[@]}"
fetch "BIOGRID-ORGANISM-$ORGANISM_VERSION.mitab" "$ORGANISM_URL" "$ORGANISM_DIR" "${ORGANISM_PATTERNS[@]}"

# Orthology (OMA)
oma_done=1
for g in "${OMA_OTHER_GENOMES[@]}"; do
    [[ -f "$OMA_DIR/OMA-Pairs-$OMA_BASE_GENOME-$g.csv" ]] || oma_done=0
done
if [[ $FORCE -eq 0 && $oma_done -eq 1 ]]; then
    echo "==> OMA orthology: already present in $OMA_DIR/ (use --force to re-download)"
else
    python3 -I oma_pairs.py "$OMA_DIR" "$OMA_BASE_GENOME" "${OMA_OTHER_GENOMES[@]}"
fi

# Essentiality
if [[ $FORCE -eq 0 && -f "$ESSENTIAL_DIR/$ESSENTIAL_FILE" ]]; then
    echo "==> Essentiality: already present in $ESSENTIAL_DIR/ (use --force to re-download)"
else
    echo "==> Downloading essentiality data ..."
    mkdir -p "$ESSENTIAL_DIR"
    download "$ESSENTIAL_URL" "$TMP_DIR/$ESSENTIAL_FILE.gz"
    gzip -dc "$TMP_DIR/$ESSENTIAL_FILE.gz" > "$TMP_DIR/$ESSENTIAL_FILE"
    mv -f "$TMP_DIR/$ESSENTIAL_FILE" "$ESSENTIAL_DIR/$ESSENTIAL_FILE"
    echo "    $ESSENTIAL_DIR/$ESSENTIAL_FILE"
fi

echo "==> Done."
