// Carrito y cobro: lógica pura, sin interfaz. Replica las reglas del servidor solo
// para avisar al cajero antes de enviar; el servidor siempre tiene la última palabra.

import { type Cents, lineGross, lineTotal, toCents } from "./money";
import type { PaymentKind, Product } from "./types";

export interface CartLine {
  product: Product;
  quantity: number; // milésimas
  discount: Cents;
}

export function addToCart(lines: CartLine[], product: Product, quantity = 1000): CartLine[] {
  const index = lines.findIndex((line) => line.product.id === product.id);
  if (index === -1) return [...lines, { product, quantity, discount: 0 }];
  return lines.map((line, i) => (i === index ? { ...line, quantity: line.quantity + quantity } : line));
}

export function lineAmount(line: CartLine, pricesIncludeTax: boolean): Cents {
  const gross = lineGross(toCents(line.product.price), line.quantity);
  const net = Math.max(0, gross - line.discount);
  return lineTotal(net, line.product.tax_rate, pricesIncludeTax);
}

export function cartTotal(lines: CartLine[], pricesIncludeTax: boolean): Cents {
  return lines.reduce((sum, line) => sum + lineAmount(line, pricesIncludeTax), 0);
}

export interface PaymentDraft {
  method: string;
  kind: PaymentKind;
  amount: Cents;
}

export interface PaymentStatus {
  paid: Cents;
  missing: Cents;
  change: Cents;
  problem: string | null;
}

export function paymentStatus(total: Cents, payments: PaymentDraft[], hasCustomer: boolean): PaymentStatus {
  const paid = payments.reduce((sum, p) => sum + p.amount, 0);
  const cash = payments.filter((p) => p.kind === "cash").reduce((sum, p) => sum + p.amount, 0);
  const missing = Math.max(0, total - paid);
  const change = Math.max(0, paid - total);
  let problem: string | null = null;
  if (payments.some((p) => p.amount <= 0)) problem = "Escriba el monto de cada pago";
  else if (missing > 0) problem = null; // se muestra como "Falta"
  else if (change > cash) problem = "Solo el efectivo puede dar vueltas: revise los montos";
  else if (payments.some((p) => p.kind === "credit") && !hasCustomer) problem = "Para fiar, seleccione el cliente";
  return { paid, missing, change, problem };
}

/** Billetes sugeridos para pagar en efectivo: el valor exacto y redondeos hacia arriba. */
export function quickCashAmounts(total: Cents): Cents[] {
  if (total <= 0) return [];
  const steps = [100000, 200000, 500000, 1000000, 2000000, 5000000, 10000000];
  const options = new Set<Cents>([total]);
  for (const step of steps) {
    const rounded = Math.ceil(total / step) * step;
    if (rounded > total) options.add(rounded);
  }
  return [...options].sort((a, b) => a - b).slice(0, 5);
}

export function newRequestId(): string {
  return typeof crypto !== "undefined" && "randomUUID" in crypto
    ? crypto.randomUUID()
    : `${Date.now()}-${Math.random().toString(36).slice(2)}`;
}
