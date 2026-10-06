// Impresión directa en la impresora térmica (ESC/POS) y su configuración en Ajustes.

import { type FormEvent, useCallback, useState } from "react";
import { api } from "../api";
import { useSession } from "../session";
import type { PrinterConfig, PrinterKind } from "../types";
import { ErrorAlert, Field, toast, useAction, useLoad } from "./ui";

const KIND_LABEL: Record<PrinterKind, string> = {
  browser: "Desde el navegador (con el cuadro de impresión)",
  windows: "Impresora instalada en este computador",
  network: "Impresora de red (cable o Wi-Fi)",
};

const WIDTH_LABEL: Record<number, string> = {
  48: "80 mm (48 caracteres)",
  42: "80 mm con letra grande (42 caracteres)",
  32: "58 mm (32 caracteres)",
};

/** Imprime tiquetes por la impresora directa si hay una; si no, con el diálogo del navegador. */
export function usePrinting() {
  const { settings } = useSession();
  const direct = settings.printer.kind !== "browser";
  const { busy, error, run } = useAction();

  const printSale = useCallback(
    async (saleId: string, copy: boolean) => {
      if (!direct) {
        window.print();
        return true;
      }
      const done = await run(() => api.post(`/sales/${saleId}/print`, { copy }));
      if (done !== undefined) toast(copy ? "Copia enviada a la impresora" : "Tiquete enviado a la impresora");
      return done !== undefined;
    },
    [direct, run],
  );

  return { direct, autoPrint: direct && settings.printer.auto_print, printSale, busy, error };
}

export function PrinterCard() {
  const { settings, reloadSettings } = useSession();
  const [form, setForm] = useState<PrinterConfig>(settings.printer);
  const printers = useLoad(
    () => (form.kind === "windows" ? api.get<{ items: string[] }>("/printing/printers") : Promise.resolve({ items: [] })),
    [form.kind],
  );
  const saving = useAction();
  const testing = useAction();
  const set = (change: Partial<PrinterConfig>) => setForm((current) => ({ ...current, ...change }));

  async function save(event: FormEvent) {
    event.preventDefault();
    const done = await saving.run(async () => {
      await api.patch("/settings", { printer: form });
      await reloadSettings();
      return true;
    });
    if (done) toast("Impresora guardada");
  }

  async function test() {
    const done = await testing.run(() => api.post("/printing/test", { printer: form }));
    if (done !== undefined) toast("Página de prueba enviada");
  }

  const installed = printers.data?.items ?? [];
  return (
    <section className="card" style={{ marginTop: 16 }} aria-labelledby="printer-title">
      <h2 id="printer-title">Impresora de tiquetes</h2>
      <p className="muted small">
        Con impresión directa el tiquete sale sin el cuadro del navegador y el cajón monedero se abre solo en las ventas con
        efectivo. Funciona con impresoras térmicas ESC/POS (Epson, Bixolon, 3nStar, Digital POS y la mayoría de genéricas).
      </p>
      <form onSubmit={save}>
        <ErrorAlert error={saving.error ?? testing.error ?? printers.error} />
        <div className="form-grid">
          <Field label="Cómo imprimir">
            <select className="input" value={form.kind} onChange={(e) => set({ kind: e.target.value as PrinterKind, target: "" })}>
              {Object.entries(KIND_LABEL).map(([kind, label]) => (
                <option key={kind} value={kind}>
                  {label}
                </option>
              ))}
            </select>
          </Field>
          {form.kind === "windows" && (
            <Field label="Impresora" hint="La que está conectada al computador donde corre el sistema">
              <select className="input" value={form.target} onChange={(e) => set({ target: e.target.value })} required>
                <option value="">— Elija —</option>
                {installed.map((name) => (
                  <option key={name} value={name}>
                    {name}
                  </option>
                ))}
                {form.target && !installed.includes(form.target) && <option value={form.target}>{form.target}</option>}
              </select>
            </Field>
          )}
          {form.kind === "network" && (
            <Field label="Dirección IP" hint="Aparece en la hoja de configuración de la impresora. Puerto opcional: 192.168.1.50:9100">
              <input className="input" value={form.target} onChange={(e) => set({ target: e.target.value })} placeholder="192.168.1.50" required />
            </Field>
          )}
          {form.kind !== "browser" && (
            <Field label="Papel">
              <select className="input" value={form.width} onChange={(e) => set({ width: Number(e.target.value) })}>
                {Object.entries(WIDTH_LABEL).map(([width, label]) => (
                  <option key={width} value={width}>
                    {label}
                  </option>
                ))}
              </select>
            </Field>
          )}
        </div>
        {form.kind !== "browser" && (
          <>
            <label className="check">
              <input type="checkbox" checked={form.auto_print} onChange={(e) => set({ auto_print: e.target.checked })} />
              Imprimir el tiquete automáticamente al terminar cada venta
            </label>
            <label className="check">
              <input type="checkbox" checked={form.open_drawer} onChange={(e) => set({ open_drawer: e.target.checked })} />
              Abrir el cajón monedero en las ventas con efectivo
            </label>
          </>
        )}
        <div className="row" style={{ marginTop: 12 }}>
          <button className="btn btn-primary" disabled={saving.busy}>
            Guardar impresora
          </button>
          {form.kind !== "browser" && (
            <button type="button" className="btn" disabled={testing.busy} onClick={test}>
              Imprimir prueba
            </button>
          )}
        </div>
      </form>
    </section>
  );
}
