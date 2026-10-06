// Pantalla de venta: escanear o buscar, ajustar cantidades y cobrar con uno o varios métodos.

import { type KeyboardEvent, useEffect, useMemo, useRef, useState } from "react";
import { ApiError, api } from "../api";
import {
  type CartLine,
  type PaymentDraft,
  addToCart,
  cartTotal,
  lineAmount,
  newRequestId,
  paymentStatus,
  quickCashAmounts,
} from "../cart";
import { CustomerPicker } from "../components/CustomerPicker";
import { OpenCash } from "../components/OpenCash";
import { Receipt } from "../components/Receipt";
import { ConfirmDialog, ErrorAlert, Modal, useAction } from "../components/ui";
import {
  type Cents,
  centsToApi,
  formatMoney,
  formatQuantity,
  parseDecimal,
  thousandthsToApi,
  toCents,
} from "../money";
import { useSession } from "../session";
import type { CashReport, Customer, Items, Product, Sale } from "../types";

const UNIT_LABEL = { unit: "und", kg: "kg", lb: "lb", l: "L" } as const;

export function SellPage() {
  const [cash, setCash] = useState<"loading" | "open" | "closed">("loading");

  const checkCash = () =>
    api
      .get<CashReport>("/cash-sessions/current")
      .then(() => setCash("open"))
      .catch((error) => setCash(error instanceof ApiError && error.status === 404 ? "closed" : "open"));

  useEffect(() => {
    void checkCash();
  }, []);

  if (cash === "loading") return <div className="empty">Cargando…</div>;
  if (cash === "closed") {
    return (
      <>
        <div className="page-header">
          <h1>Vender</h1>
        </div>
        <OpenCash onOpened={() => setCash("open")} />
      </>
    );
  }
  return <Register />;
}

