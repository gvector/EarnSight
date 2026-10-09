import { afterEach, describe, expect, it, vi } from "vitest";
import { api, ApiError, setUnauthorizedHandler, tokenStore } from "./api";
import { fakeApi } from "./test/helpers";

afterEach(() => setUnauthorizedHandler(() => {}));

describe("api client", () => {
  it("sends the bearer token and relative /api URLs", async () => {
    const server = fakeApi();
    server.on("GET", "/payslips", { body: [] });
    tokenStore.set("abc");
    await api.listDocuments();
    const [url, init] = vi.mocked(fetch).mock.calls[0]!;
    expect(url).toBe("/api/payslips");
    expect(new Headers(init?.headers).get("Authorization")).toBe("Bearer abc");
  });

  it("does not send a token on login", async () => {
    const server = fakeApi();
    server.on("POST", "/auth/login", { body: { access_token: "t" } });
    tokenStore.set("old");
    await api.login("admin", "pw");
    expect(new Headers(vi.mocked(fetch).mock.calls[0]![1]?.headers).get("Authorization")).toBeNull();
    expect(server.calls[0]!.body).toEqual({ username: "admin", password: "pw" });
  });

  it("turns the API detail into the error message", async () => {
    const server = fakeApi();
    server.on("PATCH", "/payslips/x/fields", { status: 422, body: { detail: "Correzione non valida: mese" } });
    await expect(api.correct("x", { period_month: 13 })).rejects.toMatchObject({
      message: "Correzione non valida: mese",
      status: 422,
    });
  });

  it("joins FastAPI validation errors", async () => {
    const server = fakeApi();
    server.on("PUT", "/settings", { status: 422, body: { detail: [{ msg: "campo richiesto" }, { msg: "tipo errato" }] } });
    await expect(api.saveSettings({ llm_provider: "" })).rejects.toThrow("campo richiesto; tipo errato");
  });

  it("calls the unauthorized handler on 401, but not for a failed login", async () => {
    const server = fakeApi();
    const handler = vi.fn();
    setUnauthorizedHandler(handler);
    server.on("GET", "/payslips", { status: 401, body: { detail: "Credenziali non valide" } });
    server.on("POST", "/auth/login", { status: 401, body: { detail: "Username o password non validi" } });
    await expect(api.listDocuments()).rejects.toBeInstanceOf(ApiError);
    expect(handler).toHaveBeenCalledTimes(1);
    await expect(api.login("a", "b")).rejects.toThrow("Username o password non validi");
    expect(handler).toHaveBeenCalledTimes(1);
  });

  it("explains a network failure", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")));
    await expect(api.listDocuments()).rejects.toMatchObject({ status: 0, message: expect.stringMatching(/non risponde/) });
  });

  it("uploads multipart without forcing a JSON content type", async () => {
    const server = fakeApi();
    server.on("POST", "/payslips/upload", { status: 201, body: {} });
    await api.upload(new File(["%PDF"], "a.pdf", { type: "application/pdf" }), "cu");
    const init = vi.mocked(fetch).mock.calls[0]![1]!;
    expect(new Headers(init.headers).get("Content-Type")).toBeNull();
    const form = server.calls[0]!.body as FormData;
    expect(form.get("doc_type")).toBe("cu");
    expect((form.get("file") as File).name).toBe("a.pdf");
  });
});

describe("api client edge cases", () => {
  it("falls back to the HTTP status when the body has no detail", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response("<html>bad gateway</html>", { status: 502 })));
    await expect(api.listDocuments()).rejects.toMatchObject({ message: "Errore 502", status: 502 });
  });
  it("sends no Authorization header when there is no token", async () => {
    const server = fakeApi();
    server.on("GET", "/payslips", { body: [] });
    await api.listDocuments();
    expect(server.calls[0]!.headers.get("Authorization")).toBeNull();
  });
});
