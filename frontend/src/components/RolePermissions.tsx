// Permisos por rol: qué puede hacer el supervisor y el cajero en este negocio.

import { useEffect, useState } from "react";
import { api } from "../api";
import { ErrorAlert, toast, useAction, useLoad } from "./ui";
import type { Permission, Role } from "../types";

interface RoleInfo {
  role: Role;
  label: string;
  editable: boolean;
  customized: boolean;
  permissions: Permission[];
  default_permissions: Permission[];
}

export interface RolesData {
  roles: RoleInfo[];
  permissions: { code: Permission; label: string; grantable: boolean }[];
}

const capitalize = (text: string) => text.charAt(0).toUpperCase() + text.slice(1);

export function RolePermissionsCard() {
  const data = useLoad(() => api.get<RolesData>("/roles"), []);
  const [draft, setDraft] = useState<Partial<Record<Role, Set<Permission>>>>({});
  const { busy, error, run } = useAction();

  useEffect(() => {
    if (!data.data) return;
    setDraft(Object.fromEntries(data.data.roles.map((r) => [r.role, new Set(r.permissions)])));
  }, [data.data]);

  if (!data.data) return <ErrorAlert error={data.error} />;
  const editable = data.data.roles.filter((r) => r.editable);
  const grantable = data.data.permissions.filter((p) => p.grantable);

  const toggle = (role: Role, permission: Permission) =>
    setDraft((current) => {
      const next = new Set(current[role]);
      if (next.has(permission)) next.delete(permission);
      else next.add(permission);
      return { ...current, [role]: next };
    });

  const changed = (info: RoleInfo) => {
    const selected = draft[info.role];
    if (!selected) return false; // el borrador todavía no se ha cargado
    return selected.size !== info.permissions.length || info.permissions.some((p) => !selected.has(p));
  };

  async function save(info: RoleInfo, reset = false) {
    const body = reset ? { reset: true } : { permissions: [...(draft[info.role] ?? [])] };
    const result = await run(() => api.put<RolesData>(`/roles/${info.role}`, body));
    if (result) {
      data.setData(result);
      toast(reset ? `${info.label}: permisos de fábrica restaurados` : `Permisos de ${info.label} guardados`);
    }
  }

  return (
    <section className="card" style={{ marginTop: 16 }} aria-labelledby="roles-title">
      <h2 id="roles-title">Permisos por rol</h2>
      <p className="muted small">
        El administrador siempre puede hacerlo todo. Los cambios aplican a cada usuario en su siguiente acción, sin
        cerrar sesión.
      </p>
      <ErrorAlert error={error} />
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Permiso</th>
              {editable.map((info) => (
                <th key={info.role} className="center">
                  {info.label}
                  {info.customized && <div className="muted small">personalizado</div>}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {grantable.map((permission) => (
              <tr key={permission.code}>
                <td>{capitalize(permission.label)}</td>
                {editable.map((info) => (
                  <td key={info.role} className="center">
                    <input
                      type="checkbox"
                      checked={draft[info.role]?.has(permission.code) ?? false}
                      onChange={() => toggle(info.role, permission.code)}
                      aria-label={`${info.label}: ${permission.label}`}
                    />
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
          <tfoot>
            <tr>
              <td />
              {editable.map((info) => (
                <td key={info.role} className="center">
                  <div className="row" style={{ justifyContent: "center" }}>
                    <button className="btn btn-sm btn-primary" disabled={busy || !changed(info)} onClick={() => save(info)}>
                      Guardar
                    </button>
                    {info.customized && (
                      <button className="btn btn-sm" disabled={busy} onClick={() => save(info, true)}>
                        De fábrica
                      </button>
                    )}
                  </div>
                </td>
              ))}
            </tr>
          </tfoot>
        </table>
      </div>
    </section>
  );
}
