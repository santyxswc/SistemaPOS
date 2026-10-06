// Primera vez que se abre el sistema: datos del negocio y cuenta del administrador.

import { type FormEvent, useState } from "react";
import { api } from "../api";
import { ErrorAlert, Field, toUsername, useAction } from "../components/ui";

export function SetupPage({ onDone }: { onDone: (token: string) => void }) {
  const [form, setForm] = useState({ business_name: "", full_name: "", username: "", password: "", repeat: "" });
  const { busy, error, setError, run } = useAction();
  const set = (change: Partial<typeof form>) => setForm((current) => ({ ...current, ...change }));

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (form.password !== form.repeat) {
      setError("Las contraseñas no coinciden");
      return;
    }
    const { repeat: _repeat, ...body } = form;
    const result = await run(() => api.post<{ access_token: string }>("/setup", body));
    if (result) onDone(result.access_token);
  }

  return (
    <div className="login">
      <form className="card" style={{ maxWidth: 460 }} onSubmit={submit}>
        <h1>Bienvenido</h1>
        <p className="muted">Configuremos su punto de venta. Solo toma un minuto y se hace una vez.</p>
        <ErrorAlert error={error} />
        <Field label="Nombre del negocio" hint="Aparece en el tiquete; puede cambiarlo después en Ajustes">
          <input className="input" value={form.business_name} onChange={(e) => set({ business_name: e.target.value })} autoFocus required />
        </Field>
        <h2 style={{ marginTop: 20 }}>Su cuenta de administrador</h2>
        <Field label="Su nombre">
          <input className="input" value={form.full_name} onChange={(e) => set({ full_name: e.target.value })} required />
        </Field>
        <Field label="Usuario para entrar" hint="Minúsculas y números, por ejemplo: admin">
          <input
            className="input"
            value={form.username}
            onChange={(e) => set({ username: toUsername(e.target.value) })}
            autoComplete="username"
            required
          />
        </Field>
        <Field label="Contraseña" hint="Mínimo 8 caracteres. Guárdela en un lugar seguro">
          <input className="input" type="password" value={form.password} onChange={(e) => set({ password: e.target.value })} autoComplete="new-password" minLength={8} required />
        </Field>
        <Field label="Repita la contraseña">
          <input className="input" type="password" value={form.repeat} onChange={(e) => set({ repeat: e.target.value })} autoComplete="new-password" required />
        </Field>
        <button className="btn btn-primary btn-big" style={{ width: "100%" }} disabled={busy}>
          {busy ? "Preparando…" : "Empezar a vender"}
        </button>
      </form>
    </div>
  );
}
