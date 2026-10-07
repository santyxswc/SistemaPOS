import { type FormEvent, useEffect, useState } from "react";
import { api } from "../api";
import { BrandMark } from "../components/Branding";
import { ErrorAlert, Field, useAction } from "../components/ui";
import type { Branding } from "../types";

export function LoginPage({ onLogin }: { onLogin: (token: string) => void }) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const { busy, error, run } = useAction();
  const [branding, setBranding] = useState<Branding | null>(null);

  useEffect(() => {
    api
      .get<Branding>("/branding")
      .then(setBranding)
      .catch(() => setBranding(null)); // sin marca se ve el título genérico
  }, []);

  async function submit(event: FormEvent) {
    event.preventDefault();
    const result = await run(() => api.post<{ access_token: string }>("/auth/login", { username, password }));
    if (result) onLogin(result.access_token);
  }

  return (
    <div className="login">
      <form className="card" onSubmit={submit}>
        {branding ? <BrandMark branding={branding} className="login-brand" /> : <h1>Punto de venta</h1>}
        <p className="muted">Ingrese con su usuario y contraseña.</p>
        <ErrorAlert error={error} />
        <Field label="Usuario">
          <input
            className="input input-big"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            autoFocus
            autoComplete="username"
            required
          />
        </Field>
        <Field label="Contraseña">
          <input
            className="input input-big"
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoComplete="current-password"
            required
          />
        </Field>
        <button className="btn btn-primary btn-big" style={{ width: "100%" }} disabled={busy}>
          {busy ? "Entrando…" : "Entrar"}
        </button>
      </form>
    </div>
  );
}
