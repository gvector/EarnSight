// «Netto per mese»: una barra per cedolino (mensilità aggiuntive più strette),
// cliccabile per scegliere il mese mostrato nella frase in evidenza.
import type { DocumentSummary } from "../api";
import { eur, MONTHS, period } from "../format";

export function NetChart({
  payslips,
  selectedId,
  onSelect,
}: {
  payslips: DocumentSummary[]; // ordine cronologico, già filtrati (con netto)
  selectedId: string | null;
  onSelect: (id: string) => void;
}) {
  const max = Math.max(...payslips.map((d) => Number(d.net_pay)), 1);
  // due cedolini con stesso periodo (es. 13ª e 14ª a dicembre): il nome del file li distingue
  const names = payslips.map((d) => `${period(d)}: ${eur(Number(d.net_pay))}`);
  const label = (i: number) =>
    names.indexOf(names[i]!) !== names.lastIndexOf(names[i]!) ? `${names[i]} (${payslips[i]!.filename})` : names[i]!;
  return (
    <figure className="chart">
      <figcaption>Netto per mese</figcaption>
      <div className="chart-bars" role="group" aria-label="Netto per mese">
        {payslips.map((doc, i) => {
          const net = Number(doc.net_pay);
          const short = doc.period_month ? MONTHS[doc.period_month - 1]?.slice(0, 3) : "?";
          return (
            <button
              key={doc.id}
              type="button"
              className={`bar${doc.additional_payment ? " bar-extra" : ""}`}
              aria-pressed={doc.id === selectedId}
              aria-label={label(i)}
              title={label(i)}
              onClick={() => onSelect(doc.id)}
            >
              <span className="bar-fill" style={{ height: `${Math.max((net / max) * 100, 2)}%` }} />
              <span className="bar-label">{doc.additional_payment ? "agg." : short}</span>
            </button>
          );
        })}
      </div>
    </figure>
  );
}
