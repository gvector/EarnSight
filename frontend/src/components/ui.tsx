// Piccoli componenti condivisi: badge di stato, messaggi, tabella documenti.
import type { ReactNode } from "react";
import { Link } from "react-router";
import type { DocStatus, DocumentSummary } from "../api";
import { capitalize, eur, period, STATUS } from "../format";

export function StatusBadge({ status }: { status: DocStatus }) {
  const { label, tone } = STATUS[status];
  return <span className={`badge badge-${tone}`}>{label}</span>;
}

export function Notice({ tone, children }: { tone: "error" | "warn" | "ok" | "info"; children: ReactNode }) {
  return (
    <div className={`notice notice-${tone}`} role={tone === "error" ? "alert" : "status"}>
      {children}
    </div>
  );
}

export function DocumentsTable({ documents }: { documents: DocumentSummary[] }) {
  return (
    <table className="table">
      <thead>
        <tr>
          <th scope="col">Periodo</th>
          <th scope="col" className="col-file">
            File
          </th>
          <th scope="col">Stato</th>
          <th scope="col" className="num">Netto</th>
        </tr>
      </thead>
      <tbody>
        {documents.map((doc) => (
          <tr key={doc.id}>
            <td>
              <Link to={`/documenti/${doc.id}`}>{capitalize(period(doc))}</Link>
            </td>
            <td className="muted col-file">{doc.filename}</td>
            <td>
              <StatusBadge status={doc.status} />
            </td>
            <td className="num">{eur(doc.net_pay)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
