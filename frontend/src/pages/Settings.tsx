// Ajustes del negocio: datos del tiquete, impuestos, reglas de venta y métodos de pago.

import { type FormEvent, useState } from "react";
import { api } from "../api";
import { BackupsCard } from "../components/Backups";
import { InvoicingCard } from "../components/Invoicing";
import { LicenseCard } from "../components/License";
import { PrinterCard } from "../components/Printing";
import { ErrorAlert, Field, toast, useAction } from "../components/ui";
import { useSession } from "../session";
import type { PaymentKind, PaymentMethod, Settings } from "../types";

const KIND_LABEL: Record<PaymentKind, string> = {
  cash: "Efectivo (entra al cajón y da vueltas)",
  electronic: "Electrónico (Nequi, tarjeta, transferencia)",
  credit: "Fiado (queda como deuda del cliente)",
};

export function SettingsPage() {
  const { settings, reloadSettings } = useSession();
  const [form, setForm] = useState<Settings>(settings);
  const { busy, error, run } = useAction();
  const set = (change: Partial<Settings>) => setForm((current) => ({ ...current, ...change }));

  function setMethod(index: number, change: Partial<PaymentMethod>) {
    set({ payment_methods: form.payment_methods.map((m, i) => (i === index ? { ...m, ...change } : m)) });
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    const done = await run(async () => {
      await api.patch<Settings>("/settings", {
        business_name: form.business_name,
        tax_id: form.tax_id,
        address: form.address,
        phone: form.phone,
        receipt_footer: form.receipt_footer,
        prices_include_tax: form.prices_include_tax,
        default_tax_rate: form.default_tax_rate,
        allow_negative_stock: form.allow_negative_stock,
        credit_sales_enabled: form.credit_sales_enabled,
        payment_methods: form.payment_methods,
      });
      await reloadSettings();
      return true;
    });
    if (done !== undefined) toast("Ajustes guardados");
  }

  return (
    <>
      <form onSubmit={submit}>
        <div className="page-header">
          <h1>Ajustes</h1>
          <button className="btn btn-primary" disabled={busy}>
            Guardar cambios
          </button>
        </div>
        <ErrorAlert error={error} />
        <div className="grid grid-2">
          <section className="card">
            <h2>Datos del negocio</h2>
            <p className="muted small">Aparecen en el tiquete.</p>
            <Field label="Nombre del negocio">
              <input className="input" value={form.business_name} onChange={(e) => set({ business_name: e.target.value })} required />
            </Field>
            <div className="form-grid">
              <Field label="NIT">
                <input className="input" value={form.tax_id} onChange={(e) => set({ tax_id: e.target.value })} />
              </Field>
              <Field label="Teléfono">
                <input className="input" value={form.phone} onChange={(e) => set({ phone: e.target.value })} />
              </Field>
            </div>
            <Field label="Dirección">
              <input className="input" value={form.address} onChange={(e) => set({ address: e.target.value })} />
            </Field>
            <Field label="Mensaje al pie del tiquete">
              <input className="input" value={form.receipt_footer} onChange={(e) => set({ receipt_footer: e.target.value })} />
            </Field>
          </section>

          <section className="card">
            <h2>Impuestos y reglas de venta</h2>
            <Field label="Impuesto por defecto para productos nuevos (%)" hint="19 o 5 (IVA), 8 (impuesto al consumo), 0 (exento)">
              <input className="input" inputMode="decimal" value={form.default_tax_rate} onChange={(e) => set({ default_tax_rate: e.target.value })} required />
            </Field>
            <label className="check">
              <input type="checkbox" checked={form.prices_include_tax} onChange={(e) => set({ prices_include_tax: e.target.checked })} />
              Los precios ya incluyen el impuesto (lo normal en tiendas)
            </label>
            <label className="check">
              <input type="checkbox" checked={form.credit_sales_enabled} onChange={(e) => set({ credit_sales_enabled: e.target.checked })} />
              Permitir ventas fiadas
            </label>
            <label className="check">
              <input type="checkbox" checked={form.allow_negative_stock} onChange={(e) => set({ allow_negative_stock: e.target.checked })} />
              Vender aunque el sistema marque cero existencias
            </label>
          </section>
        </div>

        <section className="card" style={{ marginTop: 16 }}>
          <h2>Métodos de pago</h2>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Nombre</th>
                  <th>Código</th>
                  <th>Tipo</th>
                  <th>Activo</th>
                </tr>
              </thead>
              <tbody>
                {form.payment_methods.map((method, index) => (
                  <tr key={index}>
                    <td>
                      <input className="input" value={method.name} onChange={(e) => setMethod(index, { name: e.target.value })} required />
                    </td>
                    <td>
                      <input
                        className="input"
                        value={method.code}
                        onChange={(e) => setMethod(index, { code: e.target.value.toLowerCase().replace(/\s+/g, "-") })}
                        required
                        disabled={settings.payment_methods.some((saved) => saved.code === method.code)}
                        title="El código no cambia después de guardado: así los reportes antiguos siguen cuadrando"
                      />
                    </td>
                    <td>
                      <select className="input" value={method.kind} onChange={(e) => setMethod(index, { kind: e.target.value as PaymentKind })}>
                        {Object.entries(KIND_LABEL).map(([kind, label]) => (
                          <option key={kind} value={kind}>
                            {label}
                          </option>
                        ))}
                      </select>
                    </td>
                    <td>
                      <input type="checkbox" checked={method.active} onChange={(e) => setMethod(index, { active: e.target.checked })} aria-label={`Activar ${method.name}`} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <button
            type="button"
            className="btn btn-sm"
            style={{ marginTop: 12 }}
            onClick={() => set({ payment_methods: [...form.payment_methods, { code: "", name: "", kind: "electronic", active: true }] })}
          >
            + Agregar método (p. ej. Bancolombia)
          </button>
        </section>
      </form>
      <PrinterCard />
      <BackupsCard />
      <InvoicingCard />
      <LicenseCard />
    </>
  );
}
