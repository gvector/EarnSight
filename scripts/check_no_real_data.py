"""Verifica che nessun dato dei cedolini reali (example_ced/) finisca nei file versionabili.

Estrae dai PDF reali importi, numeri lunghi, codice fiscale, IBAN e i nomi letti dal
parser (dipendente, azienda, codice dipendente), poi li cerca in ogni file
che git committerebbe (modificati + nuovi non ignorati), PDF di prova compresi.
Esce con 1 se trova qualcosa. Senza example_ced/ non c'è nulla da confrontare: esce 0.

Uso: .venv/bin/python scripts/check_no_real_data.py   (o `make privacy-check`)
"""

import re
import subprocess
import sys
from pathlib import Path

import pymupdf

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))
EXAMPLES = ROOT / "example_ced"
# Valori pubblici o standard che compaiono in ogni cedolino Zucchetti: non sono personali.
PUBLIC = {"26,00000", "9,19000", "1,55000", "8,00", "0,26667", "0,30000", "100,00000"}
# numeri lunghi (posizioni INPS, P.IVA), codice fiscale, IBAN
IDENTIFIER = re.compile(r"\d{7,}|[A-Z]{6}\d{2}[A-Z]\d{2}[A-Z]\d{3}[A-Z]|IT\d{2}[A-Z0-9]{20,}")
VOCE_CODE = re.compile(r"^[0-9A-Z]{6}$")  # codici voce Zucchetti (000014, ZP9960): standard


def real_tokens() -> set[str]:
    """Valori personali dei cedolini reali: importi, numeri lunghi, CF, IBAN, nomi."""
    from app.services.extraction.pipeline import run_extraction

    tokens: set[str] = set()
    for pdf in EXAMPLES.glob("*.pdf"):
        for page in pymupdf.open(pdf):
            for word in page.get_text("words"):
                text = word[4]
                if re.fullmatch(r"\d{1,3}(\.\d{3})*,\d{2,5}", text):
                    tokens.add(text)
                    plain = text.replace(".", "")
                    if len(plain.split(",")[0]) >= 4:  # 2.468,00 → anche 2468,00 e 2468.00
                        tokens.update({plain, plain.replace(",", ".")})
                elif IDENTIFIER.fullmatch(text):
                    tokens.add(text)
        fields = run_extraction(pdf).fields
        for name in ("employee_name", "company_name", "employee_code", "matricola"):
            value = fields.get(name)
            if value and isinstance(value.value, str):
                tokens.update(w for w in re.split(r"[\s.]+", value.value) if len(w) >= 4)
    return {t for t in tokens - PUBLIC if not VOCE_CODE.match(t)}


def versionable_files() -> list[Path]:
    out = subprocess.run(
        ["git", "ls-files", "--modified", "--others", "--exclude-standard", "--cached"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.split()
    names = sorted(set(out))
    return [ROOT / f for f in names if (ROOT / f).is_file() and not f.endswith("package-lock.json")]


def main() -> int:
    if not EXAMPLES.is_dir():
        print("example_ced/ assente: niente da confrontare")
        return 0
    tokens = real_tokens()
    hits: dict[str, set[str]] = {}
    files = versionable_files()
    for path in files:
        text = path.read_bytes().decode("latin-1", errors="ignore")
        for token in tokens:
            if re.search(r"(?<![\d.,A-Za-z])" + re.escape(token) + r"(?![\d,A-Za-z])", text, re.I):
                hits.setdefault(token, set()).add(str(path.relative_to(ROOT)))
    print(f"{len(files)} file controllati contro {len(tokens)} valori reali")
    for token, where in sorted(hits.items()):
        print(f"  TROVATO {token!r} in {sorted(where)}")
    return 1 if hits else 0


if __name__ == "__main__":
    sys.exit(main())
