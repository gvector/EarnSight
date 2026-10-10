"""Extraction pipeline: text extraction → template detection → parsing → validation.

Orchestrates the whole extraction of a document and returns an
``ExtractionResult``, the typed contract defined in ``result.py``. The
``doc_type`` decides the parser: ``"cu"`` goes to the CU parser, while for
payslips the detected template picks the per-template parser from the
``TEMPLATE_PARSERS`` registry, with the generic parser as fallback. Every
page gets a role (``templates.classify_pages``): only ``cedolino`` pages are
parsed, so an attendance sheet bundled in the PDF is tracked but ignored. CU
pages get ``cu`` or ``copia`` (``cu.classify_cu_pages``): the copy for the
recipient repeats the original and is never read.

PDFs without a usable text layer short-circuit to the ``needs_ocr`` status:
OCR is a future component, so the pipeline only reports the issue instead of
attempting a scan conversion.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from app.services.extraction.cu import classify_cu_pages, parse_cu
from app.services.extraction.parser import parse_payslip
from app.services.extraction.result import (
    DocumentStatus,
    Entry,
    ExtractionResult,
    Issue,
    ValidationSummary,
)
from app.services.extraction.templates import classify_pages, detect_template
from app.services.extraction.text_layer import Line, extract_lines, has_text_layer, page_count
from app.services.extraction.zucchetti import parse_zucchetti

DOC_TYPES = ("cedolino", "cu")

# Registry per-template: detect_template sceglie il parser da qui, fallback
# generico. TeamSystem si aggiunge quando arrivano cedolini reali da tarare.
TEMPLATE_PARSERS: dict[str, Callable[[list[Line]], tuple[dict, list[dict]]]] = {
    "zucchetti": parse_zucchetti,
}


def get_parser(template: str | None) -> Callable[[list[Line]], tuple[dict, list[dict]]]:
    """Return the parser registered for a template, generic as fallback.

    Parameters
    ----------
    template : str or None
        Template signature produced by ``detect_template``.

    Returns
    -------
    Callable
        Parser with the ``parse_payslip`` contract:
        ``list[Line] -> (fields, entries)``.

    Examples
    --------
    >>> get_parser(None) is parse_payslip
    True
    """
    return TEMPLATE_PARSERS.get(template or "generic", parse_payslip)


def run_extraction(pdf_path: Path, doc_type: str = "cedolino") -> ExtractionResult:
    """Run the full extraction pipeline on a payslip or CU PDF.

    Decision flow: first the PDF is checked for a text layer — without one
    the document is marked ``needs_ocr`` with a user-facing issue (OCR is a
    future component) and no parsing is attempted. Otherwise the text lines
    are extracted with their coordinates and the ``doc_type`` selects the
    parser: ``"cu"`` tags the recipient's copy pages ``copia`` and parses
    the ``cu`` pages only with ``parse_cu``, with no template, while
    ``"cedolino"`` fingerprints the layout via ``detect_template`` and picks
    the per-template parser from the ``TEMPLATE_PARSERS`` registry, falling
    back to the generic parser. The assembled result is finally
    revalidated: deterministic arithmetic checks produce issues, the
    validation summary and the derived status.

    Parameters
    ----------
    pdf_path : Path
        Path to the stored PDF document.
    doc_type : str, optional
        Document type: ``"cedolino"`` (default) or ``"cu"``. Guides the
        parser choice and the validation rules (the CU has its own checks).

    Returns
    -------
    ExtractionResult
        The typed extraction contract: fields, entries, issues, validation
        and status, including ``raw_text`` and the detected ``template``
        for payslips.

    Raises
    ------
    ValueError
        If ``doc_type`` is not one of ``DOC_TYPES``.

    Dependencies
    -----------
    - text_layer.has_text_layer, text_layer.extract_lines : PDF text-layer
      check and coordinate-aware line extraction via PyMuPDF.
    - templates.detect_template : layout fingerprinting of the payslip.
    - templates.classify_pages : page roles (cedolino / presenze / vuota).
    - pipeline.get_parser : template-to-parser registry lookup with the
      generic parser as fallback.
    - cu.classify_cu_pages : CU page roles (cu / copia).
    - cu.parse_cu : CU parser on the ministerial form.
    - result.ExtractionResult.revalidate : deterministic validation and
      status derivation.

    Examples
    --------
    >>> from pathlib import Path
    >>> result = run_extraction(Path("payslip.pdf"), doc_type="cedolino")
    >>> result.status
    <DocumentStatus.DONE: 'done'>
    >>> result = run_extraction(Path("scan.pdf"), doc_type="cu")
    >>> result.status
    <DocumentStatus.NEEDS_OCR: 'needs_ocr'>
    """
    if doc_type not in DOC_TYPES:
        raise ValueError(f"doc_type non valido: {doc_type!r} (attesi: {DOC_TYPES})")
    if not has_text_layer(pdf_path):
        return ExtractionResult(
            doc_type=doc_type,
            status=DocumentStatus.NEEDS_OCR,
            issues=[
                Issue(
                    check="text_layer",
                    message="Nessun layer di testo: richiesto OCR (componente futura)",
                    action="user",
                )
            ],
            validation=ValidationSummary(passed=False, error_count=1),
        )

    lines = extract_lines(pdf_path)
    full_text = "\n".join(line.text for line in lines)

    if doc_type == "cu":
        pages = classify_cu_pages(lines, page_count(pdf_path))
        fields, entries = parse_cu([line for line in lines if pages[line.page] == "cu"])
        template = None
    else:
        pages = classify_pages(lines, page_count(pdf_path))
        payslip_lines = [line for line in lines if pages[line.page] == "cedolino"]
        template = detect_template(full_text)
        fields, entries = get_parser(template)(payslip_lines)

    result = ExtractionResult(
        doc_type=doc_type,
        template=template,
        pages=pages,
        fields=fields,
        entries=[Entry(**entry) for entry in entries],
        raw_text=full_text,
    )
    result.revalidate()
    return result
