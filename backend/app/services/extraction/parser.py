"""Parser a regole per cedolini italiani (label-based, generico).

Produce campi canonici con confidenza e riga sorgente, più le voci di paga
(spettanze/trattenute) riconosciute dalle colonne della tabella.
"""

from __future__ import annotations

import re
from typing import Any

from app.services.extraction.result import NUMERIC_FIELDS, FieldProvenance
from app.services.extraction.text_layer import Line

AMOUNT_PATTERN = r"\d{1,3}(?:\.\d{3})*,\d{2}"
_AMOUNT_RE = re.compile(rf"^{AMOUNT_PATTERN}$")
_CODE_RE = re.compile(r"^\d{1,4}$")

# Ordine dei totali: prima le etichette specifiche, poi quelle generiche
# ("Netto" da solo matcherebbe anche "Netto imponibile").
_TOTAL_LABELS: dict[str, list[str]] = {
    "gross_pay": [
        r"(?i:(?:totale\s+)?compenso\s+lordo)",
        r"(?i:retribuzione\s+lorda)",
        r"(?i:lordo\s+di\s+paga)",
        r"(?i:totale\s+lordo)",
    ],
    "total_deductions": [
        r"(?i:totale(?:\s+delle)?\s+trattenute)",
        r"(?i:somma\s+trattenute)",
    ],
    "net_pay": [
        r"(?i:netto\s+(?:da|a)\s+pagare)",
        r"(?i:netto\s+in\s+busta)",
        r"(?i:(?:totale\s+)?netto)",  # generica, in coda
    ],
}

_TEXT_LABELS: dict[str, str] = {
    "company_name": r"(?i:azienda|datore\s+di\s+lavoro|ragione\s+sociale)",
    "employee_name": r"(?i:dipendente|lavoratore)",
    "matricola": r"(?i:matricola)",
}

_FISCAL_CODE_RE = re.compile(
    r"(?i:codice\s+fiscale)\s*:?\s*([A-Z]{6}\d{2}[A-Z]\d{2}[A-Z]\d{3}[A-Z])"
)
_PERIOD_RE = re.compile(r"(?i:periodo\s+di\s+paga|competenza)\s*:?\s*(\d{1,2})\s*/\s*(\d{2,4})")

_ENTRIES_STOP_RE = re.compile(
    r"(?i:compenso\s+lordo|totale\s+lordo|retribuzione\s+lorda|lordo\s+di\s+paga"
    r"|totale(?:\s+delle)?\s+trattenute|somma\s+trattenute"
    r"|netto\s+(?:da|a)\s+pagare|netto\s+in\s+busta|(?:totale\s+)?netto)"
)


def parse_amount(raw: str) -> float:
    """Converte un importo italiano ('1.234,56' / '250,00') in float."""
    return float(raw.replace(".", "").replace(",", "."))


def _field_value(value: Any, line: Line, confidence: float = 0.9) -> FieldProvenance:
    return FieldProvenance.parsed(value, source=line.text, confidence=confidence)


def _parse_total_fields(lines: list[Line], fields: dict[str, dict[str, Any]]) -> None:
    for name in NUMERIC_FIELDS:
        for label in _TOTAL_LABELS[name]:
            pattern = re.compile(label + r"\s*:?\s*(" + AMOUNT_PATTERN + r")")
            for line in lines:
                if name in fields:
                    break
                match = pattern.search(line.text)
                if match:
                    fields[name] = _field_value(parse_amount(match.group(1)), line)
    for name in NUMERIC_FIELDS:
        if name not in fields:
            generic = re.compile(_TOTAL_LABELS[name][-1] + r"\s*:?\s*(" + AMOUNT_PATTERN + r")")
            for line in lines:
                match = generic.search(line.text)
                if match:
                    fields[name] = _field_value(parse_amount(match.group(1)), line)
                    break


def _parse_simple_fields(lines: list[Line], fields: dict[str, dict[str, Any]]) -> None:
    for line in lines:
        if "fiscal_code" not in fields:
            match = _FISCAL_CODE_RE.search(line.text)
            if match:
                fields["fiscal_code"] = _field_value(match.group(1), line)
        if "period_month" not in fields:
            match = _PERIOD_RE.search(line.text)
            if match:
                month = int(match.group(1))
                year = int(match.group(2))
                if year < 100:
                    year += 2000
                fields["period_month"] = _field_value(month, line)
                fields["period_year"] = _field_value(year, line)
        for name, label in _TEXT_LABELS.items():
            if name in fields:
                continue
            match = re.search(label + r"\s*:?\s*(\S.*)", line.text)
            if match:
                fields[name] = _field_value(match.group(1).strip(), line)


def _parse_entries(lines: list[Line]) -> list[dict[str, Any]]:
    """Riconosce le voci di paga dalle colonne 'Spettanze'/'Trattenute'."""
    header_idx, col_spett_x, col_tratt_x = None, None, None
    for i, line in enumerate(lines):
        by_text = {w.text.lower(): w for w in line.words}
        if "spettanze" in by_text and "trattenute" in by_text:
            header_idx = i
            col_spett_x = by_text["spettanze"].center_x
            col_tratt_x = by_text["trattenute"].center_x
            break
    if header_idx is None:
        return []

    entries: list[dict[str, Any]] = []
    for line in lines[header_idx + 1 :]:
        if _ENTRIES_STOP_RE.search(line.text):
            break
        amounts: list[tuple[str, float]] = []
        for word in line.words:
            if _AMOUNT_RE.fullmatch(word.text):
                distance_spett = abs(word.center_x - col_spett_x)
                distance_tratt = abs(word.center_x - col_tratt_x)
                entry_type = "spettanza" if distance_spett <= distance_tratt else "trattenuta"
                amounts.append((entry_type, parse_amount(word.text)))
        if not amounts:
            continue

        code_word = next((w for w in line.words if _CODE_RE.fullmatch(w.text)), None)
        description_words = [
            w.text for w in line.words if w is not code_word and not _AMOUNT_RE.fullmatch(w.text)
        ]
        # esclude l'etichetta di colonna ripetuta sulla riga, se presente
        description = " ".join(
            t for t in description_words if t.lower() not in ("spettanze", "trattenute")
        )
        for entry_type, amount in amounts:
            entries.append(
                {
                    "code": code_word.text if code_word else None,
                    "description": description or None,
                    "amount": amount,
                    "entry_type": entry_type,
                }
            )
    return entries


def parse_payslip(
    lines: list[Line],
) -> tuple[dict[str, FieldProvenance], list[dict[str, Any]]]:
    """Parsing completo: restituisce (campi, voci)."""
    fields: dict[str, dict[str, Any]] = {}
    _parse_simple_fields(lines, fields)
    _parse_total_fields(lines, fields)
    entries = _parse_entries(lines)
    return fields, entries
