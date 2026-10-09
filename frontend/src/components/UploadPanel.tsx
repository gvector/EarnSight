// Caricamento di uno o più PDF: trascinamento o scelta file, tipo documento, esito per file.
import { useRef, useState, type DragEvent, type FormEvent } from "react";
import { api, ApiError, type DocType } from "../api";
import { useDocuments } from "../state";
import { Notice } from "./ui";

export function UploadPanel() {
  const { reload } = useDocuments();
  const input = useRef<HTMLInputElement>(null);
  const [files, setFiles] = useState<File[]>([]);
  const [docType, setDocType] = useState<DocType>("cedolino");
  const [busy, setBusy] = useState(false);
  const [dragging, setDragging] = useState(false);
  const [result, setResult] = useState<{ sent: number; errors: string[] } | null>(null);

  const choose = (list: FileList | null) => {
    setFiles(list ? Array.from(list) : []);
    setResult(null);
  };

  const onDrop = (event: DragEvent) => {
    event.preventDefault();
    setDragging(false);
    choose(event.dataTransfer.files);
  };

  const onSubmit = async (event: FormEvent) => {
    event.preventDefault();
    setBusy(true);
    const errors: string[] = [];
    let sent = 0;
    for (const file of files) {
      try {
        await api.upload(file, docType);
        sent += 1;
      } catch (e) {
        errors.push(`${file.name}: ${e instanceof ApiError ? e.message : String(e)}`);
      }
    }
    setResult({ sent, errors });
    setFiles([]);
    if (input.current) input.current.value = ""; // un secondo invio non ricarica gli stessi file
    setBusy(false);
    await reload();
  };

  return (
    <form className="upload" onSubmit={onSubmit} aria-labelledby="upload-title">
      <h2 id="upload-title">Carica cedolini</h2>
      <label
        className={`dropzone${dragging ? " dropzone-active" : ""}`}
        onDragOver={(e) => {
          e.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={onDrop}
      >
        <input
          ref={input}
          type="file"
          accept="application/pdf,.pdf"
          multiple
          className="visually-hidden"
          onChange={(e) => choose(e.target.files)}
          aria-label="Scegli i PDF da caricare"
        />
        {files.length === 0 ? (
          <span>
            Trascina qui i PDF o <span className="link-like">sceglili dal computer</span>
          </span>
        ) : (
          <span>
            {files.length === 1 ? "1 file pronto" : `${files.length} file pronti`}:{" "}
            {files.map((f) => f.name).join(", ")}
          </span>
        )}
      </label>

      <fieldset className="choice">
        <legend>Tipo di documento</legend>
        <label>
          <input type="radio" name="doc_type" checked={docType === "cedolino"} onChange={() => setDocType("cedolino")} />
          Cedolino mensile
        </label>
        <label>
          <input type="radio" name="doc_type" checked={docType === "cu"} onChange={() => setDocType("cu")} />
          Certificazione Unica
        </label>
      </fieldset>

      <button type="submit" className="button button-primary" disabled={files.length === 0 || busy}>
        {busy ? "Caricamento…" : "Carica"}
      </button>

      {result && result.sent > 0 && (
        <Notice tone="ok">
          {result.sent === 1 ? "1 documento caricato" : `${result.sent} documenti caricati`}: l'elaborazione
          richiede pochi secondi.
        </Notice>
      )}
      {result && result.errors.length > 0 && (
        <Notice tone="error">
          <p>Non caricati:</p>
          <ul>
            {result.errors.map((e) => (
              <li key={e}>{e}</li>
            ))}
          </ul>
        </Notice>
      )}
    </form>
  );
}
