"""Payroll software template detection via layout fingerprints.

Every payroll software (Zucchetti, Ranocchi, TeamSystem, ...) embeds a recognizable
signature in the text of the payslips it generates. This module fingerprints
a document by scanning its full text for the case-insensitive marker strings
registered in ``TEMPLATES``; the ``"generic"`` template in ``GENERIC_TEMPLATE``
is always the fallback when no marker set matches, so unknown layouts still
get parsed by the generic payslip parser.

Markers are pure data: onboarding a new template means adding one entry to
the ``TEMPLATES`` registry (in code or via configuration), with no change to
``detect_template`` itself.
"""

from __future__ import annotations

from app.services.extraction.text_layer import Line

TEMPLATES: dict[str, list[str]] = {
    # marker case-insensitive; il template "generic" è sempre il fallback
    "zucchetti": ["zucchetti"],
    # firma «Ranocchi Software» nel testo ruotato a margine: mai come frase intera
    "ranocchi": ["ranocchi"],
    "teamsystem": ["teamsystem"],
}
GENERIC_TEMPLATE = "generic"


def detect_template(text: str) -> str:
    """Detect the payroll software template from the document's full text.

    Fingerprints the layout by matching case-insensitive marker strings: a
    template matches only when ALL of its markers appear in ``text``, which
    keeps detection robust against boilerplate words shared across vendors.
    The ``"generic"`` registry entry itself is skipped, so it always remains
    the fallback rather than a candidate.

    Parameters
    ----------
    text : str
        Full text of the PDF, typically the newline-joined extracted lines.

    Returns
    -------
    str
        Name of the first template whose markers all match, or
        ``GENERIC_TEMPLATE`` (``"generic"``) when no registered marker set
        matches.

    Dependencies
    -----------
    - templates.TEMPLATES : marker registry mapping template names to the
      characteristic strings of each payroll software layout.

    Examples
    --------
    >>> detect_template("Cedolino Zucchetti del mese di gennaio")
    'zucchetti'
    >>> detect_template("Unknown payroll software layout")
    'generic'
    """
    lowered = text.lower()
    for name, markers in TEMPLATES.items():
        if name == GENERIC_TEMPLATE or not markers:
            continue
        if all(marker.lower() in lowered for marker in markers):
            return name
    return GENERIC_TEMPLATE


# Ruoli di pagina: alcuni software paghe (Zucchetti) antepongono al cedolino un
# foglio presenze, con il «periodo di riferimento» delle variabili (il mese
# precedente). Tutto ciò che non è presenze è trattato come cedolino.
_ATTENDANCE_MARKERS = ("timbrature", "giustificativi")


def classify_pages(lines: list[Line], page_count: int) -> list[str]:
    """Assign a role to every PDF page: ``cedolino``, ``presenze`` or ``vuota``.

    The attendance sheet ("presenze") is recognised by its column headers
    (TIMBRATURE and GIUSTIFICATIVI); a page with no text is ``vuota``;
    any other page is a payslip page. The pipeline parses only
    ``cedolino`` pages, so the attendance sheet's period never leaks into
    the payslip fields.

    Parameters
    ----------
    lines : list of Line
        Text lines of the whole document, as from ``extract_lines``.
    page_count : int
        Number of pages in the PDF (pages without text produce no lines).

    Returns
    -------
    list of str
        One role per page, in page order.

    Examples
    --------
    >>> classify_pages([], 1)
    ['vuota']
    """
    texts = [""] * page_count
    for line in lines:
        texts[line.page] += " " + line.text.lower()
    roles = []
    for text in texts:
        if not text.strip():
            roles.append("vuota")
        elif all(marker in text for marker in _ATTENDANCE_MARKERS):
            roles.append("presenze")
        else:
            roles.append("cedolino")
    return roles
