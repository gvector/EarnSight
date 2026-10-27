import { useState, type FormEvent } from "react";
import { Navigate, useLocation, useNavigate } from "react-router";
import { Notice } from "../components/ui";
import { useSession } from "../state";

export function LoginPage() {
  const { loggedIn, login } = useSession();
  const navigate = useNavigate();
  const from = (useLocation().state as { from?: string } | null)?.from ?? "/";
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  if (loggedIn) return <Navigate to={from} replace />;

  const onSubmit = async (event: FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await login(username, password);
      navigate(from, { replace: true });
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <main className="login">
      <form className="login-form" onSubmit={onSubmit}>
        <h1>EarnSight</h1>
        <p className="muted">I tuoi cedolini, letti e verificati sul tuo computer.</p>
        <label className="field">
          <span>Nome utente</span>
          <input autoComplete="username" required value={username} onChange={(e) => setUsername(e.target.value)} />
        </label>
        <label className="field">
          <span>Password</span>
          <input
            type="password"
            autoComplete="current-password"
            required
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
        </label>
        {error && <Notice tone="error">{error}</Notice>}
        <button type="submit" className="button button-primary" disabled={busy}>
          {busy ? "Accesso…" : "Accedi"}
        </button>
      </form>
    </main>
  );
}
