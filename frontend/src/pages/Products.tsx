// Productos e inventario: catálogo, entradas de mercancía, ajustes por conteo y kárdex.

import { type FormEvent, useState } from "react";
import { api } from "../api";
import { ImportProductsDialog } from "../components/ImportProducts";
import { Empty, ErrorAlert, Field, Modal, formatDateTime, toast, useAction, useLoad } from "../components/ui";
import { centsToApi, formatMoney, formatQuantity, parseDecimal, thousandthsToApi, toCents } from "../money";
import { useSession } from "../session";
import type { Category, Items, Product, StockMovement, Unit } from "../types";

const UNITS: { value: Unit; label: string }[] = [
  { value: "unit", label: "Unidad" },
  { value: "kg", label: "Kilogramo" },
  { value: "lb", label: "Libra" },
  { value: "l", label: "Litro" },
];

const MOVEMENT_LABEL: Record<StockMovement["type"], string> = {
  initial: "Inventario inicial",
  purchase: "Entrada",
  adjustment: "Ajuste",
  sale: "Venta",
  sale_void: "Anulación",
};

type Dialog =
  | { kind: "product"; product: Product | null }
  | { kind: "category" }
  | { kind: "import" }
  | { kind: "purchase" | "adjust" | "history"; product: Product };

export function ProductsPage() {
  const { can } = useSession();
  const exporting = useAction();
  const [text, setText] = useState("");
  const [lowOnly, setLowOnly] = useState(false);
  const [showInactive, setShowInactive] = useState(false);
  const [dialog, setDialog] = useState<Dialog | null>(null);
  const categories = useLoad(() => api.get<Items<Category>>("/categories"), []);
  const products = useLoad(
    () =>
      lowOnly
        ? api.get<Items<Product>>("/inventory/low-stock")
        : api.get<Items<Product>>("/products", { q: text, include_inactive: showInactive, limit: 200 }),
    [text, lowOnly, showInactive],
  );
  const categoryName = (id: string | null) => categories.data?.items.find((c) => c.id === id)?.name ?? "";
  const close = () => setDialog(null);
  const saved = (message: string) => {
    setDialog(null);
    toast(message);
    void products.reload();
  };

  return (
    <>
      <div className="page-header">
        <h1>Productos</h1>
        {can("manage_catalog") && (
          <div className="row">
            <button
              className="btn"
              disabled={exporting.busy}
              onClick={() => exporting.run(() => api.download("/products/export", { include_inactive: showInactive }, "productos.xlsx"))}
            >
              Exportar a Excel
            </button>
            <button className="btn" onClick={() => setDialog({ kind: "import" })}>
              Importar
            </button>
            <button className="btn" onClick={() => setDialog({ kind: "category" })}>
              Nueva categoría
            </button>
            <button className="btn btn-primary" onClick={() => setDialog({ kind: "product", product: null })}>
              Nuevo producto
            </button>
          </div>
        )}
      </div>
      <div className="row" style={{ marginBottom: 12 }}>
        <input
          className="input"
          style={{ maxWidth: 380 }}
          placeholder="Buscar por nombre, código o SKU"
          value={text}
          onChange={(e) => setText(e.target.value)}
          disabled={lowOnly}
        />
        <label className="check" style={{ margin: 0 }}>
          <input type="checkbox" checked={lowOnly} onChange={(e) => setLowOnly(e.target.checked)} /> Solo stock bajo
        </label>
        <label className="check" style={{ margin: 0 }}>
          <input type="checkbox" checked={showInactive} onChange={(e) => setShowInactive(e.target.checked)} /> Incluir
          inactivos
        </label>
      </div>
      <ErrorAlert error={products.error ?? exporting.error} />
      <section className="card table-wrap">
        {!products.data?.items.length ? (
          <Empty>{products.loading ? "Cargando…" : "No hay productos que coincidan."}</Empty>
        ) : (
          <table>
            <thead>
              <tr>
                <th>Producto</th>
                <th>Categoría</th>
                <th className="num">Precio</th>
                <th className="num">Existencia</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {products.data.items.map((product) => (
                <tr key={product.id}>
                  <td>
                    <strong>{product.name}</strong> {!product.active && <span className="badge">Inactivo</span>}
                    <div className="muted small">
                      {product.sku}
                      {product.barcode && ` · ${product.barcode}`}
                    </div>
                  </td>
                  <td>{categoryName(product.category_id)}</td>
                  <td className="num">{formatMoney(product.price)}</td>
                  <td className="num">
                    {product.track_stock ? (
                      <span className={`badge ${product.is_low_stock ? "badge-warn" : ""}`}>
                        {formatQuantity(product.stock)}
                      </span>
                    ) : (
                      <span className="muted small">No controla</span>
                    )}
                  </td>
                  <td className="right">
                    <div className="row" style={{ justifyContent: "flex-end" }}>
                      {can("manage_inventory") && product.track_stock && (
                        <>
                          <button className="btn btn-sm" onClick={() => setDialog({ kind: "purchase", product })}>
                            Entrada
                          </button>
                          <button className="btn btn-sm" onClick={() => setDialog({ kind: "adjust", product })}>
                            Ajuste
                          </button>
                          <button className="btn btn-sm" onClick={() => setDialog({ kind: "history", product })}>
                            Kárdex
                          </button>
                        </>
                      )}
                      {can("manage_catalog") && (
                        <button className="btn btn-sm" onClick={() => setDialog({ kind: "product", product })}>
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

      {dialog?.kind === "product" && (
        <ProductForm
          product={dialog.product}
          categories={categories.data?.items ?? []}
          onClose={close}
          onSaved={() => saved(dialog.product ? "Producto actualizado" : "Producto creado")}
        />
      )}
      {dialog?.kind === "category" && (
        <CategoryForm
          onClose={close}
          onSaved={() => {
            void categories.reload();
            saved("Categoría creada");
          }}
        />
      )}
      {dialog?.kind === "import" && (
        <ImportProductsDialog
          onClose={close}
          onImported={(report) => {
            void categories.reload();
            const count = report.created + report.updated;
            saved(`${count.toLocaleString("es-CO")} producto${count === 1 ? "" : "s"} importado${count === 1 ? "" : "s"}`);
          }}
        />
      )}
      {dialog?.kind === "purchase" && <PurchaseForm product={dialog.product} onClose={close} onSaved={() => saved("Entrada registrada")} />}
      {dialog?.kind === "adjust" && <AdjustForm product={dialog.product} onClose={close} onSaved={() => saved("Inventario ajustado")} />}
      {dialog?.kind === "history" && <History product={dialog.product} onClose={close} />}
    </>
  );
}

function ProductForm(props: { product: Product | null; categories: Category[]; onClose: () => void; onSaved: () => void }) {
  const { settings } = useSession();
  const editing = props.product;
  const [form, setForm] = useState({
    name: editing?.name ?? "",
    sku: editing?.sku ?? "",
    barcode: editing?.barcode ?? "",
    category_id: editing?.category_id ?? "",
    price: editing?.price ?? "",
    cost: editing?.cost ?? "",
    tax_rate: editing?.tax_rate ?? settings.default_tax_rate,
    unit: editing?.unit ?? ("unit" as Unit),
    track_stock: editing?.track_stock ?? true,
    initial_stock: "",
    min_stock: editing?.min_stock ?? "",
    active: editing?.active ?? true,
  });
  const { busy, error, run } = useAction();
  const set = (change: Partial<typeof form>) => setForm((current) => ({ ...current, ...change }));

  async function submit(event: FormEvent) {
    event.preventDefault();
    const quantity = (text: string) => thousandthsToApi(parseDecimal(text || "0", 3) ?? 0);
    const body = {
      name: form.name,
      sku: form.sku || form.name.toUpperCase().replace(/[^A-Z0-9]+/g, "-").slice(0, 30),
      barcode: form.barcode || null,
      category_id: form.category_id || null,
      price: centsToApi(toCents(form.price)),
      cost: centsToApi(toCents(form.cost || "0")),
      tax_rate: form.tax_rate,
      unit: form.unit,
      track_stock: form.track_stock,
      min_stock: quantity(form.min_stock),
    };
    const done = await run(() =>
      editing
        ? api.patch(`/products/${editing.id}`, { ...body, active: form.active })
        : api.post("/products", { ...body, initial_stock: quantity(form.initial_stock) }),
    );
    if (done !== undefined) props.onSaved();
  }

  return (
    <Modal title={editing ? "Editar producto" : "Nuevo producto"} onClose={props.onClose} wide>
      <form onSubmit={submit}>
        <ErrorAlert error={error} />
        <Field label="Nombre">
          <input className="input" value={form.name} onChange={(e) => set({ name: e.target.value })} autoFocus required />
        </Field>
        <div className="form-grid">
          <Field label="Código de barras" hint="Escanéelo con el lector">
            <input className="input" value={form.barcode} onChange={(e) => set({ barcode: e.target.value })} />
          </Field>
          <Field label="SKU (código interno)" hint="Si lo deja vacío se genera del nombre">
            <input className="input" value={form.sku} onChange={(e) => set({ sku: e.target.value })} />
          </Field>
          <Field label="Categoría">
            <select className="input" value={form.category_id} onChange={(e) => set({ category_id: e.target.value })}>
              <option value="">Sin categoría</option>
              {props.categories.map((category) => (
                <option key={category.id} value={category.id}>
                  {category.name}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Precio de venta">
            <input className="input" inputMode="decimal" value={form.price} onChange={(e) => set({ price: e.target.value })} required />
          </Field>
          <Field label="Costo">
            <input className="input" inputMode="decimal" value={form.cost} onChange={(e) => set({ cost: e.target.value })} />
          </Field>
          <Field label="Impuesto %" hint={settings.prices_include_tax ? "Incluido en el precio" : "Se suma al precio"}>
            <input className="input" inputMode="decimal" value={form.tax_rate} onChange={(e) => set({ tax_rate: e.target.value })} required />
          </Field>
          <Field label="Se vende por">
            <select className="input" value={form.unit} onChange={(e) => set({ unit: e.target.value as Unit })}>
              {UNITS.map((unit) => (
                <option key={unit.value} value={unit.value}>
                  {unit.label}
                </option>
              ))}
            </select>
          </Field>
          {form.track_stock && !editing && (
            <Field label="Existencia inicial">
              <input className="input" inputMode="decimal" value={form.initial_stock} onChange={(e) => set({ initial_stock: e.target.value })} />
            </Field>
          )}
          {form.track_stock && (
            <Field label="Avisar cuando queden" hint="Stock mínimo">
              <input className="input" inputMode="decimal" value={form.min_stock} onChange={(e) => set({ min_stock: e.target.value })} />
            </Field>
          )}
        </div>
        <label className="check">
          <input type="checkbox" checked={form.track_stock} onChange={(e) => set({ track_stock: e.target.checked })} />
          Controlar existencias (desmarque para servicios o preparaciones)
        </label>
        {editing && (
          <label className="check">
            <input type="checkbox" checked={form.active} onChange={(e) => set({ active: e.target.checked })} />
            Activo (se puede vender)
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

function CategoryForm(props: { onClose: () => void; onSaved: () => void }) {
  const [name, setName] = useState("");
  const { busy, error, run } = useAction();
  async function submit(event: FormEvent) {
    event.preventDefault();
    if ((await run(() => api.post("/categories", { name }))) !== undefined) props.onSaved();
  }
  return (
    <Modal title="Nueva categoría" onClose={props.onClose}>
      <form onSubmit={submit}>
        <ErrorAlert error={error} />
        <Field label="Nombre">
          <input className="input" value={name} onChange={(e) => setName(e.target.value)} autoFocus required />
        </Field>
        <div className="modal-actions">
          <button className="btn btn-primary" disabled={busy}>
            Crear
          </button>
        </div>
      </form>
    </Modal>
  );
}

function PurchaseForm(props: { product: Product; onClose: () => void; onSaved: () => void }) {
  const [quantity, setQuantity] = useState("");
  const [cost, setCost] = useState("");
  const [note, setNote] = useState("");
  const { busy, error, run } = useAction();
  async function submit(event: FormEvent) {
    event.preventDefault();
    const done = await run(() =>
      api.post("/inventory/purchases", {
        product_id: props.product.id,
        quantity: thousandthsToApi(parseDecimal(quantity, 3) ?? 0),
        unit_cost: cost ? centsToApi(toCents(cost)) : null,
        note,
      }),
    );
    if (done !== undefined) props.onSaved();
  }
  return (
    <Modal title={`Entrada de mercancía: ${props.product.name}`} onClose={props.onClose}>
      <form onSubmit={submit}>
        <ErrorAlert error={error} />
        <p className="muted">Existencia actual: {formatQuantity(props.product.stock)}</p>
        <Field label="Cantidad que llegó">
          <input className="input input-big" inputMode="decimal" value={quantity} onChange={(e) => setQuantity(e.target.value)} autoFocus required />
        </Field>
        <Field label="Costo unitario (opcional)" hint="Actualiza el costo promedio del producto">
          <input className="input" inputMode="decimal" value={cost} onChange={(e) => setCost(e.target.value)} />
        </Field>
        <Field label="Nota (opcional)" hint="Ej.: factura del proveedor">
          <input className="input" value={note} onChange={(e) => setNote(e.target.value)} />
        </Field>
        <div className="modal-actions">
          <button type="button" className="btn" onClick={props.onClose}>
            Cancelar
          </button>
          <button className="btn btn-primary" disabled={busy}>
            Registrar entrada
          </button>
        </div>
      </form>
    </Modal>
  );
}

function AdjustForm(props: { product: Product; onClose: () => void; onSaved: () => void }) {
  const [counted, setCounted] = useState("");
  const [reason, setReason] = useState("");
  const { busy, error, run } = useAction();
  async function submit(event: FormEvent) {
    event.preventDefault();
    const done = await run(() =>
      api.post("/inventory/adjustments", {
        product_id: props.product.id,
        counted_quantity: thousandthsToApi(parseDecimal(counted, 3) ?? 0),
        reason,
      }),
    );
    if (done !== undefined) props.onSaved();
  }
  return (
    <Modal title={`Ajuste por conteo: ${props.product.name}`} onClose={props.onClose}>
      <form onSubmit={submit}>
        <ErrorAlert error={error} />
        <p className="muted">El sistema dice que hay {formatQuantity(props.product.stock)}. Escriba lo que contó.</p>
        <Field label="Cantidad contada">
          <input className="input input-big" inputMode="decimal" value={counted} onChange={(e) => setCounted(e.target.value)} autoFocus required />
        </Field>
        <Field label="Motivo" hint="Ej.: producto vencido, conteo mensual">
          <input className="input" value={reason} onChange={(e) => setReason(e.target.value)} required />
        </Field>
        <div className="modal-actions">
          <button type="button" className="btn" onClick={props.onClose}>
            Cancelar
          </button>
          <button className="btn btn-primary" disabled={busy}>
            Guardar ajuste
          </button>
        </div>
      </form>
    </Modal>
  );
}

function History(props: { product: Product; onClose: () => void }) {
  const movements = useLoad(
    () => api.get<Items<StockMovement>>("/inventory/movements", { product_id: props.product.id, limit: 100 }),
    [props.product.id],
  );
  return (
    <Modal title={`Kárdex: ${props.product.name}`} onClose={props.onClose} wide>
      <ErrorAlert error={movements.error} />
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Fecha</th>
              <th>Movimiento</th>
              <th className="num">Cantidad</th>
              <th className="num">Queda</th>
            </tr>
          </thead>
          <tbody>
            {movements.data?.items.map((movement) => (
              <tr key={movement.id}>
                <td>{formatDateTime(movement.created_at)}</td>
                <td>
                  {MOVEMENT_LABEL[movement.type]}
                  <div className="muted small">{movement.reference || movement.note}</div>
                </td>
                <td className="num">{formatQuantity(movement.quantity)}</td>
                <td className="num">{formatQuantity(movement.stock_after)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Modal>
  );
}
