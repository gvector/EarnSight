// Dettaglio di un documento: riepilogo, campi da correggere (a mano o con l'LLM), voci, dati letti.
import { useCallback, useEffect, useState, type FormEvent } from "react";
import { Link, useParams } from "react-router";
import { api, type DocumentDetail, type Entry, type Issue, type LlmSettings } from "../api";
import { Notice, StatusBadge } from "../components/ui";
import { BUSY, capitalize, eur, parseAmount, parseInteger, period } from "../format";
import { POLL_MS, useDocuments } from "../state";

export const FIELD_LABELS: Record<string, string> = {
  gross_pay: "Lordo",
  total_deductions: "Trattenute",
  rounding: "Arrotondamento",
  net_pay: "Netto",
  period_month: "Mese (1–12)",
  period_year: "Anno",
  company_name: "Azienda",
  employee_name: "Dipendente",
  employee_code: "Codice dipendente",
  matricola: "Matricola",
  fiscal_code: "Codice fiscale",
};
const AMOUNT_FIELDS = ["gross_pay", "total_deductions", "rounding", "net_pay"];
const INTEGER_FIELDS = ["period_month", "period_year"];
const IDENTITY_FIELDS = ["company_name", "employee_name", "employee_code", "matricola", "fiscal_code"];

/** Valore digitato → valore da inviare all'API (numero per importi e interi). */
export function toCorrection(field: string, raw: string): string | number {
  if (AMOUNT_FIELDS.includes(field)) return parseAmount(raw);
  if (INTEGER_FIELDS.includes(field)) return parseInteger(raw);
  return raw.trim();
}

function asInput(field: string, value: unknown): string {
  if (value === null || value === undefined) return "";
  if (AMOUNT_FIELDS.includes(field) && typeof value === "number")
    return value.toLocaleString("it-IT", { minimumFractionDigits: 2, maximumFractionDigits: 2, useGrouping: "always" });
  return String(value);
}

