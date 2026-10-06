// Historial de ventas: consultar, reimprimir el tiquete y anular.

import { type FormEvent, useState } from "react";
import { api } from "../api";
import { usePrinting } from "../components/Printing";
import { Receipt } from "../components/Receipt";
import { Empty, ErrorAlert, Field, Modal, formatDateTime, toast, todayISO, useAction, useLoad } from "../components/ui";
import { formatMoney, toCents } from "../money";
import { useSession } from "../session";
import type { Items, Sale } from "../types";

export function SalesPage() {
  const [from, setFrom] = useState(todayISO);
  const [to, setTo] = useState(todayISO);
  const sales = useLoad(() => api.get<Items<Sale>>("/sales", { from, to, limit: 200 }), [from, to]);
  const [selected, setSelected] = useState<Sale | null>(null);

  const items = sales.data?.items ?? [];
  const completed = items.filter((sale) => sale.status === "completed");

  return (
    <>
      <div className="page-header">
        <h1>Ventas</h1>
        <div className="row">
          <label className="row small">
            Desde <input className="input input-inline" type="date" value={from} onChange={(e) => setFrom(e.target.value)} />
          </label>
          <label className="row small">
            Hasta <input className="input input-inline" type="date" value={to} onChange={(e) => setTo(e.target.value)} />
          </label>
        </div>
      </div>
      <ErrorAlert error={sales.error} />
      <p className="muted">
        {completed.length} ventas · {formatMoney(completed.reduce((sum, sale) => sum + toCents(sale.total), 0))}
        {items.length === 200 && " · se muestran las 200 más recientes"}
      </p>
      <section className="card table-wrap">
        {items.length === 0 ? (
          <Empty>{sales.loading ? "Cargando…" : "No hay ventas en estas fechas."}</Empty>
        ) : (
          <table>
            <thead>
              <tr>
                <th>#</th>
                <th>Fecha</th>
                <th>Productos</th>
                <th>Pago</th>
                <th>Estado</th>
                <th className="num">Total</th>
              </tr>
            </thead>
            <tbody>
              {items.map((sale) => (
                <tr key={sale.id} className="clickable" onClick={() => setSelected(sale)}>
                  <td>{sale.number}</td>
                  <td>{formatDateTime(sale.created_at)}</td>
                  <td className="small">
                    {sale.lines.map((line) => line.description).join(", ").slice(0, 60)}
                  </td>
                  <td className="small">{sale.payments.map((p) => p.name).join(" + ")}</td>
                  <td>
                    {sale.status === "voided" ? (
                      <span className="badge badge-danger">Anulada</span>
                    ) : (
                      <span className="badge badge-ok">Completada</span>
                    )}
                  </td>
                  <td className="num">{formatMoney(sale.total)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
      {selected && (
        <SaleModal
          sale={selected}
          onClose={() => setSelected(null)}
          onVoided={(sale) => {
            setSelected(sale);
            toast(`Venta #${sale.number} anulada`);
            void sales.reload();
          }}
        />
      )}
    </>
  );
}

function SaleModal(props: { sale: Sale; onClose: () => void; onVoided: (sale: Sale) => void }) {
  const { settings, can } = useSession();
  const [voiding, setVoiding] = useState(false);
  const [reason, setReason] = useState("");
  const { busy, error, run } = useAction();
  const printing = usePrinting();
  const { sale } = props;

  async function submit(event: FormEvent) {
    event.preventDefault();
    const voided = await run(() => api.post<Sale>(`/sales/${sale.id}/void`, { reason }));
    if (voided) {
      setVoiding(false);
      props.onVoided(voided);
    }
  }

  return (
    <Modal title={`Venta #${sale.number}`} onClose={props.onClose}>
      {sale.status === "voided" && (
        <div className="alert alert-error">
          Anulada el {formatDateTime(sale.voided_at)}: {sale.void_reason}
        </div>
      )}
      <ErrorAlert error={printing.error} />
      <Receipt sale={sale} settings={settings} />
      {voiding ? (
        <form onSubmit={submit} style={{ marginTop: 16 }}>
          <ErrorAlert error={error} />
          <p className="small muted">
            Al anular se devuelven los productos al inventario, se descuenta el efectivo de la caja y se reversa el fiado.
          </p>
          <Field label="Motivo de la anulación">
            <input className="input" value={reason} onChange={(e) => setReason(e.target.value)} autoFocus required />
          </Field>
          <div className="modal-actions">
            <button type="button" className="btn" onClick={() => setVoiding(false)}>
              Volver
            </button>
            <button className="btn btn-danger" disabled={busy}>
              Confirmar anulación
            </button>
          </div>
        </form>
      ) : (
        <div className="modal-actions">
          {can("void_sales") && sale.status === "completed" && (
            <button className="btn btn-danger" onClick={() => setVoiding(true)}>
              Anular venta
            </button>
          )}
          <button className="btn" disabled={printing.busy} onClick={() => printing.printSale(sale.id, true)}>
            Reimprimir
          </button>
          <button className="btn btn-primary" onClick={props.onClose}>
            Cerrar
          </button>
        </div>
      )}
    </Modal>
  );
}
