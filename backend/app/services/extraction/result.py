"""Contratto di estrazione: il modulo unico che possiede la shape del risultato.

ExtractionResult e FieldProvenance sono l'unica interface parlata da pipeline,
worker e API: la shape JSONB esiste solo come proiezione (to_jsonb) e la
ricostruzione come from_jsonb. Lo status del documento è derivato qui
(DocumentStatus + status_from_validation) e mai composto con literal sparsi.
"""

from __future__ import annotations

import enum
import math
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field

from app.models.payslip import PayslipDocument
from app.services.extraction.validation import run_validation

# Campi specchiati in colonne dedicate del documento (per analytics).
NUMERIC_FIELDS = ("gross_pay", "net_pay", "total_deductions")
INT_FIELDS = ("period_month", "period_year")


def coerce_correction_value(name: str, value: Any) -> Any:
    """Coerce a correction value (user or LLM) to the field's canonical type.

    User input and LLM responses arrive as untyped JSON payloads, so every
    correction passes through this gate before it can reach validation or
    the dedicated document columns. Integer fields (INT_FIELDS) accept only
    finite whole numbers, numeric fields (NUMERIC_FIELDS) only finite
    numbers, and both tolerate the Italian decimal comma. A ValueError with
    a clear message lets the caller decide whether to answer 422 (user
    input) or skip the field with a warning (malformed LLM response).

    Parameters
    ----------
    name : str
        Canonical field name (e.g. ``net_pay``, ``period_month``).
    value : Any
        Raw correction value; ``None`` is forwarded unchanged.

    Returns
    -------
    Any
        ``int`` for INT_FIELDS, ``float`` for NUMERIC_FIELDS, ``None``
        for ``None``, otherwise ``value`` unchanged.

    Raises
    ------
    ValueError
        If the value is a bool, non-numeric, non-finite (NaN/inf), or
        a non-integer number for an INT_FIELDS field.

    Dependencies
    -----------
    - result.INT_FIELDS / result.NUMERIC_FIELDS : field-type registry.

    Examples
    --------
    >>> coerce_correction_value("period_month", "9")
    9
    >>> coerce_correction_value("net_pay", "1234,56")
    1234.56
    >>> coerce_correction_value("net_pay", None) is None
    True
    """
    if value is None:
        return None
    if isinstance(value, bool):
        raise ValueError(f"{name}: valore non valido ({value!r})")
    if name in INT_FIELDS:
        try:
            number = float(str(value).strip().replace(",", "."))
        except ValueError:
            raise ValueError(f"{name}: valore non numerico ({value!r})") from None
        if not math.isfinite(number):  # float('nan')/float('inf') passerebbero
            raise ValueError(f"{name}: valore non numerico ({value!r})")
        if not number.is_integer():
            raise ValueError(f"{name} richiede un numero intero, ricevuto {value!r}")
        return int(number)
    if name in NUMERIC_FIELDS:
        try:
            number = float(str(value).strip().replace(",", "."))
        except ValueError:
            raise ValueError(f"{name}: valore non numerico ({value!r})") from None
        if not math.isfinite(number):
            raise ValueError(f"{name}: valore non numerico ({value!r})")
        return number
    return value


class DocumentStatus(enum.StrEnum):
    """Lifecycle status of a payslip Document.

    Single source of truth for the processing state of a Document, from
    upload to a terminal outcome. Pipeline, worker and API all derive
    their status from this enum, so no scattered string literals describe
    document state anywhere else in the codebase.

    Attributes
    ----------
    PENDING : str
        Uploaded, waiting for processing to start.
    PROCESSING : str
        Extraction is currently running.
    DONE : str
        Extraction finished and validation passed.
    NEEDS_REVIEW : str
        Validation failed; the result requires user or LLM corrections.
    NEEDS_OCR : str
        The PDF has no text layer; waiting for the future OCR component.
    FAILED : str
        Processing terminated with an unrecoverable error.

    Dependencies
    -----------
    - enum.StrEnum : string-valued enum base (serialises to JSON as-is).

    Examples
    --------
    >>> DocumentStatus.DONE.value
    'done'
    >>> DocumentStatus("needs_review") is DocumentStatus.NEEDS_REVIEW
    True
    """

    PENDING = "pending"
    PROCESSING = "processing"
    DONE = "done"
    NEEDS_REVIEW = "needs_review"
    NEEDS_OCR = "needs_ocr"
    FAILED = "failed"