function CorrectionForm({
  doc,
  issues,
  llm,
  onChanged,
}: {
  doc: DocumentDetail;
  issues: Issue[];
  llm: LlmSettings | null;
  onChanged: (doc: DocumentDetail, message: string) => void;
}) {
  const fields = [...new Set(issues.map((i) => i.field).filter((f): f is string => !!f))];
  const current = doc.extraction?.fields ?? {};
  const [values, setValues] = useState<Record<string, string>>(() =>
    Object.fromEntries(fields.map((f) => [f, asInput(f, current[f]?.value)])),
  );
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<"save" | "llm" | null>(null);

  const save = async (event: FormEvent) => {
    event.preventDefault();
    setError(null);
    const corrections: Record<string, string | number> = {};
    try {
      for (const field of fields) {
        if ((values[field] ?? "").trim() !== "") corrections[field] = toCorrection(field, values[field] ?? "");
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      return;
    }
    if (Object.keys(corrections).length === 0) {
      setError("Inserisci almeno un valore da correggere.");
      return;
    }
    setBusy("save");
    try {
      onChanged(await api.correct(doc.id, corrections), "Correzioni salvate.");
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(null);
    }
  };

  const askLlm = async () => {
    setError(null);
    setBusy("llm");
    try {
      onChanged(await api.llmResolve(doc.id), "Campi compilati dall'LLM: controlla i valori.");
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(null);
    }
  };

  return (
    <form className="panel corrections" onSubmit={save} aria-labelledby="fix-title">
      <h2 id="fix-title">Da correggere</h2>
      <ul className="issues">
        {issues.map((issue) => (
          <li key={`${issue.check}-${issue.field}-${issue.message}`}>{issue.message}</li>
        ))}
      </ul>
      {fields.length > 0 && (
        <>
          <div className="field-grid">
            {fields.map((field) => (
              <label className="field" key={field}>
                <span>{FIELD_LABELS[field] ?? field}</span>
                <input
                  inputMode={AMOUNT_FIELDS.includes(field) || INTEGER_FIELDS.includes(field) ? "decimal" : "text"}
                  value={values[field] ?? ""}
                  onChange={(e) => setValues({ ...values, [field]: e.target.value })}
                />
              </label>
            ))}
          </div>
          {error && <Notice tone="error">{error}</Notice>}
          <div className="actions">
            <button type="submit" className="button button-primary" disabled={busy !== null}>
              {busy === "save" ? "Salvataggio…" : "Salva correzioni"}
            </button>
            <button
              type="button"
              className="button"
              onClick={askLlm}
              disabled={busy !== null || !llm?.llm_ready}
              aria-describedby="llm-hint"
            >
              {busy === "llm" ? "Richiesta in corso…" : "Chiedi all'LLM"}
            </button>
            <span id="llm-hint" className="muted small">
              {llm?.llm_ready ? `Provider: ${llm.llm_detail}` : (llm?.llm_detail ?? "")}
              {!llm?.llm_ready && (
                <>
                  {" "}
                  <Link to="/impostazioni">Impostazioni</Link>
                </>
              )}
            </span>
          </div>
        </>
      )}
    </form>
  );
}

function EntriesTable({ title, entries }: { title: string; entries: Entry[] }) {
  if (entries.length === 0) return null;
  const total = entries.reduce((sum, e) => sum + e.amount, 0);
  return (
    <table className="table">
      <caption>{title}</caption>
      <thead>
        <tr>
          <th scope="col">Codice</th>
          <th scope="col">Voce</th>
          <th scope="col" className="num">
            Importo
          </th>
        </tr>
      </thead>
      <tbody>
        {entries.map((e, i) => (
          <tr key={`${e.code}-${i}`}>
            <td className="muted">{e.code ?? ""}</td>
            <td>{e.description ?? ""}</td>
            <td className="num">{eur(e.amount)}</td>
          </tr>
        ))}
      </tbody>
      <tfoot>
        <tr>
          <td />
          <th scope="row">Totale</th>
          <td className="num">{eur(total)}</td>
        </tr>
      </tfoot>
    </table>
  );
}

export function DocumentPage() {
  const { id = "" } = useParams();
  const { reload: reloadList } = useDocuments();
  const [doc, setDoc] = useState<DocumentDetail | null>(null);
  const [llm, setLlm] = useState<LlmSettings | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [reprocessing, setReprocessing] = useState(false);

  const load = useCallback(
    (isCurrent: () => boolean = () => true) =>
      api.getDocument(id).then(
        (detail) => {
          if (!isCurrent()) return;
          setDoc(detail);
          setError(null);
        },
        (e: unknown) => {
          if (isCurrent()) setError(e instanceof Error ? e.message : String(e));
        },
      ),
    [id],
  );

  useEffect(() => {
    let current = true;
    void load(() => current);
    api.getSettings().then(
      (s) => current && setLlm(s),
      () => current && setLlm(null),
    );
    return () => {
      current = false;
    };
  }, [load]);

  const busy = doc ? BUSY.includes(doc.status) : false;
  useEffect(() => {
    if (!busy) return;
    const timer = setInterval(() => void load(), POLL_MS);
    return () => clearInterval(timer);
  }, [busy, load]);

  if (error && !doc) return <Notice tone="error">{error}</Notice>;
  if (!doc) return <p className="muted">Caricamento…</p>;

  const changed = (updated: DocumentDetail, text: string) => {
    setDoc(updated);
    setMessage(text);
    void reloadList();
  };

  const reprocess = async () => {
    setMessage(null);
    setReprocessing(true); // niente doppio job sullo stesso documento
    try {
      await api.reprocess(doc.id);
      await load();
      void reloadList();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setReprocessing(false);
    }
  };

  const fields = doc.extraction?.fields ?? {};
  const issues = doc.extraction?.issues ?? [];
  const pages = doc.extraction?.pages ?? [];
  const rounding = fields.rounding?.value;
  const identity = IDENTITY_FIELDS.filter((f) => fields[f]?.value);

  return (
    <article className="document">
      <p>
        <Link to="/documenti">Tutti i documenti</Link>
      </p>
      <header className="document-head">
        <div>
          <h1>{capitalize(period(doc))}</h1>
          <p className="muted">{doc.filename}</p>
        </div>
        <StatusBadge status={doc.status} />
      </header>

      {message && <Notice tone="ok">{message}</Notice>}
      {error && <Notice tone="error">{error}</Notice>}
      {busy && <Notice tone="info">Lettura del PDF in corso: la pagina si aggiorna da sola.</Notice>}
      {doc.status === "failed" && <Notice tone="error">{doc.error ?? "La lettura del PDF non è riuscita."}</Notice>}
      {doc.status === "needs_ocr" && (
        <Notice tone="error">
          Questo PDF è una scansione senza testo: EarnSight per ora legge solo i cedolini digitali.
        </Notice>
      )}

      {!busy && (
        <dl className="summary">
          <div>
            <dt>Lordo</dt>
            <dd>{eur(doc.gross_pay)}</dd>
          </div>
          <div>
            <dt>Trattenute</dt>
            <dd>{eur(doc.total_deductions)}</dd>
          </div>
          {typeof rounding === "number" && rounding !== 0 && (
            <div>
              <dt>Arrotondamento</dt>
              <dd>{eur(rounding)}</dd>
            </div>
          )}
          <div className="summary-net">
            <dt>Netto</dt>
            <dd>{eur(doc.net_pay)}</dd>
          </div>
        </dl>
      )}

      {!busy && issues.length > 0 && (
        <CorrectionForm key={doc.extraction ? JSON.stringify(issues) : "none"} doc={doc} issues={issues} llm={llm} onChanged={changed} />
      )}

      {doc.entries.length > 0 && (
        <div className="columns">
          <EntriesTable title="Competenze" entries={doc.entries.filter((e) => e.entry_type === "spettanza")} />
          <EntriesTable title="Trattenute" entries={doc.entries.filter((e) => e.entry_type === "trattenuta")} />
        </div>
      )}

      {(identity.length > 0 || doc.template) && (
        <section aria-labelledby="data-title">
          <h2 id="data-title">Dati letti dal documento</h2>
          <dl className="facts">
            {identity.map((f) => (
              <div key={f}>
                <dt>{FIELD_LABELS[f]}</dt>
                <dd>{String(fields[f]?.value)}</dd>
              </div>
            ))}
            {doc.template && (
              <div>
                <dt>Formato</dt>
                <dd>{doc.template === "generic" ? "generico" : capitalize(doc.template)}</dd>
              </div>
            )}
            {doc.doc_type === "cedolino" && pages.length > 0 && (
              <div>
                <dt>Pagine</dt>
                <dd>{pages.length === 1 ? "1 (cedolino)" : `${pages.length} (${pages.join(", ")})`}</dd>
              </div>
            )}
          </dl>
        </section>
      )}

      {doc.raw_text && (
        <details>
          <summary>Testo estratto dal PDF</summary>
          <pre className="raw-text">{doc.raw_text}</pre>
        </details>
      )}

      <div className="actions">
        <button type="button" className="button" onClick={reprocess} disabled={busy || reprocessing}>
          {reprocessing ? "Rielaborazione…" : "Rielabora il PDF"}
        </button>
      </div>
    </article>
  );
}
