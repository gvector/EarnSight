// Routing e cornice dell'app: login pubblico, tutto il resto dietro sessione.
import { Navigate, NavLink, Outlet, Route, Routes, useLocation } from "react-router";
import { NEEDS_ATTENTION } from "./format";
import { DocumentPage } from "./pages/DocumentPage";
import { DocumentsPage } from "./pages/DocumentsPage";
import { LoginPage } from "./pages/LoginPage";
import { OverviewPage } from "./pages/OverviewPage";
import { ReviewPage } from "./pages/ReviewPage";
import { SettingsPage } from "./pages/SettingsPage";
import { DocumentsProvider, useDocuments, useSession } from "./state";

function RequireSession() {
  const { loggedIn } = useSession();
  const location = useLocation();
  if (!loggedIn) return <Navigate to="/accedi" replace state={{ from: location.pathname }} />;
  return (
    <DocumentsProvider>
      <Layout />
    </DocumentsProvider>
  );
}

function Layout() {
  const { logout } = useSession();
  const { documents } = useDocuments();
  const toReview = documents?.filter((d) => NEEDS_ATTENTION.includes(d.status)).length ?? 0;
  return (
    <>
      <a className="skip-link" href="#main">
        Vai al contenuto
      </a>
      <header className="topbar">
        <NavLink to="/" className="brand" end>
          EarnSight
        </NavLink>
        <nav aria-label="Sezioni">
          <NavLink to="/" end>
            Panoramica
          </NavLink>
          <NavLink to="/documenti">Documenti</NavLink>
          <NavLink to="/da-controllare">
            Da controllare
            {toReview > 0 && (
              <span className="count" aria-label={`${toReview} da controllare`}>
                {toReview}
              </span>
            )}
          </NavLink>
          <NavLink to="/impostazioni">Impostazioni</NavLink>
        </nav>
        <button type="button" className="button button-quiet" onClick={logout}>
          Esci
        </button>
      </header>
      <main id="main" className="page">
        <Outlet />
      </main>
    </>
  );
}

export function App() {
  return (
    <Routes>
      <Route path="/accedi" element={<LoginPage />} />
      <Route element={<RequireSession />}>
        <Route index element={<OverviewPage />} />
        <Route path="documenti" element={<DocumentsPage />} />
        <Route path="documenti/:id" element={<DocumentPage />} />
        <Route path="da-controllare" element={<ReviewPage />} />
        <Route path="impostazioni" element={<SettingsPage />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  );
}