def status_from_validation(passed: bool) -> DocumentStatus:
    """Derive the DocumentStatus from the outcome of validation.

    Maps a boolean validation outcome onto the two terminal extraction
    states: a passing report closes the document as DONE, a failing one
    parks it in NEEDS_REVIEW so corrections can be applied. Keeping this
    mapping in one place prevents the pipeline, worker and API from
    composing statuses independently.

    Parameters
    ----------
    passed : bool
        Whether the deterministic validation checks passed.

    Returns
    -------
    DocumentStatus
        ``DONE`` when ``passed`` is True, ``NEEDS_REVIEW`` otherwise.

    Dependencies
    -----------
    - result.DocumentStatus : target enum of the mapping.

    Examples
    --------
    >>> status_from_validation(True).value
    'done'
    >>> status_from_validation(False).value
    'needs_review'
    """
    return DocumentStatus.DONE if passed else DocumentStatus.NEEDS_REVIEW


class FieldProvenance(BaseModel):
    """Value of a canonical Field with provenance and confidence.

    Every extracted field (e.g. ``net_pay``, ``period_month``) carries not
    just a value but also how the value was obtained and how much it should
    be trusted. Confidence and the corrected flag drive the review flow:
    user corrections pin confidence to 1.0, LLM corrections lower it to
    0.7, and validation failures penalise uncorrected fields down to 0.3.

    Attributes
    ----------
    value : Any
        Extracted value; its type depends on the canonical field.
    confidence : float, optional
        Trust score in [0, 1]; the parser defaults to 0.9.
    source : str or None, optional
        Provenance of the value: the source line for parser output, or
        ``"llm"`` after an LLM correction.
    corrected : bool, optional
        True once a user has manually corrected the value.

    Methods
    -------
    parsed(value, source, confidence=0.9)
        Build a provenance from a parser match (classmethod).
    apply_user_correction(value)
        Overwrite the value and mark it user-corrected.
    apply_llm_correction(value)
        Overwrite the value from an LLM response.
    penalize()
        Cap confidence at 0.3 unless user-corrected.

    Dependencies
    -----------
    - pydantic.BaseModel : validation and JSON round-tripping.

    Examples
    --------
    >>> fp = FieldProvenance.parsed(1750.0, source="Netto a pagare 1.750,00")
    >>> (fp.value, fp.confidence, fp.corrected)
    (1750.0, 0.9, False)
    """

    value: Any
    confidence: float = 0.9
    source: str | None = None
    corrected: bool = False

    @classmethod
    def parsed(cls, value: Any, source: str | None, confidence: float = 0.9) -> FieldProvenance:
        """Build a FieldProvenance from a parser match.

        Convenience constructor used by the parsers: the value comes from
        a matched label/amount on a source line, so ``corrected`` starts
        False and the source line is preserved verbatim for traceability.

        Parameters
        ----------
        value : Any
            Extracted value.
        source : str or None
            Text of the source line the value was parsed from.
        confidence : float, optional
            Trust score; defaults to the parser's standard 0.9.

        Returns
        -------
        FieldProvenance
            New instance with ``corrected`` left False.

        Dependencies
        -----------
        - pydantic.BaseModel : constructor machinery.

        Examples
        --------
        >>> FieldProvenance.parsed(9, source="Periodo: 09/2026").value
        9
        """
        return cls(value=value, confidence=confidence, source=source)

    def apply_user_correction(self, value: Any) -> None:
        """Apply a manual correction supplied by the user.

        A user correction is authoritative by definition: the value is
        replaced, confidence is pinned to 1.0 and the field is flagged as
        corrected so later validation penalties no longer apply to it.

        Parameters
        ----------
        value : Any
            Corrected value, already coerced by the caller via
            ``coerce_correction_value``.

        Returns
        -------
        None

        Examples
        --------
        >>> fp = FieldProvenance(value=100.0)
        >>> fp.apply_user_correction(125.0)
        >>> (fp.value, fp.confidence, fp.corrected)
        (125.0, 1.0, True)
        """
        self.value = value
        self.confidence = 1.0
        self.corrected = True

    def apply_llm_correction(self, value: Any) -> None:
        """Apply a targeted correction from the LLM gateway.

        LLM answers are useful but not authoritative: the value replaces
        the current one, confidence is set to 0.7 (below the parser's
        default), the corrected flag is cleared and the source is marked
        as ``"llm"`` so the UI can distinguish the provenance.

        Parameters
        ----------
        value : Any
            Corrected value, already coerced by the caller via
            ``coerce_correction_value``.

        Returns
        -------
        None

        Examples
        --------
        >>> fp = FieldProvenance(value=100.0, source="Netto 100,00")
        >>> fp.apply_llm_correction(110.0)
        >>> (fp.value, fp.confidence, fp.source)
        (110.0, 0.7, 'llm')
        """
        self.value = value
        self.confidence = 0.7
        self.corrected = False
        self.source = "llm"

    def penalize(self) -> None:
        """Lower confidence after a validation failure.

        Uncorrected fields implicated in a failed check are capped at
        confidence 0.3 so the frontend surfaces them as unreliable.
        User-corrected fields are exempt: their value is authoritative and
        must not be demoted by a failing arithmetic check.

        Parameters
        ----------
        None

        Returns
        -------
        None

        Examples
        --------
        >>> fp = FieldProvenance(value=100.0)
        >>> fp.penalize()
        >>> fp.confidence
        0.3
        >>> fp.apply_user_correction(100.0)
        >>> fp.penalize()
        >>> fp.confidence
        1.0
        """
        if not self.corrected:
            self.confidence = min(self.confidence, 0.3)


