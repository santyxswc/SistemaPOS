// Facturación electrónica: estado de la bandeja de salida y revisión de documentos con problemas.

import { useEffect } from "react";
import { api } from "../api";
import type { ElectronicDocument, InvoicingStatus, Items } from "../types";
import { Empty, ErrorAlert, Stat, formatDateTime, toast, useAction, useLoad } from "./ui";

const STATUS_LABEL: Record<ElectronicDocument["status"], string> = {
  pending: "En cola",
  accepted: "Aceptado",
  rejected: "Rechazado",
  failed: "Falló",
};

const STATUS_BADGE: Record<ElectronicDocument["status"], string> = {
  pending: "badge-warn",
  accepted: "badge-ok",
  rejected: "badge-danger",
  failed: "badge-danger",
};

const KIND_LABEL: Record<ElectronicDocument["kind"], string> = {
  invoice: "Documento de venta",
  credit_note: "Nota crédito (anulación)",
};

// El aviso y la tarjeta de Ajustes cargan el estado por separado; este evento los mantiene de acuerdo.
const INVOICING_CHANGED = "pos:invoicing-changed";

/** Franja superior para el administrador cuando hay documentos rechazados o que no se pudieron enviar. */
export function InvoicingBanner({ onOpenSettings }: { onOpenSettings: () => void }) {
  const { data, reload } = useLoad(() => api.get<InvoicingStatus>("/invoicing"), []);
  useEffect(() => {
    const onChange = () => void reload();
    window.addEventListener(INVOICING_CHANGED, onChange);
    return () => window.removeEventListener(INVOICING_CHANGED, onChange);
  }, [reload]);
  if (!data?.needs_attention) return null;
  const count = data.needs_attention;
  return (
    <div className="alert alert-error license-banner" role="status">
      <span>
        {count === 1 ? "Hay 1 documento electrónico" : `Hay ${count} documentos electrónicos`} sin aceptar por la DIAN.
        Revíselos para no tener problemas con la facturación.
      </span>
      <button className="btn btn-sm" onClick={onOpenSettings}>
        Revisar
      </button>
    </div>
  );
}

export function InvoicingCard() {
  const status = useLoad(() => api.get<InvoicingStatus>("/invoicing"), []);
  const problems = useLoad(
    () => api.get<Items<ElectronicDocument>>("/invoicing/documents", { status: "failed,rejected,pending", limit: 100 }),
    [],
  );
  const { busy, error, run } = useAction();

  async function retry(document: ElectronicDocument) {
    const done = await run(() => api.post(`/invoicing/documents/${document.id}/retry`));
    if (done !== undefined) {
      toast(`Venta #${document.sale_number}: se intentará enviar de nuevo`);
      await Promise.all([status.reload(), problems.reload()]);
      window.dispatchEvent(new Event(INVOICING_CHANGED));
    }
  }

  const data = status.data;
  return (
    <section className="card" style={{ marginTop: 16 }} aria-labelledby="invoicing-title">
      <h2 id="invoicing-title">Facturación electrónica</h2>
      <ErrorAlert error={status.error ?? problems.error ?? error} />
      {data && !data.enabled && (
        <p className="muted">
          Desactivada: las ventas no generan documentos electrónicos. Para emitirlos ante la DIAN se necesita un proveedor
          tecnológico autorizado; su técnico lo conecta con <code>POS_INVOICE_PROVIDER</code> en el archivo de
          configuración.
        </p>
      )}
      {data?.enabled && (
        <>
          <p className="muted small">
            Proveedor: <strong>{data.provider}</strong>. Cada venta queda en cola y se envía sola; si no hay internet se
            reintenta más tarde sin detener la caja.
          </p>
          <div className="stats">
            <Stat label="Aceptados" value={data.counts.accepted} />
            <Stat label="En cola" value={data.counts.pending} />
            <Stat label="Rechazados" value={data.counts.rejected} />
            <Stat label="Fallaron" value={data.counts.failed} />
          </div>
        </>
      )}
      {(data?.enabled || !!problems.data?.items.length) && (
        <div className="table-wrap">
          {!problems.data?.items.length ? (
            <Empty>{problems.loading ? "Cargando…" : "Todo al día: no hay documentos pendientes."}</Empty>
          ) : (
            <table>
              <thead>
                <tr>
                  <th>Venta</th>
                  <th>Documento</th>
                  <th>Estado</th>
                  <th>Detalle</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {problems.data.items.map((document) => (
                  <tr key={document.id}>
                    <td>#{document.sale_number}</td>
                    <td>{KIND_LABEL[document.kind]}</td>
                    <td>
                      <span className={`badge ${STATUS_BADGE[document.status]}`}>{STATUS_LABEL[document.status]}</span>
                      {document.attempts > 0 && <div className="muted small">{document.attempts} intento(s)</div>}
                    </td>
                    <td className="small">
                      {document.last_error ?? "—"}
                      {document.status === "pending" && document.next_attempt_at && (
                        <div className="muted">Próximo intento: {formatDateTime(document.next_attempt_at)}</div>
                      )}
                    </td>
                    <td className="right">
                      {(document.status === "failed" || document.status === "rejected") && (
                        <button className="btn btn-sm" disabled={busy} onClick={() => retry(document)}>
                          Reintentar
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}
    </section>
  );
}
