// Caja: estado del turno, ingresos y retiros, cierre con arqueo e historial.

import { type FormEvent, useState } from "react";
import { ApiError, api } from "../api";
import { OpenCash } from "../components/OpenCash";
import { Empty, ErrorAlert, Field, Modal, Stat, formatDateTime, toast, useAction, useLoad } from "../components/ui";
import { centsToApi, formatMoney, toCents } from "../money";
import { useSession } from "../session";
import type { CashReport, CashSession, Items } from "../types";

const MOVEMENT_LABEL: Record<string, string> = {
  sale: "Venta",
  sale_void: "Anulación",
  deposit: "Ingreso",
  withdrawal: "Retiro",
  credit_collection: "Abono de cliente",
  supplier_payment: "Pago a proveedor",
};

async function loadCurrent(): Promise<CashReport | null> {
  try {
    return await api.get<CashReport>("/cash-sessions/current");
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) return null;
    throw error;
  }
}

export function CashPage() {
  const { can } = useSession();
  const current = useLoad(loadCurrent, []);
  const [movement, setMovement] = useState<"deposit" | "withdrawal" | null>(null);
  const [closing, setClosing] = useState(false);
  const [closed, setClosed] = useState<CashReport | null>(null);

  return (
    <>
      <div className="page-header">
        <h1>Caja</h1>
        {current.data && (
          <div className="row">
            <button className="btn" onClick={() => setMovement("deposit")}>
              Registrar ingreso
            </button>
            <button className="btn" onClick={() => setMovement("withdrawal")}>
              Registrar retiro
            </button>
            <button className="btn btn-primary" onClick={() => setClosing(true)}>
              Cerrar caja
            </button>
          </div>
        )}
      </div>
      <ErrorAlert error={current.error} />

      {closed && (
        <div className="alert alert-info">
          Caja cerrada. Diferencia: <strong>{formatMoney(closed.session.difference)}</strong>{" "}
          {differenceLabel(closed.session.difference)}
        </div>
      )}

      {current.loading && !current.data ? (
        <Empty>Cargando…</Empty>
      ) : current.data ? (
        <SessionDetail report={current.data} />
      ) : (
        <OpenCash
          onOpened={() => {
            setClosed(null);
            void current.reload();
          }}
        />
      )}

      {can("supervise_cash") && <SessionHistory key={closed?.session.id ?? "historial"} />}

      {movement && (
        <MovementModal
          kind={movement}
          onClose={() => setMovement(null)}
          onSaved={() => {
            setMovement(null);
            toast(movement === "deposit" ? "Ingreso registrado" : "Retiro registrado");
            void current.reload();
          }}
        />
      )}
      {closing && current.data && (
        <CloseModal
          report={current.data}
          onClose={() => setClosing(false)}
          onClosed={(report) => {
            setClosing(false);
            setClosed(report);
            current.setData(null);
          }}
        />
      )}
    </>
  );
}

function differenceLabel(difference: string | null): string {
  const cents = toCents(difference ?? "0");
  if (cents === 0) return "(cuadra exacto)";
  return cents > 0 ? "(sobrante)" : "(faltante)";
}

