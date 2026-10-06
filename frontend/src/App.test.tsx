// @vitest-environment jsdom
// Recorre la interfaz como un cajero, contra un servidor simulado.

import { cleanup, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { App } from "./App";
import type { Me, Product, Settings } from "./types";

const SETTINGS: Settings = {
  business_name: "Tienda Doña Rosa",
  tax_id: "900123456",
  address: "Calle 1",
  phone: "",
  currency: "COP",
  timezone: "America/Bogota",
  prices_include_tax: true,
  default_tax_rate: "19",
  allow_negative_stock: false,
  credit_sales_enabled: true,
  max_users: 3,
  receipt_footer: "¡Gracias por su compra!",
  payment_methods: [
    { code: "efectivo", name: "Efectivo", kind: "cash", active: true },
    { code: "nequi", name: "Nequi", kind: "electronic", active: true },
    { code: "fiado", name: "Fiado", kind: "credit", active: true },
  ],
};

const RICE: Product = {
  id: "p-arroz", sku: "ARROZ-500", barcode: "7702511000014", name: "Arroz Diana 500 g", category_id: null,
  price: "2500.00", cost: "0.00", tax_rate: "19", unit: "unit", track_stock: true, stock: "40", min_stock: "10",
  is_low_stock: false, active: true, updated_at: "",
};

const CASHIER: Me = {
  id: "u-1", username: "caja1", full_name: "Cajero Uno", role: "cashier",
  permissions: ["sell", "operate_cash", "manage_customers", "collect_payments"],
};

interface Call {
  method: string;
  path: string;
  body: unknown;
  headers: Record<string, string>;
}

type Handler = (call: Call) => { status?: number; body?: unknown } | "network-error";

function mockServer(handler: Handler) {
  const calls: Call[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: URL | string, init: RequestInit = {}) => {
      const url = new URL(String(input));
      const call: Call = {
        method: init.method ?? "GET",
        path: url.pathname.replace("/api/v1", "") + url.search,
        body: init.body ? JSON.parse(String(init.body)) : undefined,
        headers: (init.headers ?? {}) as Record<string, string>,
      };
      calls.push(call);
      const result = handler(call);
      if (result === "network-error") throw new TypeError("Failed to fetch");
      return new Response(JSON.stringify(result.body ?? {}), { status: result.status ?? 200 });
    }),
  );
  return calls;
}

function cashierServer(onSale: Handler): Handler {
  let cashOpen = false;
  return (call) => {
    const route = `${call.method} ${call.path.split("?")[0]}`;
    switch (route) {
      case "POST /auth/login":
        return { body: { access_token: "token-1" } };
      case "GET /auth/me":
        return { body: CASHIER };
      case "GET /settings":
        return { body: SETTINGS };
      case "GET /cash-sessions/current":
        return cashOpen ? { body: {} } : { status: 404, body: { error: { code: "not_found", message: "No tiene una caja abierta" } } };
      case "POST /cash-sessions":
        cashOpen = true;
        return { status: 201, body: {} };
      case "GET /products/lookup":
        return { body: RICE };
      case "GET /products":
        return { body: { items: [RICE] } };
      case "POST /sales":
        return onSale(call);
      default:
        return { status: 404, body: { error: { code: "not_found", message: `Sin simular: ${route}` } } };
    }
  };
}

const SALE = {
  id: "s-1", number: 1, status: "completed", cashier_id: "u-1", customer_id: null, subtotal: "4201.68",
  tax_total: "798.32", discount_total: "0.00", total: "5000.00", change: "5000.00", note: "",
  created_at: "2026-10-06T15:00:00+00:00", voided_at: null, void_reason: null,
  lines: [{ product_id: "p-arroz", sku: "ARROZ-500", description: "Arroz Diana 500 g", quantity: "2", unit_price: "2500.00",
    discount: "0.00", tax_rate: "19", base: "4201.68", tax: "798.32", total: "5000.00" }],
  payments: [{ method: "efectivo", name: "Efectivo", kind: "cash", amount: "10000.00" }],
};

async function loginAndOpenCash() {
  const user = userEvent.setup();
  render(<App />);
  await user.type(await screen.findByLabelText("Usuario"), "caja1");
  await user.type(screen.getByLabelText("Contraseña"), "clave-segura-2");
  await user.click(screen.getByRole("button", { name: "Entrar" }));
  await user.type(await screen.findByLabelText("Base en efectivo"), "50.000");
  await user.click(screen.getByRole("button", { name: "Abrir caja" }));
  return user;
}

async function scanTwoRicesAndCheckout(user: ReturnType<typeof userEvent.setup>) {
  const search = await screen.findByLabelText("Buscar producto");
  await user.type(search, "7702511000014{Enter}");
  await screen.findByText("Arroz Diana 500 g");
  await user.type(search, "7702511000014{Enter}");
  await screen.findByDisplayValue("2");
  await user.keyboard("{F9}");
  return screen.findByRole("dialog", { name: "Cobrar $5.000" });
}

