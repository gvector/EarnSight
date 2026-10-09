// Panoramica: quanto hai ricevuto (mese scelto nel grafico), carica, ultimi documenti.
import { useState } from "react";
import { Link } from "react-router";
import type { DocumentSummary } from "../api";
import { NetChart } from "../components/NetChart";
import { UploadPanel } from "../components/UploadPanel";
import { DocumentsTable, Notice, StatusBadge } from "../components/ui";
import { byPeriodDesc, eur, MONTHS } from "../format";
import { useDocuments } from "../state";

const CHART_MONTHS = 12;

/** «Ad agosto 2026 hai ricevuto» / «Con la mensilità aggiuntiva di giugno 2026 hai ricevuto». */
export function receivedSentence(doc: DocumentSummary): string {
  const month = MONTHS[(doc.period_month ?? 1) - 1] ?? "";
  if (doc.additional_payment) return `Con la mensilità aggiuntiva di ${month} ${doc.period_year} hai ricevuto`;
  return `${month.startsWith("a") ? "Ad" : "A"} ${month} ${doc.period_year} hai ricevuto`;
}

function Hero({ doc }: { doc: DocumentSummary }) {
  return (
    <div className="hero-text">
      <h1 className="hero-sentence">{receivedSentence(doc)}</h1>
      <p className="hero-amount">{eur(doc.net_pay)}</p>
      <dl className="breakdown">
        <div>
          <dt>Lordo</dt>
          <dd>{eur(doc.gross_pay)}</dd>
        </div>
        <div>
          <dt>Trattenute</dt>
          <dd>{eur(doc.total_deductions)}</dd>
        </div>
      </dl>
      <p className="hero-status">
        <StatusBadge status={doc.status} /> <Link to={`/documenti/${doc.id}`}>Apri il cedolino</Link>
      </p>
    </div>
  );
}

export function OverviewPage() {
  const { documents, error } = useDocuments();
  const [selectedId, setSelectedId] = useState<string | null>(null);

  if (error) return <Notice tone="error">{error}</Notice>;
  if (documents === null) return <p className="muted">Caricamento…</p>;

  const payslips = documents
    .filter((d) => d.doc_type === "cedolino" && d.net_pay !== null && d.period_month && d.period_year)
    .sort(byPeriodDesc)
    .slice(0, CHART_MONTHS)
    .reverse(); // cronologico, dal più vecchio
  const selected = payslips.find((d) => d.id === selectedId) ?? payslips.at(-1);

  return (
    <>
      {selected ? (
        <section className="hero" aria-label="Netto ricevuto">
          <Hero doc={selected} />
          {payslips.length > 1 && <NetChart payslips={payslips} selectedId={selected.id} onSelect={setSelectedId} />}
        </section>
      ) : (
        <section className="hero hero-empty">
          <h1>Benvenuto in EarnSight</h1>
          <p>Carica il primo cedolino in PDF: lo leggiamo, controlliamo i conti e ti mostriamo quanto hai ricevuto.</p>
        </section>
      )}

      <div className="columns">
        <UploadPanel />
        <section aria-labelledby="recent-title">
          <h2 id="recent-title">Ultimi documenti</h2>
          {documents.length === 0 ? (
            <p className="muted">Nessun documento ancora.</p>
          ) : (
            <>
              <DocumentsTable documents={[...documents].sort(byPeriodDesc).slice(0, 6)} />
              <Link to="/documenti">Tutti i documenti</Link>
            </>
          )}
        </section>
      </div>
    </>
  );
}