function SessionDetail({ report }: { report: CashReport }) {
  const { session } = report;
  return (
    <>
      <div className="stats">
        <Stat label="Base inicial" value={formatMoney(session.opening_amount)} />
        <Stat label="Efectivo esperado en cajón" value={formatMoney(session.expected_cash)} />
        <Stat label="Ventas del turno" value={`${report.sales_count} · ${formatMoney(report.sales_total)}`} />
        <Stat label="Anuladas" value={report.voided_count} />
      </div>
      <div className="grid grid-2">
        <section className="card">
          <h2>Por método de pago</h2>
          {report.totals_by_method.length === 0 ? (
            <Empty>Aún no hay ventas en este turno.</Empty>
          ) : (
            <table>
              <tbody>
                {report.totals_by_method.map((total) => (
                  <tr key={total.method}>
                    <td>{total.name}</td>
                    <td className="num">{formatMoney(total.amount)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </section>
        <section className="card">
          <h2>Movimientos de efectivo</h2>
          <p className="muted small">Abierta el {formatDateTime(session.opened_at)}</p>
          {session.movements.length === 0 ? (
            <Empty>Sin movimientos.</Empty>
          ) : (
            <div className="table-wrap" style={{ maxHeight: 360, overflowY: "auto" }}>
              <table>
                <tbody>
                  {[...session.movements].reverse().map((movement) => (
                    <tr key={movement.id}>
                      <td>
                        {MOVEMENT_LABEL[movement.type]}
                        <div className="muted small">{movement.reference || movement.note}</div>
                      </td>
                      <td className="muted small">{formatDateTime(movement.created_at)}</td>
                      <td className="num">{formatMoney(movement.amount)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>
      </div>
    </>
  );
}

function MovementModal(props: { kind: "deposit" | "withdrawal"; onClose: () => void; onSaved: () => void }) {
  const [amount, setAmount] = useState("");
  const [note, setNote] = useState("");
  const { busy, error, run } = useAction();

  async function submit(event: FormEvent) {
    event.preventDefault();
    const done = await run(() =>
      api.post("/cash-sessions/current/movements", {
        type: props.kind,
        amount: centsToApi(toCents(amount)),
        note,
      }),
    );
    if (done !== undefined) props.onSaved();
  }

  return (
    <Modal title={props.kind === "deposit" ? "Ingreso de efectivo" : "Retiro de efectivo"} onClose={props.onClose}>
      <form onSubmit={submit}>
        <ErrorAlert error={error} />
        <Field label="Monto">
          <input className="input input-big" inputMode="decimal" value={amount} onChange={(e) => setAmount(e.target.value)} autoFocus required />
        </Field>
        <Field label="Motivo" hint={props.kind === "deposit" ? "Ej.: cambio para el cajón" : "Ej.: pago a proveedor de pan"}>
          <input className="input" value={note} onChange={(e) => setNote(e.target.value)} required />
        </Field>
        <div className="modal-actions">
          <button type="button" className="btn" onClick={props.onClose}>
            Cancelar
          </button>
          <button className="btn btn-primary" disabled={busy}>
            Guardar
          </button>
        </div>
      </form>
    </Modal>
  );
}

function CloseModal(props: { report: CashReport; onClose: () => void; onClosed: (report: CashReport) => void }) {
  const [counted, setCounted] = useState("");
  const [note, setNote] = useState("");
  const { busy, error, run } = useAction();
  const expected = toCents(props.report.session.expected_cash);
  const difference = counted ? toCents(counted) - expected : null;

  async function submit(event: FormEvent) {
    event.preventDefault();
    const report = await run(() =>
      api.post<CashReport>("/cash-sessions/current/close", { counted_amount: centsToApi(toCents(counted)), note }),
    );
    if (report) props.onClosed(report);
  }

  return (
    <Modal title="Cerrar caja" onClose={props.onClose}>
      <form onSubmit={submit}>
        <ErrorAlert error={error} />
        <p>
          El sistema espera <strong>{formatMoney(expected)}</strong> en efectivo. Cuente el dinero del cajón y escriba el
          total. Después de cerrar no podrá registrar más ventas en esta caja.
        </p>
        <Field label="Efectivo contado">
          <input className="input input-big" inputMode="decimal" value={counted} onChange={(e) => setCounted(e.target.value)} autoFocus required />
        </Field>
        {difference !== null && (
          <div className={`alert ${difference === 0 ? "alert-info" : "alert-warn"}`}>
            {difference === 0
              ? "La caja cuadra exacto."
              : `${difference > 0 ? "Sobran" : "Faltan"} ${formatMoney(Math.abs(difference))}`}
          </div>
        )}
        <Field label="Observaciones (opcional)">
          <input className="input" value={note} onChange={(e) => setNote(e.target.value)} />
        </Field>
        <div className="modal-actions">
          <button type="button" className="btn" onClick={props.onClose}>
            Cancelar
          </button>
          <button className="btn btn-primary" disabled={busy || !counted}>
            Cerrar caja
          </button>
        </div>
      </form>
    </Modal>
  );
}

function SessionHistory() {
  const sessions = useLoad(() => api.get<Items<CashSession>>("/cash-sessions", { limit: 30 }), []);
  const [selected, setSelected] = useState<string | null>(null);

  return (
    <section className="card" style={{ marginTop: 16 }}>
      <h2>Historial de cajas</h2>
      <ErrorAlert error={sessions.error} />
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Apertura</th>
              <th>Cierre</th>
              <th>Estado</th>
              <th className="num">Esperado</th>
              <th className="num">Contado</th>
              <th className="num">Diferencia</th>
            </tr>
          </thead>
          <tbody>
            {sessions.data?.items.map((session) => (
              <tr key={session.id} className="clickable" onClick={() => setSelected(session.id)}>
                <td>{formatDateTime(session.opened_at)}</td>
                <td>{formatDateTime(session.closed_at)}</td>
                <td>
                  <span className={`badge ${session.status === "open" ? "badge-ok" : ""}`}>
                    {session.status === "open" ? "Abierta" : "Cerrada"}
                  </span>
                </td>
                <td className="num">{formatMoney(session.expected_cash)}</td>
                <td className="num">{formatMoney(session.counted_amount)}</td>
                <td className="num">
                  {session.difference !== null && (
                    <span className={`badge ${toCents(session.difference) === 0 ? "badge-ok" : "badge-warn"}`}>
                      {formatMoney(session.difference)}
                    </span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {selected && <SessionModal id={selected} onClose={() => setSelected(null)} />}
    </section>
  );
}

function SessionModal({ id, onClose }: { id: string; onClose: () => void }) {
  const report = useLoad(() => api.get<CashReport>(`/cash-sessions/${id}`), [id]);
  return (
    <Modal title="Detalle de caja" onClose={onClose} wide>
      <ErrorAlert error={report.error} />
      {report.data ? <SessionDetail report={report.data} /> : <Empty>Cargando…</Empty>}
    </Modal>
  );
}