beforeEach(() => {
  localStorage.clear();
  window.location.hash = "";
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("primera vez", () => {
  it("el asistente crea el negocio y entra directo a vender", async () => {
    const calls = mockServer((call) => {
      const route = `${call.method} ${call.path.split("?")[0]}`;
      if (route === "GET /setup") return { body: { needs_setup: true } };
      if (route === "POST /setup") return { status: 201, body: { access_token: "token-1" } };
      return cashierServer(() => ({ status: 201, body: SALE }))(call);
    });
    const user = userEvent.setup();
    render(<App />);

    await user.type(await screen.findByLabelText(/Nombre del negocio/), "Panadería La Espiga");
    await user.type(screen.getByLabelText("Su nombre"), "Ana Ruiz");
    await user.type(screen.getByLabelText(/Usuario para entrar/), "Dueño Ana");
    await user.type(screen.getByLabelText(/^Contraseña/), "clave-segura-1");
    await user.type(screen.getByLabelText("Repita la contraseña"), "clave-segura-1");
    await user.click(screen.getByRole("button", { name: "Empezar a vender" }));

    expect(await screen.findByLabelText("Base en efectivo")).toBeTruthy();
    expect(calls.find((c) => c.path === "/setup" && c.method === "POST")?.body).toEqual({
      business_name: "Panadería La Espiga",
      full_name: "Ana Ruiz",
      username: "duenoana",
      password: "clave-segura-1",
    });
  });
});

describe("venta en la caja", () => {
  it("escanea, cobra en efectivo con vueltas y muestra el tiquete", async () => {
    const calls = mockServer(cashierServer(() => ({ status: 201, body: SALE })));
    const user = await loginAndOpenCash();

    expect(calls.find((c) => c.path === "/cash-sessions")?.body).toEqual({ opening_amount: "50000.00" });
    const dialog = await scanTwoRicesAndCheckout(user);

    await user.type(within(dialog).getByLabelText("Monto recibido"), "10000");
    expect(within(dialog).getAllByText("$5.000").length).toBeGreaterThan(0); // vueltas
    await user.click(within(dialog).getByRole("button", { name: "Confirmar venta" }));

    const receipt = await screen.findByRole("dialog", { name: "Venta #1 registrada" });
    expect(within(receipt).getByText("Tienda Doña Rosa")).toBeTruthy();
    expect(within(receipt).getByText("Entregue de vueltas:")).toBeTruthy();
    const sale = calls.find((c) => c.method === "POST" && c.path === "/sales")!;
    expect(sale.body).toEqual({
      items: [{ product_id: "p-arroz", quantity: "2" }],
      payments: [{ method: "efectivo", amount: "10000.00" }],
    });
    expect(sale.headers["Idempotency-Key"]).toBeTruthy();
  });

  it("si la red falla, el reintento usa la misma clave y no duplica la venta", async () => {
    let attempts = 0;
    const calls = mockServer(cashierServer(() => (++attempts === 1 ? "network-error" : { status: 201, body: SALE })));
    const user = await loginAndOpenCash();
    const dialog = await scanTwoRicesAndCheckout(user);

    await user.click(within(dialog).getByRole("button", { name: "Exacto" }));
    await user.click(within(dialog).getByRole("button", { name: "Confirmar venta" }));
    expect(await within(dialog).findByRole("alert")).toHaveProperty("textContent", expect.stringMatching(/conexión/));
    await user.click(within(dialog).getByRole("button", { name: "Confirmar venta" }));

    await screen.findByText("Venta #1 registrada");
    const keys = calls.filter((c) => c.path === "/sales").map((c) => c.headers["Idempotency-Key"]);
    expect(keys).toHaveLength(2);
    expect(keys[0]).toBe(keys[1]);
  });

  it("no deja cobrar fiado sin cliente ni dar vueltas con Nequi", async () => {
    mockServer(cashierServer(() => ({ status: 201, body: SALE })));
    const user = await loginAndOpenCash();
    const dialog = await scanTwoRicesAndCheckout(user);
    const confirm = within(dialog).getByRole("button", { name: "Confirmar venta" });

    await user.click(within(dialog).getByRole("button", { name: "Fiado" }));
    expect(within(dialog).getByText("Para fiar, seleccione el cliente")).toBeTruthy();
    expect(confirm).toHaveProperty("disabled", true);

    await user.click(within(dialog).getByRole("button", { name: "Nequi" }));
    const amount = within(dialog).getByLabelText("Monto recibido");
    await user.clear(amount);
    await user.type(amount, "20000");
    expect(within(dialog).getByText(/Solo el efectivo puede dar vueltas/)).toBeTruthy();
    expect(confirm).toHaveProperty("disabled", true);
  });

  it("el cajero no ve las pantallas de administración", async () => {
    mockServer(cashierServer(() => ({ status: 201, body: SALE })));
    await loginAndOpenCash();
    const menu = await screen.findByRole("navigation", { name: "Menú principal" });
    const labels = within(menu).getAllByRole("link").map((link) => link.textContent);
    expect(labels.some((label) => label?.includes("Vender"))).toBe(true);
    expect(labels.some((label) => label?.includes("Reportes") || label?.includes("Usuarios"))).toBe(false);
  });
});
