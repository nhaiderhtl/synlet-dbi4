#!/usr/bin/env bash
#
# Removes the data downloaded by ./install.sh.
#
# Only files that install.sh creates are deleted. Anything else in the data folders (e.g. your own
# "modified_..." copies) is kept, and a folder is only removed once it is empty.
#
# Usage:  ./clean.sh        (lists what will be deleted and asks for confirmation)
#         ./clean.sh -y     (no confirmation)

set -euo pipefail
shopt -s nullglob

cd "$(dirname "$0")"

# Must match what install.sh writes.
FILES=(
    BIOGRID-SYSTEM-LATEST.tab3/BIOGRID-SYSTEM-Synthetic_Lethality-*.tab3.txt.csv
    BIOGRID-ORGANISM-*.mitab/BIOGRID-ORGANISM-Rattus_norvegicus-*.mitab.txt.csv
    BIOGRID-ORGANISM-*.mitab/BIOGRID-ORGANISM-Escherichia_coli_K12*.mitab.txt.csv
    BIOGRID-ORGANISM-*.mitab/BIOGRID-ORGANISM-Homo_sapiens-*.mitab.txt.csv
    OMA-Orthology/OMA-Pairs-*.csv
    OMA-Orthology/*.part
    Essentiality/G-HumanEssential.tsv
)
DIRS=(BIOGRID-SYSTEM-LATEST.tab3 BIOGRID-ORGANISM-*.mitab OMA-Orthology Essentiality)

# keep only paths that exist (non-glob entries like the .tsv stay in the list even when missing)
existing=()
for f in "${FILES[@]}"; do [[ -e "$f" ]] && existing+=("$f"); done
FILES=("${existing[@]}")

if [[ ${#FILES[@]} -eq 0 ]]; then
    echo "Nothing to clean."
    exit 0
fi

echo "These downloaded files will be deleted:"
du -ch "${FILES[@]}" | sed 's/^/    /'

if [[ "${1:-}" != "-y" ]]; then
    read -r -p "Continue? [y/N] " answer
    [[ "$answer" == [yYjJ]* ]] || { echo "Aborted."; exit 1; }
fi

rm -f -- "${FILES[@]}"

for d in "${DIRS[@]}"; do
    [[ -d "$d" ]] || continue
    if rmdir -- "$d" 2>/dev/null; then
        echo "Removed $d/"
    else
        echo "Kept    $d/ (contains files not created by install.sh):"
        for f in "$d"/*; do echo "            $f"; done
    fi
done

echo "Done. Run ./install.sh to download everything again."
