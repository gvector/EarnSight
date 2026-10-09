import { UploadPanel } from "../components/UploadPanel";
import { DocumentsTable, Notice } from "../components/ui";
import { byPeriodDesc } from "../format";
import { useDocuments } from "../state";

export function DocumentsPage() {
  const { documents, error } = useDocuments();
  return (
    <>
      <h1>Documenti</h1>
      {error && <Notice tone="error">{error}</Notice>}
      {documents === null && !error && <p className="muted">Caricamento…</p>}
      {documents?.length === 0 && <p className="muted">Nessun documento: caricane uno qui sotto.</p>}
      {documents && documents.length > 0 && <DocumentsTable documents={[...documents].sort(byPeriodDesc)} />}
      <UploadPanel />
    </>
  );
}
