// Clientes: datos, cupo de crédito, estado de cuenta y abonos a los fiados.

import { type FormEvent, useState } from "react";
import { api } from "../api";
import { Empty, ErrorAlert, Field, Modal, Stat, formatDateTime, toast, useAction, useLoad } from "../components/ui";
import { centsToApi, formatMoney, toCents } from "../money";
import { useSession } from "../session";
import type { Customer, Items, LedgerEntry } from "../types";

const ENTRY_LABEL: Record<LedgerEntry["type"], string> = {
  charge: "Compra fiada",
  payment: "Abono",
  reversal: "Venta anulada",
};

export function CustomersPage() {
  const { can } = useSession();
  const [text, setText] = useState("");
  const [onlyDebtors, setOnlyDebtors] = useState(false);
  const [editing, setEditing] = useState<Customer | null | "new">(null);
  const [statement, setStatement] = useState<Customer | null>(null);
  const customers = useLoad(() => api.get<Items<Customer>>("/customers", { q: text, limit: 200 }), [text]);

  const items = (customers.data?.items ?? []).filter((c) => !onlyDebtors || toCents(c.balance) > 0);
  const totalDebt = (customers.data?.items ?? []).reduce((sum, c) => sum + Math.max(0, toCents(c.balance)), 0);

  return (
    <>
      <div className="page-header">
        <h1>Clientes</h1>
        {can("manage_customers") && (
          <button className="btn btn-primary" onClick={() => setEditing("new")}>
            Nuevo cliente
          </button>
        )}
      </div>
      <div className="row" style={{ marginBottom: 12 }}>
        <input
          className="input"
          style={{ maxWidth: 380 }}
          placeholder="Buscar por nombre, cédula o teléfono"
          value={text}
          onChange={(e) => setText(e.target.value)}
        />
        <label className="check" style={{ margin: 0 }}>
          <input type="checkbox" checked={onlyDebtors} onChange={(e) => setOnlyDebtors(e.target.checked)} /> Solo con
          deuda
        </label>
        <span className="spacer" />
        <span className="muted">Por cobrar en esta lista: {formatMoney(totalDebt)}</span>
      </div>
      <ErrorAlert error={customers.error} />
      <section className="card table-wrap">
        {items.length === 0 ? (
          <Empty>{customers.loading ? "Cargando…" : "No hay clientes que coincidan."}</Empty>
        ) : (
          <table>
            <thead>
              <tr>
                <th>Cliente</th>
                <th>Teléfono</th>
                <th className="num">Debe</th>
                <th className="num">Cupo disponible</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {items.map((customer) => (
                <tr key={customer.id}>
                  <td>
                    <strong>{customer.name}</strong>
                    <div className="muted small">{customer.document}</div>
                  </td>
                  <td>{customer.phone}</td>
                  <td className="num">
                    {toCents(customer.balance) > 0 ? (
                      <span className="badge badge-warn">{formatMoney(customer.balance)}</span>
                    ) : (
                      formatMoney(customer.balance)
                    )}
                  </td>
                  <td className="num">{formatMoney(customer.available_credit)}</td>
                  <td className="right">
                    <div className="row" style={{ justifyContent: "flex-end" }}>
                      {can("collect_payments") && (
                        <button className="btn btn-sm" onClick={() => setStatement(customer)}>
                          Estado de cuenta
                        </button>
                      )}
                      {can("manage_customers") && (
                        <button className="btn btn-sm" onClick={() => setEditing(customer)}>
                          Editar
                        </button>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>

      {editing && (
        <CustomerForm
          customer={editing === "new" ? null : editing}
          onClose={() => setEditing(null)}
          onSaved={() => {
            toast(editing === "new" ? "Cliente creado" : "Cliente actualizado");
            setEditing(null);
            void customers.reload();
          }}
        />
      )}
      {statement && (
        <Statement customer={statement} onClose={() => setStatement(null)} onChanged={() => void customers.reload()} />
      )}
    </>
  );
}

function CustomerForm(props: { customer: Customer | null; onClose: () => void; onSaved: () => void }) {
  const { can } = useSession();
  const editing = props.customer;
  const [form, setForm] = useState({
    name: editing?.name ?? "",
    document: editing?.document ?? "",
    phone: editing?.phone ?? "",
    email: editing?.email ?? "",
    address: editing?.address ?? "",
    credit_limit: editing ? editing.credit_limit : "",
    active: editing?.active ?? true,
  });
  const { busy, error, run } = useAction();
  const set = (change: Partial<typeof form>) => setForm((current) => ({ ...current, ...change }));

  async function submit(event: FormEvent) {
    event.preventDefault();
    const body: Record<string, unknown> = {
      name: form.name,
      document: form.document || null,
      phone: form.phone,
      email: form.email,
      address: form.address,
    };
    if (can("grant_credit")) body.credit_limit = centsToApi(toCents(form.credit_limit || "0"));
    if (editing) body.active = form.active;
    const done = await run(() => (editing ? api.patch(`/customers/${editing.id}`, body) : api.post("/customers", body)));
    if (done !== undefined) props.onSaved();
  }

  return (
    <Modal title={editing ? "Editar cliente" : "Nuevo cliente"} onClose={props.onClose}>
      <form onSubmit={submit}>
        <ErrorAlert error={error} />
        <Field label="Nombre">
          <input className="input" value={form.name} onChange={(e) => set({ name: e.target.value })} autoFocus required />
        </Field>
        <div className="form-grid">
          <Field label="Cédula o NIT">
            <input className="input" value={form.document} onChange={(e) => set({ document: e.target.value })} />
          </Field>
          <Field label="Teléfono">
            <input className="input" inputMode="tel" value={form.phone} onChange={(e) => set({ phone: e.target.value })} />
          </Field>
          <Field label="Correo">
            <input className="input" type="email" value={form.email} onChange={(e) => set({ email: e.target.value })} />
          </Field>
          <Field label="Dirección">
            <input className="input" value={form.address} onChange={(e) => set({ address: e.target.value })} />
          </Field>
          {can("grant_credit") && (
            <Field label="Cupo de fiado" hint="0 = no se le fía">
              <input className="input" inputMode="decimal" value={form.credit_limit} onChange={(e) => set({ credit_limit: e.target.value })} />
            </Field>
          )}
        </div>
        {editing && (
          <label className="check">
            <input type="checkbox" checked={form.active} onChange={(e) => set({ active: e.target.checked })} /> Activo
          </label>
        )}
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

interface StatementData {
  customer: Customer;
  entries: LedgerEntry[];
}

function Statement(props: { customer: Customer; onClose: () => void; onChanged: () => void }) {
  const { settings } = useSession();
  const data = useLoad(() => api.get<StatementData>(`/customers/${props.customer.id}/statement`, { limit: 100 }), [props.customer.id]);
  const methods = settings.payment_methods.filter((m) => m.active && m.kind !== "credit");
  const [amount, setAmount] = useState("");
  const [method, setMethod] = useState(methods[0]?.code ?? "");
  const { busy, error, run } = useAction();
  const customer = data.data?.customer ?? props.customer;

  async function pay(event: FormEvent) {
    event.preventDefault();
    const done = await run(() =>
      api.post(`/customers/${customer.id}/payments`, { amount: centsToApi(toCents(amount)), method }),
    );
    if (done !== undefined) {
      toast("Abono registrado");
      setAmount("");
      void data.reload();
      props.onChanged();
    }
  }

  return (
    <Modal title={`Estado de cuenta: ${customer.name}`} onClose={props.onClose} wide>
      <div className="stats">
        <Stat label="Debe" value={formatMoney(customer.balance)} />
        <Stat label="Cupo" value={formatMoney(customer.credit_limit)} />
        <Stat label="Disponible" value={formatMoney(customer.available_credit)} />
      </div>
      {toCents(customer.balance) > 0 && (
        <form className="row" onSubmit={pay} style={{ marginBottom: 16 }}>
          <input
            className="input"
            style={{ maxWidth: 180 }}
            inputMode="decimal"
            placeholder="Valor del abono"
            value={amount}
            onChange={(e) => setAmount(e.target.value)}
            required
          />
          <select className="input" style={{ maxWidth: 200 }} value={method} onChange={(e) => setMethod(e.target.value)}>
            {methods.map((m) => (
              <option key={m.code} value={m.code}>
                {m.name}
              </option>
            ))}
          </select>
          <button className="btn btn-sm" type="button" onClick={() => setAmount(customer.balance)}>
            Todo
          </button>
          <button className="btn btn-primary" disabled={busy}>
            Registrar abono
          </button>
        </form>
      )}
      <ErrorAlert error={error ?? data.error} />
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Fecha</th>
              <th>Movimiento</th>
              <th className="num">Valor</th>
              <th className="num">Saldo</th>
            </tr>
          </thead>
          <tbody>
            {data.data?.entries.map((entry) => (
              <tr key={entry.id}>
                <td>{formatDateTime(entry.created_at)}</td>
                <td>
                  {ENTRY_LABEL[entry.type]}
                  <div className="muted small">{entry.note}</div>
                </td>
                <td className="num">
                  {entry.type === "charge" ? "+" : "−"}
                  {formatMoney(entry.amount)}
                </td>
                <td className="num">{formatMoney(entry.balance_after)}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {data.data?.entries.length === 0 && <Empty>Sin movimientos.</Empty>}
      </div>
    </Modal>
  );
}
