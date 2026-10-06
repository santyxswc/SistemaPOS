import { describe, expect, it } from "vitest";
import { addToCart, cartTotal, paymentStatus, quickCashAmounts } from "./cart";
import type { Product } from "./types";

function product(id: string, price: string, tax_rate = "19"): Product {
  return {
    id, sku: id, barcode: null, name: id, category_id: null, price, cost: "0", tax_rate, unit: "unit",
    track_stock: true, stock: "10", min_stock: "0", is_low_stock: false, active: true, updated_at: "",
  };
}

describe("carrito", () => {
  it("suma unidades del mismo producto en una sola línea", () => {
    let lines = addToCart([], product("arroz", "2500"));
    lines = addToCart(lines, product("arroz", "2500"));
    lines = addToCart(lines, product("aceite", "9000"));
    expect(lines.map((l) => [l.product.id, l.quantity])).toEqual([["arroz", 2000], ["aceite", 1000]]);
    expect(cartTotal(lines, true)).toBe(1400000);
  });

  it("agrega el impuesto cuando los precios no lo incluyen", () => {
    const lines = addToCart([], product("servicio", "10000"));
    expect(cartTotal(lines, false)).toBe(1190000);
  });

  it("descuenta el descuento de la línea", () => {
    const lines = [{ ...addToCart([], product("arroz", "2500"))[0], discount: 50000 }];
    expect(cartTotal(lines, true)).toBe(200000);
  });
});

describe("cobro", () => {
  it("calcula vueltas solo con efectivo", () => {
    expect(paymentStatus(750000, [{ method: "efectivo", kind: "cash", amount: 1000000 }], false)).toEqual({
      paid: 1000000, missing: 0, change: 250000, problem: null,
    });
    const nequi = paymentStatus(750000, [{ method: "nequi", kind: "electronic", amount: 1000000 }], false);
    expect(nequi.problem).toMatch(/efectivo/);
  });

  it("indica lo que falta y exige cliente para fiar", () => {
    expect(paymentStatus(750000, [{ method: "efectivo", kind: "cash", amount: 500000 }], false).missing).toBe(250000);
    expect(paymentStatus(750000, [{ method: "fiado", kind: "credit", amount: 750000 }], false).problem).toMatch(
      /cliente/,
    );
    expect(paymentStatus(750000, [{ method: "fiado", kind: "credit", amount: 750000 }], true).problem).toBeNull();
  });

  it("sugiere billetes redondos", () => {
    expect(quickCashAmounts(1270000)).toEqual([1270000, 1300000, 1400000, 1500000, 2000000]);
    expect(quickCashAmounts(0)).toEqual([]);
  });
});
