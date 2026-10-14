// End-to-end sullo stack completo (nginx → api → worker → postgres) con PDF sintetici.
// Presuppone uno stack appena creato: `make e2e` lo crea, esegue questi test e lo distrugge.
// PDF: e2e/fixtures, generati da make_fixtures.py (layout Zucchetti e CU, dati inventati).
import { expect, test, type Page } from "@playwright/test";
import path from "node:path";

const fixture = (name: string) => path.join(import.meta.dirname, "fixtures", name);
const USER = process.env.E2E_USERNAME ?? "admin";
const PASSWORD = process.env.E2E_PASSWORD ?? "";

async function login(page: Page) {
  await page.goto("/");
  await page.getByLabel("Nome utente").fill(USER);
  await page.getByLabel("Password").fill(PASSWORD);
  await page.getByRole("button", { name: "Accedi" }).click();
  await expect(page.getByRole("button", { name: "Esci" })).toBeVisible();
}

// Indipendenti dallo stato: girano anche se il flusso in sequenza qui sotto fallisce.
test.describe("stack", () => {
  test("wrong password is refused with the API message", async ({ page }) => {
    await page.goto("/documenti");
    await expect(page).toHaveURL(/\/accedi$/);
    await page.getByLabel("Nome utente").fill(USER);
    await page.getByLabel("Password").fill("password-sbagliata");
    await page.getByRole("button", { name: "Accedi" }).click();
    await expect(page.getByRole("alert")).toHaveText("Username o password non validi");
  });

  test("nginx sends the security headers and stops oversized uploads", async ({ request }) => {
    const home = await request.get("/");
    expect(home.headers()["content-security-policy"]).toContain("script-src 'self'");
    expect(home.headers()["x-frame-options"]).toBe("DENY");
    const big = await request.post("/api/payslips/upload", {
      multipart: { file: { name: "grande.pdf", mimeType: "application/pdf", buffer: Buffer.alloc(12 * 1024 * 1024) } },
    });
    expect(big.status()).toBe(413); // fermato da nginx (client_max_body_size), prima dell'API
  });

  test("settings: without a provider the LLM is reported as not ready", async ({ page }) => {
    await login(page);
    await page.getByRole("link", { name: "Impostazioni" }).click();
    await expect(page.getByRole("status").filter({ hasText: "Nessun provider" })).toBeVisible();
  });
});

// Flusso in sequenza su uno stack appena creato: ogni passo usa i documenti del precedente.
test.describe.serial("flusso", () => {

test("upload: PDFs are read by the worker, a fake PDF is refused", async ({ page }) => {
  await login(page);
  await expect(page.getByRole("heading", { name: "Benvenuto in EarnSight" })).toBeVisible();
  await page.getByLabel("Scegli i PDF da caricare").setInputFiles([
    fixture("cedolino-aprile.pdf"),
    fixture("cedolino-maggio-incoerente.pdf"),
    fixture("quattordicesima-giugno.pdf"),
    fixture("non-un-pdf.pdf"),
  ]);
  await page.getByRole("button", { name: "Carica", exact: true }).click();
  await expect(page.getByText("3 documenti caricati")).toBeVisible();
  await expect(page.getByRole("alert")).toContainText("non-un-pdf.pdf: Il file non è un PDF valido");

  // il polling aggiorna la tabella fino alla fine dell'elaborazione
  const recent = page.getByRole("table");
  await expect(recent.getByText("Verificato")).toHaveCount(2, { timeout: 30_000 });
  await expect(recent.getByText("Da controllare")).toHaveCount(1);
});

test("overview: latest month in the sentence, bars switch month", async ({ page }) => {
  await login(page);
  const hero = page.getByRole("region", { name: "Netto ricevuto" });
  await expect(hero).toContainText("Con la mensilità aggiuntiva di giugno 2026 hai ricevuto");
  await expect(hero.locator(".hero-amount")).toHaveText("1.571,00 €");
  await hero.getByRole("button", { name: /^aprile 2026/ }).click();
  await expect(hero).toContainText("Ad aprile 2026 hai ricevuto");
});

test("review: fix the inconsistent net and the document becomes verified", async ({ page }) => {
  await login(page);
  await expect(page.getByLabel("1 da controllare")).toBeVisible();
  await page.getByRole("link", { name: /Da controllare/ }).click();
  await page.getByRole("link", { name: "Maggio 2026" }).click();
  await expect(page.getByText(/non combacia con il netto/)).toBeVisible();

  const net = page.getByLabel("Netto");
  await expect(net).toHaveValue("1.500,00");
  await net.fill("1.571,00");
  await page.getByRole("button", { name: "Salva correzioni" }).click();
  await expect(page.getByText("Correzioni salvate.")).toBeVisible();
  await expect(page.locator(".document-head").getByText("Verificato")).toBeVisible();
  await expect(page.getByLabel("1 da controllare")).toHaveCount(0);
});

test("detail: the attendance sheet is tracked, deep links survive a reload", async ({ page }) => {
  await login(page);
  await page.getByRole("link", { name: "Documenti", exact: true }).click();
  await page.getByRole("link", { name: "Aprile 2026" }).click();
  await expect(page.getByText("2 (presenze, cedolino)")).toBeVisible();
  await expect(page.getByRole("table", { name: "Competenze" })).toContainText("Retribuzione");

  const url = page.url();
  await page.reload(); // nginx serve index.html anche sui percorsi della SPA
  await expect(page).toHaveURL(url);
  await expect(page.getByText("2 (presenze, cedolino)")).toBeVisible();

  await page.getByRole("button", { name: "Esci" }).click();
  await expect(page).toHaveURL(/\/accedi$/);
});

test("cu: an uploaded Certificazione Unica shows points 1 and 21, the copy is tracked", async ({ page }) => {
  await login(page);
  await page.getByLabel("Scegli i PDF da caricare").setInputFiles([fixture("cu-2025.pdf")]);
  await page.getByLabel("Certificazione Unica").check();
  await page.getByRole("button", { name: "Carica", exact: true }).click();
  await expect(page.getByText("1 documento caricato")).toBeVisible();

  await page.getByRole("link", { name: "Documenti", exact: true }).click();
  await page.getByRole("link", { name: "CU 2025" }).click({ timeout: 30_000 });
  await expect(page.getByText("Imponibile IRPEF (punti 1 e 2)")).toBeVisible();
  await expect(page.getByText("25.000,00 €")).toBeVisible({ timeout: 30_000 });
  await expect(page.getByText("IRPEF trattenuta (punto 21)")).toBeVisible();
  await expect(page.getByText("5 (cu, cu, cu, copia, copia)")).toBeVisible();
  await expect(page.getByText("Netto")).toHaveCount(0);
});

test("anni: one card per year, missing months, the CU optional", async ({ page }) => {
  await login(page);
  await page.getByRole("link", { name: "Anni", exact: true }).click();
  const current = page.getByRole("region", { name: "2026 · Zucchetti · datore 01234567890" });
  await expect(current).toBeVisible();
  await expect(current.getByRole("link", { name: "apr" })).toBeVisible();
  await expect(current.getByRole("link", { name: "+ agg. giu" })).toBeVisible();
  await expect(current.getByText(/Mancano gen–mar/)).toBeVisible();
  await expect(current.getByText(/Nessuna CU per quest'anno/)).toBeVisible();

  const previous = page.getByRole("region", { name: "2025 · datore 01234567890" });
  await expect(previous.getByText("Nessun cedolino di quest'anno da confrontare con la CU")).toBeVisible();
});
});
