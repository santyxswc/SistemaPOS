import { useEffect, useState } from "react";
import { api } from "../api";
import { formatMoney } from "../money";
import type { Customer, Items } from "../types";

/** Busca un cliente por nombre, documento o teléfono. */
export function CustomerPicker(props: { value: Customer | null; onChange: (customer: Customer | null) => void }) {
  const [text, setText] = useState("");
  const [results, setResults] = useState<Customer[]>([]);

  useEffect(() => {
    if (text.trim().length < 2) {
      setResults([]);
      return;
    }
    const timer = window.setTimeout(() => {
      api
        .get<Items<Customer>>("/customers", { q: text, limit: 8 })
        .then((data) => setResults(data.items))
        .catch(() => setResults([]));
    }, 250);
    return () => window.clearTimeout(timer);
  }, [text]);

  if (props.value) {
    const customer = props.value;
    return (
      <div className="alert alert-info row">
        <div>
          <strong>{customer.name}</strong>
          <div className="small">
            Debe {formatMoney(customer.balance)} · Cupo disponible {formatMoney(customer.available_credit)}
          </div>
        </div>
        <span className="spacer" />
        <button type="button" className="btn btn-sm" onClick={() => props.onChange(null)}>
          Cambiar
        </button>
      </div>
    );
  }

  return (
    <div>
      <input
        className="input"
        placeholder="Buscar cliente por nombre, cédula o teléfono"
        value={text}
        onChange={(e) => setText(e.target.value)}
      />
      {results.length > 0 && (
        <div className="search-results">
          {results.map((customer) => (
            <button
              type="button"
              key={customer.id}
              className="search-result"
              onClick={() => {
                props.onChange(customer);
                setText("");
              }}
            >
              <span>
                {customer.name} <span className="muted small">{customer.document}</span>
              </span>
              <span className="small muted">Cupo {formatMoney(customer.available_credit)}</span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