class Issue(BaseModel):
    """Problem detected by validation, with a suggested remediation action.

    Each deterministic check that fails emits an Issue naming the
    offending field (when identifiable), the check that caught the
    problem, a human readable message and the recommended action:
    ``"user"`` asks for a manual correction in the UI, ``"llm"`` asks for
    a targeted request to the LLM gateway.

    Attributes
    ----------
    field : str or None, optional
        Canonical field name involved, or None for document-wide checks.
    check : str
        Identifier of the failed check (e.g. ``net_consistency``).
    message : str
        Human readable description of the problem.
    action : str
        Suggested remediation: ``"user"`` (manual fix) or ``"llm"``
        (targeted gateway request).

    Dependencies
    -----------
    - pydantic.BaseModel : validation and JSON round-tripping.

    Examples
    --------
    >>> issue = Issue(check="net_consistency", message="mismatch", action="user")
    >>> issue.action
    'user'
    """

    field: str | None = None
    check: str
    message: str
    action: str  # "user" (correzione manuale) | "llm" (richiesta mirata)


class ValidationSummary(BaseModel):
    """Aggregated outcome of the deterministic validation checks.

    Compact rollup persisted inside the JSONB projection so the API and
    the frontend can tell at a glance whether a result is trustworthy and
    how many problems were found, without scanning the full issue list.

    Attributes
    ----------
    passed : bool, optional
        True when no errors were reported (warnings are allowed).
    error_count : int, optional
        Number of blocking issues.
    warning_count : int, optional
        Number of non-blocking issues.

    Dependencies
    -----------
    - pydantic.BaseModel : validation and JSON round-tripping.

    Examples
    --------
    >>> ValidationSummary().passed
    False
    >>> ValidationSummary(passed=True, error_count=0, warning_count=1).warning_count
    1
    """

    passed: bool = False
    error_count: int = 0
    warning_count: int = 0


