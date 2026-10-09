import pytest
from app.services.extraction.cu import parse_cu
from app.services.extraction.pipeline import run_extraction
from app.services.extraction.text_layer import Line, Word


def _lines(*texts: str) -> list[Line]:
    lines = []
    for y, text in enumerate(texts):
        words = [
            Word(text=t, x0=i * 10.0, y0=float(y), x1=i * 10.0 + 8, y1=y + 1.0, page=0)
            for i, t in enumerate(text.split())
        ]
        lines.append(Line(page=0, y=float(y), words=words))
    return lines


def test_cu_extraction_is_done(cu_pdf):
    result = run_extraction(cu_pdf, doc_type="cu")
    assert result.status == "done", result.issues
    assert result.template is None
    assert result.fields["gross_pay"].value == 25000.0
    assert result.fields["total_deductions"].value == 5000.0
    assert result.fields["net_pay"].value == 20000.0
    assert result.fields["period_year"].value == 2025
    assert "period_month" not in result.fields


@pytest.mark.parametrize(
    "label",
    [
        "Anno di riferimento: 2024",
        "Anno 2024",
        "Anno imposta 2024",
        "Anno di imposta 2024",
        "Anno d'imposta 2024",
        "Anno d’imposta 2024",
        "Periodo d'imposta 2024",
    ],
)
def test_parse_cu_year_label_variants(label):
    fields, entries = parse_cu(_lines(label))
    assert fields["period_year"].value == 2024
    assert entries == []
