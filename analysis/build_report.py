"""Erzeugt den HTML-Bericht aus den Notebook-Ergebnissen.

Ablauf: erst das Notebook ausführen (schreibt results/report_data.json), dann:
    .venv/bin/python analysis/build_report.py
"""
from pathlib import Path

HERE = Path(__file__).resolve().parent
data = (HERE / "results" / "report_data.json").read_text(encoding="utf-8")
template = (HERE / "report_template.html").read_text(encoding="utf-8")
html = template.replace("__DATA__", data.replace("</", "<\\/"))
out = HERE / "synthetic_lethality_bericht.html"
out.write_text(html, encoding="utf-8")
print("geschrieben:", out)
