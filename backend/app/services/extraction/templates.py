"""Payroll software template detection via layout fingerprints.

Every payroll software (Zucchetti, TeamSystem, ...) embeds a recognizable
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

TEMPLATES: dict[str, list[str]] = {
    # marker case-insensitive; il template "generic" è sempre il fallback
    "zucchetti": ["zucchetti"],
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
