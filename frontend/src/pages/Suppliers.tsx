// Proveedores: cuentas por pagar, compras de mercancía con su factura y datos de cada proveedor.

import { type FormEvent, type KeyboardEvent, useState } from "react";
import { api } from "../api";
import { Empty, ErrorAlert, Field, Modal, Stat, formatDateTime, toast, useAction, useLoad } from "../components/ui";
import { centsToApi, formatMoney, formatQuantity, lineGross, parseDecimal, thousandthsToApi, toCents } from "../money";
import { useSession } from "../session";
import type {
  Items,
  Payables,
  Product,
  Purchase,
  PurchasePaymentMode,
  Supplier,
  SupplierEntry,
  SupplierStatement,
} from "../types";

const MODE_LABEL: Record<PurchasePaymentMode, string> = {
  cash_drawer: "Efectivo de la caja",
  external: "Pagada por fuera (transferencia, Nequi…)",
  credit: "A crédito (queda debiendo)",
};

const ENTRY_LABEL: Record<SupplierEntry["type"], string> = {
  purchase: "Compra a crédito",
  payment: "Pago",
};

/** "2026-10-20" → "20/10/2026" sin pasar por la zona horaria del navegador. */
export function formatDay(iso: string | null): string {
  if (!iso) return "—";
  const [year, month, day] = iso.split("-");
  return `${day}/${month}/${year}`;
}

type Tab = "payables" | "purchases" | "suppliers";

export function SuppliersPage() {
  const { can } = useSession();
  const tabs: { id: Tab; label: string; visible: boolean }[] = [
    { id: "payables", label: "Por pagar", visible: can("manage_suppliers") },
    { id: "purchases", label: "Compras", visible: true },
    { id: "suppliers", label: "Proveedores", visible: true },
  ];
  const visible = tabs.filter((t) => t.visible);
  const [tab, setTab] = useState<Tab>(visible[0].id);
  const [buying, setBuying] = useState(false);
  const [editing, setEditing] = useState<Supplier | null | "new">(null);
  const [statement, setStatement] = useState<Supplier | null>(null);
  const [version, setVersion] = useState(0); // recarga las pestañas después de un cambio
  const changed = () => setVersion((v) => v + 1);

  return (
    <>
      <div className="page-header">
        <h1>Proveedores</h1>
        <div className="row">
          {can("manage_suppliers") && (
            <button className="btn" onClick={() => setEditing("new")}>
              Nuevo proveedor
            </button>
          )}
          {can("manage_inventory") && (
            <button className="btn btn-primary" onClick={() => setBuying(true)}>
              Registrar compra
            </button>
          )}
        </div>
      </div>
      <div className="tabs" role="tablist">
        {visible.map((t) => (
          <button
            key={t.id}
            role="tab"
            aria-selected={tab === t.id}
            className={`tab ${tab === t.id ? "active" : ""}`}
            onClick={() => setTab(t.id)}
          >
            {t.label}
          </button>
        ))}
      </div>
      {tab === "payables" && <PayablesTab version={version} onOpen={setStatement} />}
      {tab === "purchases" && <PurchasesTab version={version} />}
      {tab === "suppliers" && <SuppliersTab version={version} onEdit={setEditing} onOpen={setStatement} />}

      {buying && (
        <PurchaseForm
          onClose={() => setBuying(false)}
          onSaved={(purchase) => {
            setBuying(false);
            toast(`Compra #${purchase.number} registrada por ${formatMoney(purchase.total)}`);
            changed();
          }}
        />
      )}
      {editing && (
        <SupplierForm
          supplier={editing === "new" ? null : editing}
          onClose={() => setEditing(null)}
          onSaved={() => {
            toast(editing === "new" ? "Proveedor creado" : "Proveedor actualizado");
            setEditing(null);
            changed();
          }}
        />
      )}
      {statement && <StatementModal supplier={statement} onClose={() => setStatement(null)} onChanged={changed} />}
    </>
  );
}