class Entry(BaseModel):
    """A payslip line item recognised in the earnings/deductions table.

    Cedolini lay out their line items in two columns: spettanze
    (earnings) and trattenute (deductions). The parser attributes each
    amount to the closer column header and records the row's payroll
    code and description alongside the classified amount.

    Attributes
    ----------
    code : str or None, optional
        Payroll code of the item (1-4 digits), if printed on the row.
    description : str or None, optional
        Free-text description of the item, taken from the row.
    amount : float
        Monetary amount of the item.
    entry_type : str
        ``"spettanza"`` (earning) or ``"trattenuta"`` (deduction).

    Dependencies
    -----------
    - pydantic.BaseModel : validation and JSON round-tripping.

    Examples
    --------
    >>> Entry(amount=1500.0, entry_type="spettanza").amount
    1500.0
    """

    code: str | None = None
    description: str | None = None
    amount: float
    entry_type: str  # "spettanza" | "trattenuta"


class ExtractionResult(BaseModel):
    """Typed contract of a document extraction.

    The single interface spoken by pipeline, worker, API and (in Phase 2)
    the frontend: canonical fields with provenance, recognised entries,
    validation issues and the derived status. The JSONB shape exists only
    as a projection (``to_jsonb``) with reconstruction via ``from_jsonb``
    and ``from_document``; ``template`` and ``raw_text`` live exclusively
    in dedicated document columns and are re-attached by ``from_document``
    so correction routes never lose them across PATCHes.

    Attributes
    ----------
    template : str or None, optional
        Detected payroll software layout signature, if any.
    doc_type : str, optional
        ``"cedolino"`` (monthly payslip) or ``"cu"`` (annual
        certificate); selects parser behaviour and validation rules.
    fields : dict of str to FieldProvenance, optional
        Canonical fields keyed by name (e.g. ``net_pay``).
    entries : list of Entry, optional
        Recognised payslip line items.
    issues : list of Issue, optional
        Problems found by validation, with suggested actions.
    validation : ValidationSummary, optional
        Aggregated outcome of the deterministic checks.
    status : DocumentStatus, optional
        Lifecycle status derived from validation.
    raw_text : str, optional
        Raw text layer of the source PDF.

    Methods
    -------
    from_jsonb(data)
        Rebuild the result from its JSONB projection (classmethod).
    from_document(doc)
        Rebuild the full result from the Document ORM row (classmethod).
    revalidate()
        Re-run validation and refresh issues/validation/status.
    apply_user_correction(corrections)
        Apply manual user corrections, then revalidate.
    apply_llm_corrections(corrections)
        Apply LLM corrections, then revalidate.
    issue_fields()
        Sorted list of field names referenced by issues.
    column_values()
        Values for the dedicated columns of the Document.
    to_jsonb()
        JSONB projection persisted on the Document.

    Dependencies
    -----------
    - pydantic.BaseModel : validation and (de)serialisation.
    - validation.run_validation : deterministic checks behind revalidate.

    Examples
    --------
    >>> result = ExtractionResult(doc_type="cedolino")
    >>> result.status.value
    'pending'
    >>> sorted(result.to_jsonb())
    ['entries', 'fields', 'issues', 'validation']
    """

    template: str | None = None
    doc_type: str = "cedolino"  # cedolino | cu: guida parser e validazione
    fields: dict[str, FieldProvenance] = Field(default_factory=dict)
    entries: list[Entry] = Field(default_factory=list)
    issues: list[Issue] = Field(default_factory=list)
    validation: ValidationSummary = Field(default_factory=ValidationSummary)
    status: DocumentStatus = DocumentStatus.PENDING
    raw_text: str = ""

    @classmethod
    def from_jsonb(cls, data: dict | None) -> ExtractionResult:
        """Rebuild the result from its JSONB projection.

        Inverse of ``to_jsonb``: rebuilds the nested FieldProvenance,
        Entry, Issue and ValidationSummary models from the plain dicts
        stored in the Document's ``extraction`` JSONB column. Missing
        keys degrade to defaults, so partially populated projections
        from earlier phases still load.

        Parameters
        ----------
        data : dict or None
            JSONB projection; None and missing keys are tolerated.

        Returns
        -------
        ExtractionResult
            Reconstructed result. ``template``, ``raw_text`` and
            ``doc_type`` keep their defaults because they are not part
            of the projection; use ``from_document`` for those.

        Dependencies
        -----------
        - result.FieldProvenance / Entry / Issue / ValidationSummary :
          nested model reconstruction.

        Examples
        --------
        >>> ExtractionResult.from_jsonb(
        ...     {"validation": {"passed": True}}).validation.passed
        True
        >>> ExtractionResult.from_jsonb(None).fields
        {}
        """
        data = data or {}
        return cls(
            template=data.get("template"),
            fields={k: FieldProvenance(**v) for k, v in (data.get("fields") or {}).items()},
            entries=[Entry(**e) for e in (data.get("entries") or [])],
            issues=[Issue(**i) for i in (data.get("issues") or [])],
            validation=ValidationSummary(**(data.get("validation") or {})),
        )

    @classmethod
    def from_document(cls, doc: PayslipDocument) -> ExtractionResult:
        """Reconstruct the full result from a Document ORM row.

        ``template``, ``raw_text`` and ``doc_type`` live only in the
        dedicated columns of PayslipDocument, never in the JSONB
        projection. This classmethod re-attaches them after rebuilding
        the JSONB part, so every correction route that round-trips a
        result through ``apply_to_document`` preserves them across
        PATCHes.

        Parameters
        ----------
        doc : PayslipDocument
            ORM row holding the JSONB projection plus the dedicated
            ``template``, ``raw_text`` and ``doc_type`` columns.

        Returns
        -------
        ExtractionResult
            Complete result: JSONB fields, entries, issues and
            validation, plus template, raw_text and doc_type recovered
            from the dedicated columns.

        Dependencies
        -----------
        - ExtractionResult.from_jsonb : JSONB reconstruction.

        Examples
        --------
        >>> from types import SimpleNamespace
        >>> doc = SimpleNamespace(
        ...     extraction={"validation": {"passed": True}},
        ...     template="zucchetti", raw_text="Netto 100,00",
        ...     doc_type="cedolino")
        >>> result = ExtractionResult.from_document(doc)
        >>> (result.template, result.doc_type)
        ('zucchetti', 'cedolino')
        """
        result = cls.from_jsonb(doc.extraction)
        result.template = doc.template
        result.raw_text = doc.raw_text or ""
        result.doc_type = doc.doc_type or "cedolino"
        return result

    def revalidate(self) -> None:
        """Re-run validation on the current fields and refresh the result.

        Runs the deterministic checks, penalises the confidence of every
        uncorrected field implicated in an issue, and replaces issues,
        validation summary and status. Called after every correction (user
        or LLM) so the stored result always reflects the latest field
        values.

        Parameters
        ----------
        None

        Returns
        -------
        None

        Dependencies
        -----------
        - validation.run_validation : deterministic checks.
        - result.Issue / ValidationSummary / status_from_validation :
          issue mapping and status derivation.

        Examples
        --------
        >>> result = ExtractionResult()
        >>> result.revalidate()
        >>> result.status.value
        'needs_review'
        """
        report = run_validation(self.fields, self.entries, self.doc_type)
        issues = report["errors"] + report["warnings"]
        for issue in issues:
            field_name = issue.get("field")
            if field_name and field_name in self.fields:
                self.fields[field_name].penalize()
        self.issues = [Issue(**issue) for issue in issues]
        self.validation = ValidationSummary(
            passed=report["passed"],
            error_count=report["error_count"],
            warning_count=report["warning_count"],
        )
        self.status = status_from_validation(report["passed"])

    def apply_user_correction(self, corrections: dict[str, Any]) -> None:
        """Apply manual user corrections, then revalidate.

        Delegates each correction to
        ``FieldProvenance.apply_user_correction`` (value replaced,
        confidence pinned to 1.0, corrected flag set), then revalidates
        so issues, summary and status reflect the corrected values.

        Parameters
        ----------
        corrections : dict of str to Any
            Field name to corrected value; values are expected to be
            already coerced via ``coerce_correction_value``.

        Returns
        -------
        None

        Dependencies
        -----------
        - FieldProvenance.apply_user_correction : per-field correction.
        - ExtractionResult._apply : shared correction loop.

        Examples
        --------
        >>> result = ExtractionResult(
        ...     fields={"net_pay": FieldProvenance(value=100.0)})
        >>> result.apply_user_correction({"net_pay": 125.0})
        >>> result.fields["net_pay"].corrected
        True
        """
        self._apply(corrections, FieldProvenance.apply_user_correction)

    def apply_llm_corrections(self, corrections: dict[str, Any]) -> None:
        """Apply targeted LLM corrections, then revalidate.

        Delegates each correction to
        ``FieldProvenance.apply_llm_correction`` (value replaced,
        confidence set to 0.7, source marked ``"llm"``), then
        revalidates so issues, summary and status reflect the corrected
        values.

        Parameters
        ----------
        corrections : dict of str to Any
            Field name to corrected value; values are expected to be
            already coerced via ``coerce_correction_value``.

        Returns
        -------
        None

        Dependencies
        -----------
        - FieldProvenance.apply_llm_correction : per-field correction.
        - ExtractionResult._apply : shared correction loop.

        Examples
        --------
        >>> result = ExtractionResult(
        ...     fields={"net_pay": FieldProvenance(value=100.0)})
        >>> result.apply_llm_corrections({"net_pay": 110.0})
        >>> (result.fields["net_pay"].value, result.fields["net_pay"].source)
        (110.0, 'llm')
        """
        self._apply(corrections, FieldProvenance.apply_llm_correction)

    def _apply(self, corrections: dict[str, Any], apply_method: Any) -> None:
        """Shared correction loop behind the user and LLM routes.

        For each (name, value) pair the field is fetched - or created on
        the fly when missing - the supplied per-field correction method
        is applied, and the updated FieldProvenance is written back. A
        single revalidate at the end keeps the common behaviour of both
        correction routes in one place.

        Parameters
        ----------
        corrections : dict of str to Any
            Field name to corrected value.
        apply_method : Any
            Unbound FieldProvenance method performing the per-field
            correction (user or LLM flavour).

        Returns
        -------
        None

        Dependencies
        -----------
        - result.FieldProvenance : field creation when absent.
        - ExtractionResult.revalidate : post-correction refresh.

        Examples
        --------
        >>> result = ExtractionResult()
        >>> result._apply({"net_pay": 100.0},
        ...              FieldProvenance.apply_user_correction)
        >>> result.fields["net_pay"].value
        100.0
        """
        for name, value in corrections.items():
            field_value = self.fields.get(name) or FieldProvenance(value=value)
            apply_method(field_value, value)
            self.fields[name] = field_value
        self.revalidate()

    def issue_fields(self) -> list[str]:
        """Field names referenced by the current issues.

        Collects the distinct, non-None ``field`` values across all
        issues and returns them sorted, so the frontend can highlight
        exactly the inputs that need attention.

        Parameters
        ----------
        None

        Returns
        -------
        list of str
            Sorted unique field names referenced by issues; empty when
            no issue names a field.

        Examples
        --------
        >>> result = ExtractionResult(issues=[
        ...     Issue(field="net_pay", check="c", message="m", action="user"),
        ...     Issue(field="net_pay", check="c", message="m", action="user")])
        >>> result.issue_fields()
        ['net_pay']
        """
        return sorted({issue.field for issue in self.issues if issue.field})

    def column_values(self) -> dict[str, Any]:
        """Values for the dedicated columns of PayslipDocument.

        Projects the mirrored numeric fields (NUMERIC_FIELDS) into
        Decimal instances - the type of the ORM columns - and the period
        integers as-is, so ``apply_to_document`` can persist them with
        no further conversion. Missing fields map to None.

        Parameters
        ----------
        None

        Returns
        -------
        dict of str to Any
            Keys ``gross_pay``, ``net_pay`` and ``total_deductions``
            (Decimal or None) plus ``period_month`` and ``period_year``
            (int or None).

        Dependencies
        -----------
        - result.NUMERIC_FIELDS : mirrored numeric field registry.
        - decimal.Decimal : column-compatible numeric type.

        Examples
        --------
        >>> result = ExtractionResult(
        ...     fields={"net_pay": FieldProvenance(value=100.0)})
        >>> result.column_values()["net_pay"]
        Decimal('100.0')
        """
        values: dict[str, Any] = {}
        for name in NUMERIC_FIELDS:
            field_value = self.fields.get(name)
            value = field_value.value if field_value else None
            values[name] = Decimal(str(value)) if isinstance(value, int | float) else None
        values["period_month"] = self._field_value("period_month")
        values["period_year"] = self._field_value("period_year")
        return values

    def _field_value(self, name: str) -> Any:
        """Return the raw value of a single field.

        Parameters
        ----------
        name : str
            Canonical field name.

        Returns
        -------
        Any
            The field's value, or None when the field is missing.

        Examples
        --------
        >>> r = ExtractionResult(fields={"net_pay": FieldProvenance(value=1.0)})
        >>> r._field_value("net_pay")
        1.0
        """
        field_value = self.fields.get(name)
        return field_value.value if field_value else None

    def to_jsonb(self) -> dict[str, Any]:
        """Project the result onto its persisted JSONB shape.

        Only fields, entries, issues and validation are included: the
        shape is unchanged since Phase 1. ``template``, ``raw_text``
        and ``doc_type`` are deliberately excluded because they live in
        dedicated document columns.

        Parameters
        ----------
        None

        Returns
        -------
        dict of str to Any
            JSON-serialisable projection with keys ``fields``,
            ``entries``, ``issues`` and ``validation``.

        Dependencies
        -----------
        - pydantic.BaseModel.model_dump : serialisation engine.

        Examples
        --------
        >>> sorted(ExtractionResult().to_jsonb())
        ['entries', 'fields', 'issues', 'validation']
        """
        return self.model_dump(
            include={"fields", "entries", "issues", "validation"},
        )


