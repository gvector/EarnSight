// Stato condiviso: sessione (token) e lista documenti con polling.
import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from "react";
import { api, setUnauthorizedHandler, tokenStore, type DocumentSummary } from "./api";
import { BUSY } from "./format";

interface Session {
  loggedIn: boolean;
  login: (username: string, password: string) => Promise<void>;
  logout: () => void;
}

const SessionContext = createContext<Session | null>(null);

export function SessionProvider({ children }: { children: ReactNode }) {
  const [loggedIn, setLoggedIn] = useState(() => tokenStore.get() !== null);

  const logout = useCallback(() => {
    tokenStore.clear();
    setLoggedIn(false);
  }, []);

  // un 401 su qualsiasi richiesta (token scaduto) riporta al login
  useEffect(() => setUnauthorizedHandler(logout), [logout]);

  const login = useCallback(async (username: string, password: string) => {
    const { access_token } = await api.login(username, password);
    tokenStore.set(access_token);
    setLoggedIn(true);
  }, []);

  return <SessionContext value={{ loggedIn, login, logout }}>{children}</SessionContext>;
}

export function useSession(): Session {
  const session = useContext(SessionContext);
  if (!session) throw new Error("useSession fuori da SessionProvider");
  return session;
}

interface Documents {
  documents: DocumentSummary[] | null; // null = primo caricamento in corso
  error: string | null;
  reload: () => Promise<void>;
}

const DocumentsContext = createContext<Documents | null>(null);
export const POLL_MS = 2000;

/** Lista documenti condivisa da tutte le pagine; si aggiorna da sola finché c'è un'elaborazione in corso. */
export function DocumentsProvider({ children }: { children: ReactNode }) {
  const [documents, setDocuments] = useState<DocumentSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  // solo la risposta dell'ultima richiesta vince: un polling lento non sovrascrive dati più nuovi
  const latest = useRef(0);
  const apply = useCallback((result: Promise<DocumentSummary[]>, isCurrent: () => boolean = () => true) => {
    const request = ++latest.current;
    return result.then(
      (list) => {
        if (!isCurrent() || request !== latest.current) return;
        setDocuments(list);
        setError(null);
      },
      (e: unknown) => {
        if (isCurrent() && request === latest.current) setError(e instanceof Error ? e.message : String(e));
      },
    );
  }, []);

  const reload = useCallback(() => apply(api.listDocuments()), [apply]);

  useEffect(() => {
    let current = true;
    void apply(api.listDocuments(), () => current);
    return () => {
      current = false;
    };
  }, [apply]);

  const busy = documents?.some((d) => BUSY.includes(d.status)) ?? false;
  useEffect(() => {
    if (!busy) return;
    const timer = setInterval(() => void reload(), POLL_MS);
    return () => clearInterval(timer);
  }, [busy, reload]);

  return <DocumentsContext value={{ documents, error, reload }}>{children}</DocumentsContext>;
}

export function useDocuments(): Documents {
  const docs = useContext(DocumentsContext);
  if (!docs) throw new Error("useDocuments fuori da DocumentsProvider");
  return docs;
}
