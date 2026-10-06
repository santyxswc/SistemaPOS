import { describe, expect, it } from "vitest";
import {
  centsToApi,
  formatMoney,
  lineGross,
  lineTotal,
  parseDecimal,
  thousandthsToApi,
  toCents,
  toThousandths,
} from "./money";

describe("lectura de montos", () => {
  it("entiende los formatos que escribe un cajero", () => {
    expect(toCents("12500")).toBe(1250000);
    expect(toCents("12.500")).toBe(1250000);
    expect(toCents("12.500,50")).toBe(1250050);
    expect(toCents("$ 2.000")).toBe(200000);
    expect(toCents("3333.335")).toBe(333334);
    expect(toCents("0.1")).toBe(10);
  });

  it("en cantidades el punto es decimal", () => {
    expect(toThousandths("1.500")).toBe(1500);
    expect(toThousandths("0,375")).toBe(375);
    expect(toThousandths("2")).toBe(2000);
  });

  it("rechaza texto que no es número", () => {
    expect(parseDecimal("abc", 2)).toBeNull();
    expect(parseDecimal("", 2)).toBeNull();
    expect(parseDecimal("1.2.3", 3)).toBeNull();
  });
});

describe("conversión para la API", () => {
  it("envía texto exacto", () => {
    expect(centsToApi(1250050)).toBe("12500.50");
    expect(centsToApi(5)).toBe("0.05");
    expect(thousandthsToApi(1500)).toBe("1.5");
    expect(thousandthsToApi(2000)).toBe("2");
  });
});

describe("cálculo de líneas", () => {
  it("redondea como el servidor (mitad hacia arriba)", () => {
    expect(lineGross(1899000, 375)).toBe(712125); // 0,375 kg a $18.990
    expect(lineGross(333333, 3000)).toBe(999999);
    expect(lineGross(1, 500)).toBe(1); // 0,005 → 0,01
  });

  it("suma el impuesto solo si el precio no lo incluye", () => {
    expect(lineTotal(1000000, "19", true)).toBe(1000000);
    expect(lineTotal(1000000, "19", false)).toBe(1190000);
    expect(lineTotal(100, "8", false)).toBe(108);
  });

  it("muestra el dinero en formato colombiano", () => {
    expect(formatMoney(1250000)).toBe("$12.500");
    expect(formatMoney("12500.50")).toBe("$12.500,50");
    expect(formatMoney(-50000)).toBe("-$500");
  });
});
