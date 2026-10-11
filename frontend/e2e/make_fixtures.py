"""Rigenera i PDF sintetici degli E2E (dati inventati: layout Zucchetti e CU dei test).

Dalla root: .venv/bin/python frontend/e2e/make_fixtures.py
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "tests"), str(ROOT / "backend")]
from conftest import build_cu_pdf, build_zucchetti_pdf  # noqa: E402

OUT = Path(__file__).parent / "fixtures"
build_zucchetti_pdf(
    OUT / "cedolino-aprile.pdf", period="Aprile 2026", attendance_period="Marzo 2026"
)
build_zucchetti_pdf(OUT / "cedolino-maggio-incoerente.pdf", period="Maggio 2026", net="1.500,00")
build_zucchetti_pdf(OUT / "quattordicesima-giugno.pdf", period="Giugno 2026 AGG.")
build_cu_pdf(OUT / "cu-2025.pdf")
(OUT / "non-un-pdf.pdf").write_bytes(b"<html>non sono un PDF</html>")
print("\n".join(sorted(p.name for p in OUT.iterdir())))