def apply_to_document(doc: PayslipDocument, result: ExtractionResult) -> None:
    """Project the result onto the Document ORM row.

    Single owner of the persistence projection: writes the JSONB
    extraction, syncs the dedicated columns (template, raw_text,
    period, mirrored numerics as Decimal) and derives the document
    status. The worker, PATCH /fields and POST /llm-resolve all go
    through this seam, so a result can never be persisted partially.

    Parameters
    ----------
    doc : PayslipDocument
        ORM row to update in place.
    result : ExtractionResult
        Result to project; its ``to_jsonb`` shape and column values
        are written onto the row.

    Returns
    -------
    None

    Dependencies
    -----------
    - ExtractionResult.to_jsonb / column_values : projections.
    - result.NUMERIC_FIELDS : mirrored numeric columns.

    Examples
    --------
    >>> from types import SimpleNamespace
    >>> doc = SimpleNamespace(extraction=None, template=None, status=None,
    ...                       period_month=None, period_year=None, net_pay=None)
    >>> apply_to_document(doc, ExtractionResult(fields={}))
    >>> doc.status
    'pending'
    """
    doc.template = result.template
    doc.raw_text = result.raw_text or None
    doc.extraction = result.to_jsonb()
    values = result.column_values()
    for field_name in NUMERIC_FIELDS:
        setattr(doc, field_name, values[field_name])
    doc.period_month = values["period_month"]
    doc.period_year = values["period_year"]
    doc.status = result.status.value
