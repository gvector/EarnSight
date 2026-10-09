import { describe, expect, it } from "vitest";
import { byPeriodDesc, eur, parseAmount, parseInteger, period } from "./format";
import { makeDoc } from "./test/helpers";

describe("eur", () => {
  // Intl separa la cifra dall'€ con uno spazio non separabile (U+00A0)
  it("formats like the payslip, thousands separator included", () => {
    expect(eur("2468.00")).toBe("2.468,00\u00a0€");
    expect(eur(642)).toBe("642,00\u00a0€");
    expect(eur(-0.66)).toBe("-0,66\u00a0€");
  });
  it("shows a dash for missing or non-numeric values", () => {
    expect(eur(null)).toBe("—");
    expect(eur("")).toBe("—");
    expect(eur("abc")).toBe("—");
  });
});

describe("parseAmount", () => {
  it.each([
    ["2.250,50", 2250.5],
    ["2,250.50", 2250.5],
    ["2250.50", 2250.5],
    ["250,00", 250],
    ["2.250", 2250],
    ["2.468,00 €", 2468],
    ["-0,66", -0.66],
  ])("%s → %s", (raw, expected) => expect(parseAmount(raw)).toBe(expected));

  it.each(["", "marzo", "1.2.3", "12,34,56", "--1"])("rejects %j", (raw) => {
    expect(() => parseAmount(raw)).toThrow();
  });
});

describe("parseInteger", () => {
  it("accepts whole numbers only", () => {
    expect(parseInteger(" 12 ")).toBe(12);
    expect(() => parseInteger("3.5")).toThrow();
    expect(() => parseInteger("marzo")).toThrow();
  });
});

describe("period", () => {
  it("names the month, the additional month and the CU", () => {
    expect(period(makeDoc({ period_month: 8, period_year: 2026 }))).toBe("agosto 2026");
    expect(period(makeDoc({ period_month: 6, additional_payment: true }))).toBe("giugno 2026, mensilità aggiuntiva");
    expect(period(makeDoc({ doc_type: "cu", period_month: null, period_year: 2025 }))).toBe("CU 2025");
    expect(period(makeDoc({ period_month: null }))).toBe("periodo non riconosciuto");
  });
});

describe("byPeriodDesc", () => {
  it("puts the newest period first and the additional month right after its month", () => {
    const may = makeDoc({ period_month: 5 });
    const june = makeDoc({ period_month: 6 });
    const extra = makeDoc({ period_month: 6, additional_payment: true });
    const july = makeDoc({ period_month: 7 });
    expect([may, extra, july, june].sort(byPeriodDesc).map((d) => d.id)).toEqual([
      july.id,
      extra.id,
      june.id,
      may.id,
    ]);
  });
});

describe("status groups", () => {
  it("polls for pending and processing, asks attention for review/ocr/failed", async () => {
    const { BUSY, NEEDS_ATTENTION, STATUS } = await import("./format");
    expect(BUSY).toEqual(["pending", "processing"]);
    expect(NEEDS_ATTENTION).toEqual(["needs_review", "needs_ocr", "failed"]);
    expect(STATUS.pending.label).toBe("In coda");
    expect(STATUS.processing.label).toBe("In elaborazione");
  });
});

describe("period and ordering edge cases", () => {
  it("handles december and a missing year", () => {
    expect(period(makeDoc({ period_month: 12, period_year: 2026 }))).toBe("dicembre 2026");
    expect(period(makeDoc({ period_year: null }))).toBe("periodo non riconosciuto");
  });
  it("breaks ties on the same month with the newest upload first", () => {
    const old = makeDoc({ period_month: 5, created_at: "2026-06-01T10:00:00Z" });
    const reupload = makeDoc({ period_month: 5, created_at: "2026-06-02T10:00:00Z" });
    expect([old, reupload].sort(byPeriodDesc)[0]!.id).toBe(reupload.id);
  });
});
