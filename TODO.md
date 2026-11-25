# TODO

## Orthologie-Daten für die Abbildung auf den Menschen

Die Analyse in `analysis/synthetic_lethality_analyse.ipynb` bildet Gene von Ratte und *E. coli* bisher nur
über **gleiche Gensymbole** auf den Menschen ab. Das ist bei der Ratte ein grober Behelf und bei *E. coli*
praktisch unbrauchbar (z.B. `ada` ≠ `ADA`, `recA` ↔ `RAD51` wird nicht gefunden).

- [ ] `install.sh` um Orthologie-Downloads erweitern (Dateien nicht committen, wie die BioGRID-Daten):
  - [ ] Ratte ↔ Mensch: NCBI `gene_orthologs.gz` (https://ftp.ncbi.nlm.nih.gov/gene/DATA/gene_orthologs.gz),
        gefiltert auf Taxonomie-IDs 10116 und 9606, Abgleich über Entrez-Gene-IDs
  - [ ] *E. coli* K-12 ↔ Mensch: paarweise Orthologe aus dem OMA-Browser (oder eggNOG)
- [ ] Abschnitt 7 und 8 des Notebooks mit echten Orthologen statt Gensymbolen neu rechnen
- [ ] Danach prüfen: Welche *E. coli*-SL-Kandidaten (Score ≤ −20) sind auch beim Menschen als SL bekannt?

## Optional

- [ ] Gen-Essentialität beim Menschen (z.B. DepMap) ergänzen, um "allein schon letale" Gene auszusortieren
- [ ] SL-Datei (BioGRID 5.0.x) und Organismus-Dateien (4.4.225) auf dieselbe BioGRID-Version bringen
