// Licencia de uso: aviso para el administrador y activación del código enviado por el proveedor.

import { type FormEvent, useEffect, useState } from "react";
import { api } from "../api";
import type { LicenseStatus } from "../types";
import { ErrorAlert, Field, toast, useAction, useLoad } from "./ui";

const STATE_LABEL: Record<LicenseStatus["state"], string> = {
  trial: "Periodo de prueba",
  active: "Activa",
  trial_expired: "Prueba terminada",
  expired: "Vencida",
};

// El aviso y la tarjeta de Ajustes cargan la licencia por separado; este evento los mantiene de acuerdo.
const LICENSE_CHANGED = "pos:license-changed";

function formatDate(iso: string | null): string {
  if (!iso) return "No vence";
  const [year, month, day] = iso.split("-");
  return `${day}/${month}/${year}`;
}

/** Franja superior que solo aparece cuando la licencia está por vencer o vencida. */
export function LicenseBanner({ onOpenSettings }: { onOpenSettings: () => void }) {
  const { data, reload } = useLoad(() => api.get<LicenseStatus>("/license"), []);
  useEffect(() => {
    const onChange = () => void reload();
    window.addEventListener(LICENSE_CHANGED, onChange);
    return () => window.removeEventListener(LICENSE_CHANGED, onChange);
  }, [reload]);
  if (!data?.needs_attention) return null;
  return (
    <div className={`alert ${data.valid ? "alert-warn" : "alert-error"} license-banner`} role="status">
      <span>{data.message}</span>
      <button className="btn btn-sm" onClick={onOpenSettings}>
        Activar licencia
      </button>
    </div>
  );
}

export function LicenseCard() {
  const status = useLoad(() => api.get<LicenseStatus>("/license"), []);
  const [code, setCode] = useState("");
  const { busy, error, run } = useAction();
  const data = status.data;

  async function submit(event: FormEvent) {
    event.preventDefault();
    const result = await run(() => api.post<LicenseStatus>("/license", { code }));
    if (result) {
      status.setData(result);
      setCode("");
      window.dispatchEvent(new Event(LICENSE_CHANGED));
      toast("Licencia activada");
    }
  }

  return (
    <section className="card" style={{ marginTop: 16 }} aria-labelledby="license-title">
      <h2 id="license-title">Licencia</h2>
      <ErrorAlert error={status.error} />
      {data && (
        <div className="license-summary">
          <div>
            <span className={`badge ${data.valid ? "badge-ok" : "badge-danger"}`}>{STATE_LABEL[data.state]}</span>{" "}
            {data.message}
          </div>
          <dl className="details">
            {data.license && (
              <>
                <dt>Negocio</dt>
                <dd>{data.license.business_name}</dd>
                <dt>Plan</dt>
                <dd>{data.license.plan}</dd>
              </>
            )}
            <dt>Usuarios activos permitidos</dt>
            <dd>{data.max_users ?? "Sin límite"}</dd>
            <dt>{data.state === "trial" || data.state === "trial_expired" ? "Fin de la prueba" : "Vence"}</dt>
            <dd>{formatDate(data.expires_on)}</dd>
          </dl>
        </div>
      )}
      <form onSubmit={submit}>
        <Field label="Código de licencia" hint="Péguelo completo, tal como se lo envió su proveedor (empieza por POS1).">
          <textarea
            className="input"
            rows={3}
            value={code}
            onChange={(e) => setCode(e.target.value)}
            spellCheck={false}
            required
          />
        </Field>
        <ErrorAlert error={error} />
        <button className="btn btn-primary" disabled={busy || !code.trim()}>
          Activar licencia
        </button>
      </form>
    </section>
  );
}