function Register() {
  const { settings, can } = useSession();
  const [lines, setLines] = useState<CartLine[]>([]);
  const [checkout, setCheckout] = useState(false);
  const [lastSale, setLastSale] = useState<{ sale: Sale; customer: Customer | null } | null>(null);
  const [confirmingClear, setConfirmingClear] = useState(false);
  const searchRef = useRef<HTMLInputElement>(null);

  const total = cartTotal(lines, settings.prices_include_tax);
  const units = lines.reduce((sum, line) => sum + line.quantity, 0);

  useEffect(() => {
    const onKey = (event: globalThis.KeyboardEvent) => {
      if (event.key === "F9" && lines.length > 0 && !checkout && !confirmingClear) {
        event.preventDefault();
        setCheckout(true);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [lines.length, checkout, confirmingClear]);

  const focusSearch = () => window.setTimeout(() => searchRef.current?.focus(), 0);

  function update(index: number, change: Partial<CartLine>) {
    setLines((current) => current.map((line, i) => (i === index ? { ...line, ...change } : line)));
  }

  return (
    <>
      <div className="page-header">
        <h1>Vender</h1>
        <span className="muted small">Escanee o escriba · F9 cobrar · Esc cerrar</span>
      </div>
      <div className="pos">
        <section className="card">
          <ProductSearch
            inputRef={searchRef}
            onPick={(product) => setLines((current) => addToCart(current, product))}
            onEmptyEnter={() => lines.length > 0 && setCheckout(true)}
          />
          <div className="table-wrap" style={{ marginTop: 16 }}>
            {lines.length === 0 ? (
              <div className="empty">Escanee un código de barras o busque un producto para empezar.</div>
            ) : (
              <table>
                <thead>
                  <tr>
                    <th>Producto</th>
                    <th>Cantidad</th>
                    <th className="num">Precio</th>
                    {can("apply_discounts") && <th className="num">Descuento</th>}
                    <th className="num">Total</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {lines.map((line, index) => (
                    <CartRow
                      key={line.product.id}
                      line={line}
                      amount={lineAmount(line, settings.prices_include_tax)}
                      allowDiscount={can("apply_discounts")}
                      onChange={(change) => update(index, change)}
                      onRemove={() => setLines((current) => current.filter((_, i) => i !== index))}
                    />
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </section>

        <aside className="card total-box">
          <div className="muted">Total a pagar</div>
          <div className="grand-total">{formatMoney(total)}</div>
          <div className="muted small" style={{ marginBottom: 16 }}>
            {lines.length} {lines.length === 1 ? "producto" : "productos"} · {formatQuantity(units / 1000)}{" "}
            {units === 1000 ? "unidad" : "unidades"}
            {!settings.prices_include_tax && " · impuesto incluido en el total"}
          </div>
          <button
            className="btn btn-primary btn-big"
            style={{ width: "100%" }}
            disabled={lines.length === 0}
            onClick={() => setCheckout(true)}
          >
            Cobrar (F9)
          </button>
          <button
            className="btn"
            style={{ width: "100%", marginTop: 8 }}
            disabled={lines.length === 0}
            onClick={() => setConfirmingClear(true)}
          >
            Cancelar venta
          </button>
        </aside>
      </div>

      {checkout && (
        <Checkout
          lines={lines}
          total={total}
          onClose={() => {
            setCheckout(false);
            focusSearch();
          }}
          onDone={(sale, customer) => {
            setCheckout(false);
            setLines([]);
            setLastSale({ sale, customer });
          }}
        />
      )}

      {confirmingClear && (
        <ConfirmDialog
          title="Cancelar venta"
          message={
            lines.length === 1
              ? "Se quitará el producto de la venta actual."
              : `Se quitarán los ${lines.length} productos de la venta actual.`
          }
          confirmLabel="Sí, vaciar la venta"
          danger
          onCancel={() => {
            setConfirmingClear(false);
            focusSearch();
          }}
          onConfirm={() => {
            setConfirmingClear(false);
            setLines([]);
            focusSearch();
          }}
        />
      )}

      {lastSale && (
        <Modal
          title={`Venta #${lastSale.sale.number} registrada`}
          onClose={() => {
            setLastSale(null);
            focusSearch();
          }}
        >
          {lastSale.sale.change !== "0.00" && (
            <div className="alert alert-info">
              Entregue de vueltas: <span className="change">{formatMoney(lastSale.sale.change)}</span>
            </div>
          )}
          <Receipt sale={lastSale.sale} settings={settings} customerName={lastSale.customer?.name} />
          <div className="modal-actions">
            <button className="btn" onClick={() => window.print()}>
              Imprimir tiquete
            </button>
            <button
              className="btn btn-primary"
              autoFocus
              onClick={() => {
                setLastSale(null);
                focusSearch();
              }}
            >
              Nueva venta
            </button>
          </div>
        </Modal>
      )}
    </>
  );
}

function ProductSearch(props: {
  inputRef: React.RefObject<HTMLInputElement | null>;
  onPick: (product: Product) => void;
  onEmptyEnter: () => void;
}) {
  const [text, setText] = useState("");
  const [results, setResults] = useState<Product[]>([]);
  const [selected, setSelected] = useState(0);
  const [message, setMessage] = useState<string | null>(null);

  useEffect(() => {
    const query = text.trim();
    if (query.length < 2 || /^\d{6,}$/.test(query)) {
      setResults([]);
      return;
    }
    const timer = window.setTimeout(() => {
      api
        .get<Items<Product>>("/products", { q: query, limit: 12 })
        .then((data) => {
          setResults(data.items);
          setSelected(0);
        })
        .catch(() => setResults([]));
    }, 200);
    return () => window.clearTimeout(timer);
  }, [text]);

  function pick(product: Product) {
    props.onPick(product);
    setText("");
    setResults([]);
    setMessage(null);
    props.inputRef.current?.focus();
  }

  async function onKeyDown(event: KeyboardEvent<HTMLInputElement>) {
    if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      event.preventDefault();
      const step = event.key === "ArrowDown" ? 1 : -1;
      setSelected((current) => Math.min(Math.max(current + step, 0), Math.max(results.length - 1, 0)));
      return;
    }
    if (event.key !== "Enter") return;
    event.preventDefault();
    const code = text.trim();
    if (!code) {
      props.onEmptyEnter();
      return;
    }
    if (results[selected] && !/^\d{6,}$/.test(code)) {
      pick(results[selected]);
      return;
    }
    // Un lector de código de barras escribe el código y presiona Enter.
    try {
      pick(await api.get<Product>("/products/lookup", { code }));
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Producto no encontrado");
      setText("");
    }
  }

  return (
    <div>
      <input
        ref={props.inputRef}
        className="input input-big"
        placeholder="Código de barras o nombre del producto"
        value={text}
        onChange={(e) => setText(e.target.value)}
        onKeyDown={onKeyDown}
        autoFocus
        aria-label="Buscar producto"
      />
      {message && (
        <div className="alert alert-warn" style={{ marginTop: 8 }} role="alert">
          {message}
        </div>
      )}
      {results.length > 0 && (
        <div className="search-results" role="listbox">
          {results.map((product, index) => (
            <button
              key={product.id}
              className={`search-result ${index === selected ? "selected" : ""}`}
              onClick={() => pick(product)}
              role="option"
              aria-selected={index === selected}
            >
              <span>
                <strong>{product.name}</strong> <span className="muted small">{product.sku}</span>
              </span>
              <span className="row">
                {product.track_stock && (
                  <span className={`badge ${product.is_low_stock ? "badge-warn" : ""}`}>
                    {formatQuantity(product.stock)} {UNIT_LABEL[product.unit]}
                  </span>
                )}
                <strong>{formatMoney(product.price)}</strong>
              </span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

function CartRow(props: {
  line: CartLine;
  amount: Cents;
  allowDiscount: boolean;
  onChange: (change: Partial<CartLine>) => void;
  onRemove: () => void;
}) {
  const { line } = props;
  const fractional = line.product.unit !== "unit";
  const step = 1000;
  const [qtyText, setQtyText] = useState(thousandthsToApi(line.quantity));

  useEffect(() => setQtyText(thousandthsToApi(line.quantity)), [line.quantity]);

  function commitQuantity(value: string) {
    const parsed = parseDecimal(value, 3);
    if (parsed === null || parsed <= 0 || (!fractional && parsed % 1000 !== 0)) {
      setQtyText(thousandthsToApi(line.quantity));
      return;
    }
    props.onChange({ quantity: parsed });
  }

  const overStock = line.product.track_stock && line.quantity > Number(line.product.stock) * 1000;

  return (
    <tr>
      <td>
        <strong>{line.product.name}</strong>
        <div className="muted small">
          {line.product.sku}
          {overStock && <span className="badge badge-warn" style={{ marginLeft: 6 }}>Solo hay {formatQuantity(line.product.stock)}</span>}
        </div>
      </td>
      <td>
        <span className="qty">
          <button
            className="btn btn-sm"
            aria-label="Menos"
            disabled={line.quantity <= step}
            onClick={() => props.onChange({ quantity: line.quantity - step })}
          >
            −
          </button>
          <input
            className="input"
            inputMode="decimal"
            value={qtyText}
            onChange={(e) => setQtyText(e.target.value)}
            onBlur={(e) => commitQuantity(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && commitQuantity(e.currentTarget.value)}
            aria-label={`Cantidad de ${line.product.name}`}
          />
          <button className="btn btn-sm" aria-label="Más" onClick={() => props.onChange({ quantity: line.quantity + step })}>
            +
          </button>
          <span className="muted small">{UNIT_LABEL[line.product.unit]}</span>
        </span>
      </td>
      <td className="num">{formatMoney(line.product.price)}</td>
      {props.allowDiscount && (
        <td className="num">
          <input
            className="input"
            style={{ width: 100, textAlign: "right" }}
            inputMode="decimal"
            placeholder="0"
            defaultValue={line.discount ? centsToApi(line.discount) : ""}
            onBlur={(e) => props.onChange({ discount: Math.max(0, toCents(e.target.value || "0")) })}
            aria-label={`Descuento de ${line.product.name}`}
          />
        </td>
      )}
      <td className="num">
        <strong>{formatMoney(props.amount)}</strong>
      </td>
      <td className="right">
        <button className="btn btn-sm btn-danger" onClick={props.onRemove} aria-label={`Quitar ${line.product.name}`}>
          Quitar
        </button>
      </td>
    </tr>
  );
}

function Checkout(props: {
  lines: CartLine[];
  total: Cents;
  onClose: () => void;
  onDone: (sale: Sale, customer: Customer | null) => void;
}) {
  const { settings } = useSession();
  const methods = settings.payment_methods.filter(
    (method) => method.active && (method.kind !== "credit" || settings.credit_sales_enabled),
  );
  const firstCash = methods.find((method) => method.kind === "cash") ?? methods[0];
  const [payments, setPayments] = useState<{ method: string; text: string }[]>([
    { method: firstCash.code, text: "" },
  ]);
  const [customer, setCustomer] = useState<Customer | null>(null);
  // La misma clave en cada reintento: si la red falla después de cobrar, la venta no se duplica.
  const requestId = useMemo(newRequestId, []);
  const { busy, error, run } = useAction();

  const drafts: PaymentDraft[] = payments.map((payment) => {
    const method = methods.find((m) => m.code === payment.method)!;
    return { method: method.code, kind: method.kind, amount: toCents(payment.text || "0") };
  });
  const status = paymentStatus(props.total, drafts, customer !== null);
  const needsCustomer = drafts.some((draft) => draft.kind === "credit");
  const canConfirm = status.missing === 0 && status.problem === null && !busy;

  function setPayment(index: number, change: Partial<{ method: string; text: string }>) {
    setPayments((current) => current.map((p, i) => (i === index ? { ...p, ...change } : p)));
  }

  async function confirm() {
    if (!canConfirm) return;
    const sale = await run(() =>
      api.post<Sale>(
        "/sales",
        {
          items: props.lines.map((line) => ({
            product_id: line.product.id,
            quantity: thousandthsToApi(line.quantity),
            ...(line.discount > 0 ? { discount: centsToApi(line.discount) } : {}),
          })),
          payments: drafts.map((draft) => ({ method: draft.method, amount: centsToApi(draft.amount) })),
          ...(customer ? { customer_id: customer.id } : {}),
        },
        { "Idempotency-Key": requestId },
      ),
    );
    if (sale) props.onDone(sale, customer);
  }

  const single = payments.length === 1;
  const singleKind = drafts[0]?.kind;

  return (
    <Modal title={`Cobrar ${formatMoney(props.total)}`} onClose={props.onClose}>
      <form
        onSubmit={(event) => {
          event.preventDefault();
          void confirm();
        }}
      >
        {single && (
          <div className="pay-methods" role="radiogroup" aria-label="Método de pago">
            {methods.map((method) => (
              <button
                type="button"
                key={method.code}
                className={`btn pay-method ${payments[0].method === method.code ? "active" : ""}`}
                aria-pressed={payments[0].method === method.code}
                onClick={() =>
                  setPayment(0, {
                    method: method.code,
                    text: method.kind === "cash" ? payments[0].text : centsToApi(props.total),
                  })
                }
              >
                {method.name}
              </button>
            ))}
          </div>
        )}

        {payments.map((payment, index) => (
          <div className="row" key={index} style={{ marginBottom: 8 }}>
            {!single && (
              <select
                className="input"
                style={{ maxWidth: 180 }}
                value={payment.method}
                onChange={(e) => setPayment(index, { method: e.target.value })}
                aria-label="Método de pago"
              >
                {methods.map((method) => (
                  <option key={method.code} value={method.code}>
                    {method.name}
                  </option>
                ))}
              </select>
            )}
            <input
              className="input input-big"
              style={{ flex: 1 }}
              inputMode="decimal"
              placeholder={single ? "¿Con cuánto paga?" : "Monto"}
              value={payment.text}
              onChange={(e) => setPayment(index, { text: e.target.value })}
              autoFocus={index === payments.length - 1}
              aria-label="Monto recibido"
            />
            {!single && (
              <button
                type="button"
                className="btn btn-sm btn-danger"
                onClick={() => setPayments((current) => current.filter((_, i) => i !== index))}
              >
                Quitar
              </button>
            )}
          </div>
        ))}

        {single && singleKind === "cash" && (
          <div className="quick-amounts">
            {quickCashAmounts(props.total).map((amount, index) => (
              <button type="button" key={amount} className="btn btn-sm" onClick={() => setPayment(0, { text: centsToApi(amount) })}>
                {index === 0 ? "Exacto" : formatMoney(amount)}
              </button>
            ))}
          </div>
        )}

        <button
          type="button"
          className="btn-link small"
          onClick={() =>
            setPayments((current) => [
              ...current,
              { method: methods.find((m) => !current.some((p) => p.method === m.code))?.code ?? firstCash.code, text: status.missing ? centsToApi(status.missing) : "" },
            ])
          }
        >
          + Pagar con otro método (pago mixto)
        </button>

        {needsCustomer && (
          <div style={{ marginTop: 12 }}>
            <strong className="small">Cliente al que se le fía</strong>
            <CustomerPicker value={customer} onChange={setCustomer} />
          </div>
        )}

        <div className="card" style={{ marginTop: 16, background: "var(--surface-2)" }}>
          <div className="total-line">
            <span>Total</span>
            <strong>{formatMoney(props.total)}</strong>
          </div>
          <div className="total-line">
            <span>Recibido</span>
            <span>{formatMoney(status.paid)}</span>
          </div>
          {status.missing > 0 ? (
            <div className="total-line" style={{ color: "var(--danger)" }}>
              <span>Falta</span>
              <strong className="change">{formatMoney(status.missing)}</strong>
            </div>
          ) : (
            <div className="total-line">
              <span>Vueltas</span>
              <strong className="change">{formatMoney(status.change)}</strong>
            </div>
          )}
        </div>

        {status.problem && status.missing === 0 && <div className="alert alert-warn" style={{ marginTop: 12 }}>{status.problem}</div>}
        <ErrorAlert error={error} />

        <div className="modal-actions">
          <button type="button" className="btn" onClick={props.onClose}>
            Volver
          </button>
          <button className="btn btn-primary btn-big" disabled={!canConfirm}>
            {busy ? "Registrando…" : "Confirmar venta"}
          </button>
        </div>
      </form>
    </Modal>
  );
}