function PayablesTab(props: { version: number; onOpen: (supplier: Supplier) => void }) {
  const data = useLoad(() => api.get<Payables>("/suppliers/payables"), [props.version]);
  const payables = data.data;
  return (
    <>
      <ErrorAlert error={data.error} />
      <div className="stats">
        <Stat label="Total por pagar" value={formatMoney(payables?.total ?? null)} />
        <Stat label="Vencido" value={<span className={toCents(payables?.overdue ?? "0") > 0 ? "text-danger" : ""}>{formatMoney(payables?.overdue ?? null)}</span>} />
        <Stat label="Vence en 7 días" value={formatMoney(payables?.due_soon ?? null)} />
      </div>
      <section className="card table-wrap">
        {!payables?.suppliers.length ? (
          <Empty>{data.loading ? "Cargando…" : "No le debe nada a ningún proveedor."}</Empty>
        ) : (
          <table>
            <thead>
              <tr>
                <th>Proveedor</th>
                <th className="num">Debe</th>
                <th className="num">Vencido</th>
                <th>Próximo vencimiento</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {payables.suppliers.map((row) => (
                <tr key={row.supplier.id}>
                  <td>
                    <strong>{row.supplier.name}</strong>
                    <div className="muted small">{row.supplier.phone}</div>
                  </td>
                  <td className="num">{formatMoney(row.supplier.balance)}</td>
                  <td className="num">
                    {toCents(row.overdue) > 0 ? <span className="badge badge-danger">{formatMoney(row.overdue)}</span> : "—"}
                  </td>
                  <td>{formatDay(row.next_due_date)}</td>
                  <td className="right">
                    <button className="btn btn-sm" onClick={() => props.onOpen(row.supplier)}>
                      Pagar
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
    </>
  );
}

function PurchaseStatus({ purchase }: { purchase: Purchase }) {
  if (purchase.status === "paid") return <span className="badge badge-ok">Pagada</span>;
  if (purchase.overdue) return <span className="badge badge-danger">Vencida · debe {formatMoney(purchase.outstanding)}</span>;
  return <span className="badge badge-warn">Debe {formatMoney(purchase.outstanding)}</span>;
}

function PurchasesTab(props: { version: number }) {
  const [pendingOnly, setPendingOnly] = useState(false);
  const [detail, setDetail] = useState<Purchase | null>(null);
  const purchases = useLoad(
    () => api.get<Items<Purchase>>("/purchases", { pending: pendingOnly, limit: 200 }),
    [pendingOnly, props.version],
  );
  return (
    <>
      <div className="row" style={{ marginBottom: 12 }}>
        <label className="check" style={{ margin: 0 }}>
          <input type="checkbox" checked={pendingOnly} onChange={(e) => setPendingOnly(e.target.checked)} /> Solo las
          que se deben
        </label>
      </div>
      <ErrorAlert error={purchases.error} />
      <section className="card table-wrap">
        {!purchases.data?.items.length ? (
          <Empty>{purchases.loading ? "Cargando…" : "No hay compras registradas."}</Empty>
        ) : (
          <table>
            <thead>
              <tr>
                <th>#</th>
                <th>Fecha</th>
                <th>Proveedor</th>
                <th>Factura</th>
                <th className="num">Total</th>
                <th>Estado</th>
                <th>Vence</th>
              </tr>
            </thead>
            <tbody>
              {purchases.data.items.map((purchase) => (
                <tr key={purchase.id} className="clickable" onClick={() => setDetail(purchase)}>
                  <td>{purchase.number}</td>
                  <td>{formatDateTime(purchase.created_at)}</td>
                  <td>{purchase.supplier_name ?? <span className="muted">Sin proveedor</span>}</td>
                  <td>{purchase.invoice_number || "—"}</td>
                  <td className="num">{formatMoney(purchase.total)}</td>
                  <td>
                    <PurchaseStatus purchase={purchase} />
                  </td>
                  <td>{formatDay(purchase.due_date)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
      {detail && <PurchaseDetail purchase={detail} onClose={() => setDetail(null)} />}
    </>
  );
}

function PurchaseDetail(props: { purchase: Purchase; onClose: () => void }) {
  const { purchase } = props;
  return (
    <Modal title={`Compra #${purchase.number}`} onClose={props.onClose} wide>
      <div className="stats">
        <Stat label="Proveedor" value={purchase.supplier_name ?? "—"} />
        <Stat label="Factura" value={purchase.invoice_number || "—"} />
        <Stat label="Forma de pago" value={MODE_LABEL[purchase.payment_mode].split(" (")[0]} />
        <Stat label="Total" value={formatMoney(purchase.total)} />
      </div>
      <p>
        <PurchaseStatus purchase={purchase} /> {purchase.due_date && <span className="muted">Vence el {formatDay(purchase.due_date)}</span>}
      </p>
      {purchase.note && <p className="muted">{purchase.note}</p>}
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Producto</th>
              <th className="num">Cantidad</th>
              <th className="num">Costo unitario</th>
              <th className="num">Total</th>
            </tr>
          </thead>
          <tbody>
            {purchase.lines.map((line, index) => (
              <tr key={index}>
                <td>
                  {line.description}
                  <div className="muted small">{line.sku}</div>
                </td>
                <td className="num">{formatQuantity(line.quantity)}</td>
                <td className="num">{formatMoney(line.unit_cost)}</td>
                <td className="num">{formatMoney(line.total)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Modal>
  );
}

function SuppliersTab(props: {
  version: number;
  onEdit: (supplier: Supplier) => void;
  onOpen: (supplier: Supplier) => void;
}) {
  const { can } = useSession();
  const [text, setText] = useState("");
  const [showInactive, setShowInactive] = useState(false);
  const suppliers = useLoad(
    () => api.get<Items<Supplier>>("/suppliers", { q: text, include_inactive: showInactive, limit: 200 }),
    [text, showInactive, props.version],
  );
  return (
    <>
      <div className="row" style={{ marginBottom: 12 }}>
        <input
          className="input"
          style={{ maxWidth: 380 }}
          placeholder="Buscar por nombre, NIT, vendedor o teléfono"
          value={text}
          onChange={(e) => setText(e.target.value)}
        />
        <label className="check" style={{ margin: 0 }}>
          <input type="checkbox" checked={showInactive} onChange={(e) => setShowInactive(e.target.checked)} /> Incluir
          inactivos
        </label>
      </div>
      <ErrorAlert error={suppliers.error} />
      <section className="card table-wrap">
        {!suppliers.data?.items.length ? (
          <Empty>{suppliers.loading ? "Cargando…" : "No hay proveedores que coincidan."}</Empty>
        ) : (
          <table>
            <thead>
              <tr>
                <th>Proveedor</th>
                <th>Vendedor</th>
                <th>Teléfono</th>
                <th className="num">Se le debe</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {suppliers.data.items.map((supplier) => (
                <tr key={supplier.id}>
                  <td>
                    <strong>{supplier.name}</strong> {!supplier.active && <span className="badge">Inactivo</span>}
                    <div className="muted small">{supplier.document}</div>
                  </td>
                  <td>{supplier.contact_name}</td>
                  <td>{supplier.phone}</td>
                  <td className="num">
                    {toCents(supplier.balance) > 0 ? <span className="badge badge-warn">{formatMoney(supplier.balance)}</span> : formatMoney(supplier.balance)}
                  </td>
                  <td className="right">
                    {can("manage_suppliers") && (
                      <div className="row" style={{ justifyContent: "flex-end" }}>
                        <button className="btn btn-sm" onClick={() => props.onOpen(supplier)}>
                          Estado de cuenta
                        </button>
                        <button className="btn btn-sm" onClick={() => props.onEdit(supplier)}>
                          Editar
                        </button>
                      </div>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
    </>
  );
}

function SupplierForm(props: { supplier: Supplier | null; onClose: () => void; onSaved: () => void }) {
  const editing = props.supplier;
  const [form, setForm] = useState({
    name: editing?.name ?? "",
    document: editing?.document ?? "",
    contact_name: editing?.contact_name ?? "",
    phone: editing?.phone ?? "",
    email: editing?.email ?? "",
    address: editing?.address ?? "",
    notes: editing?.notes ?? "",
    active: editing?.active ?? true,
  });
  const { busy, error, run } = useAction();
  const set = (change: Partial<typeof form>) => setForm((current) => ({ ...current, ...change }));

  async function submit(event: FormEvent) {
    event.preventDefault();
    const { active, ...data } = form;
    const body: Record<string, unknown> = { ...data, document: form.document || null };
    if (editing) body.active = active;
    const done = await run(() => (editing ? api.patch(`/suppliers/${editing.id}`, body) : api.post("/suppliers", body)));
    if (done !== undefined) props.onSaved();
  }

  return (
    <Modal title={editing ? "Editar proveedor" : "Nuevo proveedor"} onClose={props.onClose}>
      <form onSubmit={submit}>
        <ErrorAlert error={error} />
        <Field label="Nombre o razón social">
          <input className="input" value={form.name} onChange={(e) => set({ name: e.target.value })} autoFocus required />
        </Field>
        <div className="form-grid">
          <Field label="NIT o cédula">
            <input className="input" value={form.document} onChange={(e) => set({ document: e.target.value })} />
          </Field>
          <Field label="Vendedor o contacto">
            <input className="input" value={form.contact_name} onChange={(e) => set({ contact_name: e.target.value })} />
          </Field>
          <Field label="Teléfono">
            <input className="input" inputMode="tel" value={form.phone} onChange={(e) => set({ phone: e.target.value })} />
          </Field>
          <Field label="Correo">
            <input className="input" type="email" value={form.email} onChange={(e) => set({ email: e.target.value })} />
          </Field>
        </div>
        <Field label="Dirección">
          <input className="input" value={form.address} onChange={(e) => set({ address: e.target.value })} />
        </Field>
        <Field label="Notas" hint="Ej.: visita los martes, pedido mínimo, días de crédito">
          <input className="input" value={form.notes} onChange={(e) => set({ notes: e.target.value })} />
        </Field>
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

interface DraftLine {
  product: Product;
  quantity: string;
  unitCost: string;
}

function draftTotal(line: DraftLine): number {
  return lineGross(toCents(line.unitCost || "0"), parseDecimal(line.quantity, 3) ?? 0);
}

function PurchaseForm(props: { onClose: () => void; onSaved: (purchase: Purchase) => void }) {
  const suppliers = useLoad(() => api.get<Items<Supplier>>("/suppliers", { limit: 200 }), []);
  const [supplierId, setSupplierId] = useState("");
  const [invoice, setInvoice] = useState("");
  const [mode, setMode] = useState<PurchasePaymentMode>("credit");
  const [dueDate, setDueDate] = useState("");
  const [note, setNote] = useState("");
  const [lines, setLines] = useState<DraftLine[]>([]);
  const [search, setSearch] = useState("");
  const found = useLoad(
    () => (search.trim() ? api.get<Items<Product>>("/products", { q: search, limit: 8 }) : Promise.resolve({ items: [] })),
    [search],
  );
  const { busy, error, setError, run } = useAction();
  const total = lines.reduce((sum, line) => sum + draftTotal(line), 0);

  function addProduct(product: Product) {
    setLines((current) => {
      const index = current.findIndex((line) => line.product.id === product.id);
      if (index >= 0) {
        // Escanear dos veces el mismo producto suma una unidad en lugar de repetir la fila.
        return current.map((line, i) =>
          i === index ? { ...line, quantity: thousandthsToApi((parseDecimal(line.quantity, 3) ?? 0) + 1000) } : line,
        );
      }
      return [...current, { product, quantity: "1", unitCost: toCents(product.cost) > 0 ? centsToApi(toCents(product.cost)) : "" }];
    });
    setSearch("");
  }

  async function onSearchKey(event: KeyboardEvent<HTMLInputElement>) {
    if (event.key !== "Enter") return;
    event.preventDefault();
    const code = search.trim();
    if (!code) return;
    try {
      addProduct(await api.get<Product>("/products/lookup", { code })); // lector de código de barras
    } catch {
      const first = found.data?.items[0];
      if (first) addProduct(first);
      else setError(`No se encontró «${code}»`);
    }
  }

  const setLine = (index: number, change: Partial<DraftLine>) =>
    setLines((current) => current.map((line, i) => (i === index ? { ...line, ...change } : line)));

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!lines.length) {
      setError("Agregue al menos un producto");
      return;
    }
    const purchase = await run(() =>
      api.post<Purchase>("/purchases", {
        supplier_id: supplierId || null,
        invoice_number: invoice,
        payment_mode: mode,
        due_date: mode === "credit" && dueDate ? dueDate : null,
        note,
        items: lines.map((line) => ({
          product_id: line.product.id,
          quantity: thousandthsToApi(parseDecimal(line.quantity, 3) ?? 0),
          unit_cost: centsToApi(toCents(line.unitCost || "0")),
        })),
      }),
    );
    if (purchase) props.onSaved(purchase);
  }

  const modes = Object.keys(MODE_LABEL) as PurchasePaymentMode[];
  return (
    <Modal title="Registrar compra de mercancía" onClose={props.onClose} wide>
      <form onSubmit={submit}>
        <ErrorAlert error={error ?? suppliers.error} />
        <div className="form-grid">
          <Field label="Proveedor" hint={mode === "credit" ? "Obligatorio para compras a crédito" : undefined}>
            <select className="input" value={supplierId} onChange={(e) => setSupplierId(e.target.value)} required={mode === "credit"}>
              <option value="">— Sin proveedor —</option>
              {suppliers.data?.items.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.name}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Número de factura del proveedor">
            <input className="input" value={invoice} onChange={(e) => setInvoice(e.target.value)} />
          </Field>
          <Field label="Forma de pago">
            <select className="input" value={mode} onChange={(e) => setMode(e.target.value as PurchasePaymentMode)}>
              {modes.map((m) => (
                <option key={m} value={m}>
                  {MODE_LABEL[m]}
                </option>
              ))}
            </select>
          </Field>
          {mode === "credit" && (
            <Field label="Vence el">
              <input className="input" type="date" value={dueDate} onChange={(e) => setDueDate(e.target.value)} />
            </Field>
          )}
        </div>

        <Field label="Agregar producto" hint="Escriba el nombre o escanee el código de barras y presione Enter">
          <input className="input" value={search} onChange={(e) => setSearch(e.target.value)} onKeyDown={onSearchKey} autoFocus />
        </Field>
        {search.trim() && !!found.data?.items.length && (
          <div className="search-results">
            {found.data.items.map((product) => (
              <button type="button" key={product.id} className="search-result" onClick={() => addProduct(product)}>
                <span>
                  {product.name} <span className="muted small">{product.sku}</span>
                </span>
                <span className="small muted">Costo {formatMoney(product.cost)}</span>
              </button>
            ))}
          </div>
        )}

        <div className="table-wrap" style={{ marginTop: 12 }}>
          <table>
            <thead>
              <tr>
                <th>Producto</th>
                <th className="num">Cantidad</th>
                <th className="num">Costo unitario</th>
                <th className="num">Total</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {lines.map((line, index) => (
                <tr key={line.product.id}>
                  <td>
                    {line.product.name}
                    <div className="muted small">Hay {formatQuantity(line.product.stock)}</div>
                  </td>
                  <td className="num">
                    <input
                      className="input input-num"
                      inputMode="decimal"
                      value={line.quantity}
                      onChange={(e) => setLine(index, { quantity: e.target.value })}
                      aria-label={`Cantidad de ${line.product.name}`}
                      required
                    />
                  </td>
                  <td className="num">
                    <input
                      className="input input-num"
                      inputMode="decimal"
                      value={line.unitCost}
                      onChange={(e) => setLine(index, { unitCost: e.target.value })}
                      aria-label={`Costo de ${line.product.name}`}
                      required
                    />
                  </td>
                  <td className="num">{formatMoney(draftTotal(line))}</td>
                  <td className="right">
                    <button type="button" className="btn btn-sm btn-danger" onClick={() => setLines(lines.filter((_, i) => i !== index))} aria-label={`Quitar ${line.product.name}`}>
                      ✕
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {!lines.length && <Empty>Todavía no ha agregado productos.</Empty>}
        </div>
        <Field label="Nota (opcional)">
          <input className="input" value={note} onChange={(e) => setNote(e.target.value)} />
        </Field>
        <div className="modal-actions">
          <strong style={{ marginRight: "auto", fontSize: "1.2rem" }}>Total: {formatMoney(total)}</strong>
          <button type="button" className="btn" onClick={props.onClose}>
            Cancelar
          </button>
          <button className="btn btn-primary" disabled={busy}>
            Guardar compra
          </button>
        </div>
      </form>
    </Modal>
  );
}

function StatementModal(props: { supplier: Supplier; onClose: () => void; onChanged: () => void }) {
  const data = useLoad(() => api.get<SupplierStatement>(`/suppliers/${props.supplier.id}/statement`, { limit: 100 }), [props.supplier.id]);
  const [amount, setAmount] = useState("");
  const [fromDrawer, setFromDrawer] = useState(false);
  const [method, setMethod] = useState("");
  const { busy, error, run } = useAction();
  const supplier = data.data?.supplier ?? props.supplier;

  async function pay(event: FormEvent) {
    event.preventDefault();
    const done = await run(() =>
      api.post(`/suppliers/${supplier.id}/payments`, {
        amount: centsToApi(toCents(amount)),
        from_cash_drawer: fromDrawer,
        method: fromDrawer ? "" : method,
      }),
    );
    if (done !== undefined) {
      toast("Pago registrado");
      setAmount("");
      void data.reload();
      props.onChanged();
    }
  }

  return (
    <Modal title={`Cuenta con ${supplier.name}`} onClose={props.onClose} wide>
      <div className="stats">
        <Stat label="Se le debe" value={formatMoney(supplier.balance)} />
        <Stat label="Facturas pendientes" value={data.data?.pending.length ?? "—"} />
        <Stat label="Teléfono" value={supplier.phone || "—"} />
      </div>
      {toCents(supplier.balance) > 0 && (
        <form className="row" onSubmit={pay} style={{ marginBottom: 16, flexWrap: "wrap" }}>
          <input
            className="input"
            style={{ maxWidth: 170 }}
            inputMode="decimal"
            placeholder="Valor del pago"
            value={amount}
            onChange={(e) => setAmount(e.target.value)}
            aria-label="Valor del pago"
            required
          />
          <button className="btn btn-sm" type="button" onClick={() => setAmount(supplier.balance)}>
            Todo
          </button>
          <label className="check" style={{ margin: 0 }}>
            <input type="checkbox" checked={fromDrawer} onChange={(e) => setFromDrawer(e.target.checked)} /> Sale del efectivo de
            mi caja
          </label>
          {!fromDrawer && (
            <input className="input" style={{ maxWidth: 200 }} placeholder="¿Cómo? (transferencia…)" value={method} onChange={(e) => setMethod(e.target.value)} aria-label="Forma de pago" />
          )}
          <button className="btn btn-primary" disabled={busy}>
            Registrar pago
          </button>
        </form>
      )}
      <ErrorAlert error={error ?? data.error} />
      {!!data.data?.pending.length && (
        <>
          <h3>Facturas pendientes (se pagan primero las que vencen antes)</h3>
          <div className="table-wrap" style={{ marginBottom: 16 }}>
            <table>
              <thead>
                <tr>
                  <th>Compra</th>
                  <th>Factura</th>
                  <th>Vence</th>
                  <th className="num">Total</th>
                  <th className="num">Debe</th>
                </tr>
              </thead>
              <tbody>
                {data.data.pending.map((purchase) => (
                  <tr key={purchase.id}>
                    <td>#{purchase.number}</td>
                    <td>{purchase.invoice_number || "—"}</td>
                    <td>
                      {formatDay(purchase.due_date)} {purchase.overdue && <span className="badge badge-danger">Vencida</span>}
                    </td>
                    <td className="num">{formatMoney(purchase.total)}</td>
                    <td className="num">{formatMoney(purchase.outstanding)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
      <h3>Movimientos</h3>
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
                  {entry.method && ` · ${entry.method}`}
                  <div className="muted small">{entry.note}</div>
                </td>
                <td className="num">
                  {entry.type === "purchase" ? "+" : "−"}
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
