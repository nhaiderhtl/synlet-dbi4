# Analyse: Synthetische Letalität bei Mensch, Ratte und *E. coli*

**Notebook:** [`synthetic_lethality_analyse.ipynb`](synthetic_lethality_analyse.ipynb). Erklärt Schritt für Schritt
(mit Diagrammen), wie man SL in den BioGRID-Daten findet, wie die SL-Gene pro Spezies verteilt sind,
in welchen Zelllinien beim Menschen gemessen wurde und ob/wie sich SL auf den Menschen übertragen lässt.

## Ausführen

```bash
./install.sh                                  # BioGRID-Daten laden (einmalig)
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/jupyter nbconvert --to notebook --execute --inplace analysis/synthetic_lethality_analyse.ipynb
```

(oder das Notebook in IntelliJ / VS Code / Jupyter öffnen und mit dem `.venv`-Interpreter ausführen)

## Ergebnisse in `results/`

| Datei | Inhalt |
|---|---|
| `spezies_ueberblick.csv` | Interaktionen, SL und negative genetische Interaktionen pro Spezies |
| `mensch_sl_gene.csv` | alle menschlichen SL-Gene mit Anzahl SL-Partner |
| `mensch_zelllinien.csv` | Zelllinien, in denen SL beim Menschen gemessen wurde |
| `ecoli_sl_kandidaten.csv` | *E. coli*-Genpaare mit negativer genetischer Interaktion, Score ≤ −20 |
| `ratte_testbare_sl_paare.csv` | menschliche SL-Paare, deren Gene (per Symbol) auch in den Ratten-Daten vorkommen |
| `ecoli_mensch_namensgleiche_gene.csv` | *E. coli*-Gene mit gleichnamigem menschlichem SL-Gen (inkl. Einordnung) |

## Kernergebnisse

- **Mensch:** 2.255 SL-Einträge, 2.219 Genpaare, 1.954 Gene; fast nur in Krebszelllinien gemessen, kaum Wiederholungen.
- ***E. coli*:** keine expliziten SL, aber 25.813 starke negative genetische Interaktionen (SL-Kandidaten, 848 Gene).
- **Ratte:** keine SL-Daten in BioGRID; SL ist für die Ratte mit diesen Daten nicht bestimmbar.
- Abbildung auf den Menschen bisher nur über Gensymbole, echte Orthologie-Daten fehlen noch (siehe `../TODO.md`).
