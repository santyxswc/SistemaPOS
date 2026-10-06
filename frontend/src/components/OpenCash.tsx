import { type FormEvent, useState } from "react";
import { api } from "../api";
import { centsToApi, toCents } from "../money";
import { ErrorAlert, Field, useAction } from "./ui";

/** Apertura de caja con la base (efectivo inicial del cajón). */
export function OpenCash({ onOpened }: { onOpened: () => void }) {
  const [amount, setAmount] = useState("");
  const { busy, error, run } = useAction();

  async function submit(event: FormEvent) {
    event.preventDefault();
    const done = await run(() => api.post("/cash-sessions", { opening_amount: centsToApi(toCents(amount || "0")) }));
    if (done !== undefined) onOpened();
  }

  return (
    <form className="card" style={{ maxWidth: 420 }} onSubmit={submit}>
      <h2>Abrir caja</h2>
      <p className="muted">Antes de vender, cuente el efectivo con que empieza el turno.</p>
      <ErrorAlert error={error} />
      <Field label="Base en efectivo">
        <input
          className="input input-big"
          inputMode="decimal"
          placeholder="0"
          value={amount}
          onChange={(e) => setAmount(e.target.value)}
          autoFocus
        />
      </Field>
      <button className="btn btn-primary btn-big" disabled={busy}>
        Abrir caja
      </button>
    </form>
  );
}
