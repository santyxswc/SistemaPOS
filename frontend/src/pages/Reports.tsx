// Reportes: ventas por día o mes, métodos de pago y productos más vendidos.

import { useState } from "react";
import { api } from "../api";
import { Empty, ErrorAlert, Stat, todayISO, useAction, useLoad } from "../components/ui";
import { formatMoney, formatQuantity, toCents } from "../money";
import type { Items, ProductSales, SalesSummary } from "../types";

function iso(date: Date): string {
  const offset = date.getTimezoneOffset() * 60000;
  return new Date(date.getTime() - offset).toISOString().slice(0, 10);
}

const PRESETS: { label: string; range: () => [string, string] }[] = [
  { label: "Hoy", range: () => [todayISO(), todayISO()] },
  {
    label: "Últimos 7 días",
    range: () => {
      const start = new Date();
      start.setDate(start.getDate() - 6);
      return [iso(start), todayISO()];
    },
  },
  {
    label: "Este mes",
    range: () => {
      const now = new Date();
      return [iso(new Date(now.getFullYear(), now.getMonth(), 1)), todayISO()];
    },
  },
  {
    label: "Mes pasado",
    range: () => {
      const now = new Date();
      return [iso(new Date(now.getFullYear(), now.getMonth() - 1, 1)), iso(new Date(now.getFullYear(), now.getMonth(), 0))];
    },
  },
  {
    label: "Este año",
    range: () => [iso(new Date(new Date().getFullYear(), 0, 1)), todayISO()],
  },
];

export function ReportsPage() {
  const [[from, to], setRange] = useState<[string, string]>(() => PRESETS[0].range());
  const longRange = new Date(to).getTime() - new Date(from).getTime() > 62 * 86400000;
  const groupBy = longRange ? "month" : "day";
  const summary = useLoad(() => api.get<SalesSummary>("/reports/sales-summary", { from, to, group_by: groupBy }), [from, to, groupBy]);
  const top = useLoad(() => api.get<Items<ProductSales>>("/reports/top-products", { from, to, limit: 15 }), [from, to]);
  const data = summary.data;
  const exporting = useAction();

  return (
    <>
      <div className="page-header">
        <h1>Reportes</h1>
        <div className="row">
          {PRESETS.map((preset) => (
            <button key={preset.label} className="btn btn-sm" onClick={() => setRange(preset.range())}>
              {preset.label}
            </button>
          ))}
          <input className="input input-inline" type="date" value={from} onChange={(e) => setRange([e.target.value, to])} aria-label="Desde" />
          <input className="input input-inline" type="date" value={to} onChange={(e) => setRange([from, e.target.value])} aria-label="Hasta" />
          <button
            className="btn"
            disabled={exporting.busy}
            onClick={() => exporting.run(() => api.download("/reports/export", { from, to }, "ventas.xlsx"))}
            title="Resumen, ventas una por una con sus impuestos y productos vendidos: lo que pide el contador"
          >
            {exporting.busy ? "Exportando…" : "Exportar a Excel"}
          </button>
        </div>
      </div>
      <ErrorAlert error={summary.error ?? top.error ?? exporting.error} />
      {data && (
        <>
          <div className="stats">
            <Stat label="Ventas" value={formatMoney(data.total)} />
            <Stat label="Número de ventas" value={data.sales_count} />
            <Stat label="Ticket promedio" value={formatMoney(data.average_ticket)} />
            <Stat label="Impuestos" value={formatMoney(data.tax_total)} />
            <Stat label="Descuentos" value={formatMoney(data.discount_total)} />
            <Stat label="Anuladas" value={data.voided_count} />
          </div>
          <div className="grid grid-2">
            <section className="card">
              <h2>{groupBy === "month" ? "Ventas por mes" : "Ventas por día"}</h2>
              {data.by_period.length === 0 ? (
                <Empty>Sin ventas en este periodo.</Empty>
              ) : (
                <Bars rows={data.by_period.map((p) => ({ label: p.period, value: p.total }))} />
              )}
            </section>
            <section className="card">
              <h2>Por método de pago</h2>
              {data.by_payment_method.length === 0 ? (
                <Empty>Sin ventas en este periodo.</Empty>
              ) : (
                <Bars rows={data.by_payment_method.map((p) => ({ label: p.name, value: p.amount }))} />
              )}
            </section>
          </div>
        </>
      )}
      <section className="card" style={{ marginTop: 16 }}>
        <h2>Productos más vendidos</h2>
        {!top.data?.items.length ? (
          <Empty>Sin ventas en este periodo.</Empty>
        ) : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Producto</th>
                  <th className="num">Cantidad</th>
                  <th className="num">Vendido</th>
                </tr>
              </thead>
              <tbody>
                {top.data.items.map((item) => (
                  <tr key={item.product_id}>
                    <td>
                      {item.description} <span className="muted small">{item.sku}</span>
                    </td>
                    <td className="num">{formatQuantity(item.quantity)}</td>
                    <td className="num">{formatMoney(item.total)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </>
  );
}

function Bars({ rows }: { rows: { label: string; value: string }[] }) {
  const max = Math.max(...rows.map((row) => toCents(row.value)), 1);
  return (
    <div className="bars">
      {rows.map((row) => (
        <div className="bar-row" key={row.label}>
          <span className="small">{row.label}</span>
          <div className="bar-track" aria-hidden>
            <div className="bar-fill" style={{ width: `${(toCents(row.value) / max) * 100}%` }} />
          </div>
          <span className="num small">{formatMoney(row.value)}</span>
        </div>
      ))}
    </div>
  );
}
