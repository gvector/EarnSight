// Da controllare: i documenti che hanno bisogno di te, con il motivo.
import { Link } from "react-router";
import type { DocumentSummary } from "../api";
import { Notice, StatusBadge } from "../components/ui";
import { byPeriodDesc, capitalize, NEEDS_ATTENTION, period } from "../format";
import { useDocuments } from "../state";

const WHAT_TO_DO: Record<string, string> = {
  needs_review: "I conti non tornano o manca un valore: correggi i campi segnalati.",
  needs_ocr: "Il PDF è una scansione senza testo: serve la versione digitale del cedolino.",
  failed: "La lettura del PDF non è riuscita: prova a rielaborarlo.",
};

export function ReviewPage() {
  const { documents, error } = useDocuments();
  if (error) return <Notice tone="error">{error}</Notice>;
  if (documents === null) return <p className="muted">Caricamento…</p>;

  const todo: DocumentSummary[] = documents.filter((d) => NEEDS_ATTENTION.includes(d.status)).sort(byPeriodDesc);
  return (
    <>
      <h1>Da controllare</h1>
      {todo.length === 0 ? (
        <Notice tone="ok">Tutti i documenti sono verificati: non c'è niente da controllare.</Notice>
      ) : (
        <ul className="todo">
          {todo.map((doc) => (
            <li key={doc.id}>
              <div>
                <Link to={`/documenti/${doc.id}`}>{capitalize(period(doc))}</Link>{" "}
                <span className="muted">{doc.filename}</span>
              </div>
              <StatusBadge status={doc.status} />
              <p>{WHAT_TO_DO[doc.status]}</p>
            </li>
          ))}
        </ul>
      )}
    </>
  );
}
