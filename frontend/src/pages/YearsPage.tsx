import { useEffect, useState } from "react";
import { Link } from "react-router";
import { api, type DocumentSummary, type YearCu, type YearSummary } from "../api";
import { Notice } from "../components/ui";
import { capitalize, eur, MONTHS, period } from "../format";
import { useDocuments } from "../state";

const shortMonth = (month: number | null) => (month ? MONTHS[month - 1]!.slice(0, 3) : "?");

/** [1,2,3,6] → "gen–mar, giu": le serie consecutive si comprimono. */
function monthRuns(months: number[]): string {
  const runs: number[][] = [];
  for (const m of [...months].sort((a, b) => a - b)) {
    const last = runs[runs.length - 1];
    if (last && m === last[last.length - 1]! + 1) last.push(m);
    else runs.push([m]);
  }
  return runs
    .map((r) => (r.length > 1 ? `${shortMonth(r[0]!)}–${shortMonth(r[r.length - 1]!)}` : r.map(shortMonth).join(", ")))
    .join(", ");
}

function heading(year: YearSummary): string {
  const parts = [String(year.year)];
  if (year.template) parts.push(capitalize(year.template));
  parts.push(year.employer_tax_code ? `datore ${year.employer_tax_code}` : "datore sconosciuto");
  return parts.join(" · ");
}

function DocLinks({ ids, documents }: { ids: string[]; documents: DocumentSummary[] | null }) {
  return (
    <>
      {ids.map((id, i) => {
        const doc = documents?.find((d) => d.id === id);
        return (
          <span key={id}>
            {i > 0 && ", "}
            <Link to={`/documenti/${id}`}>{doc ? capitalize(period(doc)) : "documento"}</Link>
          </span>
        );
      })}
    </>
  );
}

function CuLine({ cu, lastMonth }: { cu: YearCu | null; lastMonth: string | undefined }) {
  if (!cu) return <p className="muted">Nessuna CU per quest'anno: è facoltativa, puoi caricarla da Panoramica</p>;
  const open = <Link to={`/documenti/${cu.id}`}>Apri la CU</Link>;
  switch (cu.status) {
    case "match":
      return <Notice tone="ok">La CU combacia con i progressivi del cedolino di {lastMonth}</Notice>;
    case "mismatch":
      return (
        <Notice tone="error">
          La CU non combacia: imponibile {eur(cu.taxable_diff)}, IRPEF {eur(cu.tax_diff)} {open}
        </Notice>
      );
    case "no_payslips":
      return <p className="muted">Nessun cedolino di quest'anno da confrontare con la CU</p>;
    case "no_fiscal_data":
      return <p className="muted">I cedolini non hanno i dati fiscali: rielaborali</p>;
    case "to_review":
      return (
        <Notice tone="warn">
          La CU è da controllare {open}
        </Notice>
      );
  }
}

function YearCard({ year, documents }: { year: YearSummary; documents: DocumentSummary[] | null }) {
  const { totals, completeness } = year;
  const rows: [string, string | null][] = [
    ["Lordo", totals.gross_pay],
    ["Netto", totals.net_pay],
    ["Trattenute", totals.total_deductions],
    ["Imponibile IRPEF", totals.taxable_income],
    ["IRPEF trattenuta", totals.income_tax],
  ];
  const last = year.payslips[year.payslips.length - 1];
  const lastMonth = last?.month ? MONTHS[last.month - 1] : undefined;
  return (
    <section className="panel" aria-labelledby={`anno-${year.year}-${year.employer_tax_code ?? "x"}`}>
      <h2 id={`anno-${year.year}-${year.employer_tax_code ?? "x"}`}>{heading(year)}</h2>
      <p>
        {year.payslips.map((p, i) => (
          <span key={p.id}>
            {i > 0 && " "}
            <Link to={`/documenti/${p.id}`}>
              {p.additional_payment ? `+ agg. ${shortMonth(p.month)}` : shortMonth(p.month)}
            </Link>
          </span>
        ))}
      </p>
      {year.missing_months.length > 0 && (
        <Notice tone="warn">Mancano {monthRuns(year.missing_months)}: carica i cedolini per completare l'anno</Notice>
      )}
      <dl className="facts">
        {rows
          .filter(([, v]) => v !== null)
          .map(([label, v]) => (
            <div key={label}>
              <dt>{label}</dt>
              <dd>{eur(v)}</dd>
            </div>
          ))}
      </dl>
      <p className="muted small">somma dei cedolini caricati</p>
      {completeness.status === "complete" && <p>Cedolini completi: le somme dei mesi tornano con i progressivi</p>}
      {completeness.status === "incomplete" && (
        <p>
          Mancano cedolini: rispetto ai progressivi mancano {eur(completeness.taxable_diff)} di imponibile e{" "}
          {eur(completeness.tax_diff)} di IRPEF
        </p>
      )}
      {completeness.status === "no_fiscal_data" && <p>I cedolini non hanno i dati fiscali: rielaborali</p>}
      <CuLine cu={year.cu} lastMonth={lastMonth} />
      {year.duplicates.length > 0 && (
        <p>
          Caricati due volte, conta il più recente: <DocLinks ids={year.duplicates} documents={documents} />
        </p>
      )}
      {year.to_review.length > 0 && (
        <p>
          Da controllare, esclusi dai conti: <DocLinks ids={year.to_review} documents={documents} />
        </p>
      )}
    </section>
  );
}

export function YearsPage() {
  const { documents } = useDocuments();
  const [years, setYears] = useState<YearSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  // si ricarica a ogni cambio della lista documenti (caricamento, correzione, rielaborazione)
  useEffect(() => {
    let current = true;
    api.years().then(
      (list) => {
        if (!current) return;
        setYears(list);
        setError(null);
      },
      (e: unknown) => {
        if (current) setError(e instanceof Error ? e.message : String(e));
      },
    );
    return () => {
      current = false;
    };
  }, [documents]);

  return (
    <>
      <h1>Anni</h1>
      {error && <Notice tone="error">{error}</Notice>}
      {years === null && !error && <p className="muted">Caricamento…</p>}
      {years?.length === 0 && <p className="muted">Nessun anno da mostrare: carica i cedolini per vedere totali e verifiche.</p>}
      {years?.map((y) => <YearCard key={`${y.year}-${y.employer_tax_code ?? ""}`} year={y} documents={documents} />)}
    </>
  );
}
