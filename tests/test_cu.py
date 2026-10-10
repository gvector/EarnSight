import pytest
from app.services.extraction import pipeline
from app.services.extraction.cu import parse_cu
from app.services.extraction.pipeline import run_extraction
from app.services.extraction.text_layer import Line, Word
from conftest import build_cu_pdf


def _lines(*texts: str) -> list[Line]:
    lines = []
    for y, text in enumerate(texts):
        words = [
            Word(text=t, x0=i * 10.0, y0=float(y), x1=i * 10.0 + 8, y1=y + 1.0, page=0)
            for i, t in enumerate(text.split())
        ]
        lines.append(Line(page=0, y=float(y), words=words))
    return lines


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


def _cu(tmp_path, **kwargs):
    path = tmp_path / "cu.pdf"
    build_cu_pdf(path, **kwargs)
    return run_extraction(path, doc_type="cu")


def test_cu_extraction_is_done(tmp_path):
    result = _cu(tmp_path)
    v = {k: f.value for k, f in result.fields.items()}
    assert result.status == "done", result.issues
    assert result.template is None
    assert v == {"period_year": 2025, "taxable_income": 25000.0, "income_tax": 5000.0,
                 "employer_tax_code": "01234567890"}  # fmt: skip
    assert result.pages == ["cu", "cu", "cu", "copia", "copia"]


def test_copy_pages_are_never_read(tmp_path):
    result = _cu(tmp_path, copy_point1="99.999,00")
    assert result.fields["taxable_income"].value == 25000.0


def test_parser_receives_only_cu_pages(tmp_path, monkeypatch):
    # l'originale precede la copia: senza questa spia leggere anche la copia
    # non cambierebbe i valori, quindi il filtro non sarebbe verificato
    seen = set()

    def spy(lines):
        seen.update(line.page for line in lines)
        return parse_cu(lines)

    monkeypatch.setattr(pipeline, "parse_cu", spy)
    _cu(tmp_path)
    assert seen == {0, 1, 2}


def test_empty_point_gives_absent_field(tmp_path):
    result = _cu(tmp_path, point21=None)
    assert "income_tax" not in result.fields
    assert result.status == "needs_review"
    assert any(i.field == "income_tax" and i.check == "missing_field" for i in result.issues)


def test_cu_has_no_payslip_totals(tmp_path):
    result = _cu(tmp_path)
    assert not {"gross_pay", "net_pay", "total_deductions"} & set(result.fields)
    assert all(i.field not in ("gross_pay", "net_pay", "total_deductions") for i in result.issues)


def test_taxable_income_adds_fixed_term_employment(tmp_path):
    # punto 1 (tempo indeterminato) + punto 2 (tempo determinato): stesso reddito di lavoro
    result = _cu(tmp_path, point2="3.000,00")
    assert result.fields["taxable_income"].value == 28000.0
    assert result.status == "done", result.issues


def test_fixed_term_employment_alone(tmp_path):
    result = _cu(tmp_path, point1=None, point2="3.000,00")
    assert result.fields["taxable_income"].value == 3000.0
