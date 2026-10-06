// Usuarios: crear cajeros y administradores, desactivarlos y restablecer contraseñas.

import { type FormEvent, useState } from "react";
import { api } from "../api";
import { RolePermissionsCard } from "../components/RolePermissions";
import { Empty, ErrorAlert, Field, Modal, formatDateTime, toUsername, toast, useAction, useLoad } from "../components/ui";
import { useSession } from "../session";
import { type Items, type LicenseStatus, ROLE_LABEL, type Role, type User } from "../types";

export function UsersPage() {
  const { me } = useSession();
  const users = useLoad(() => api.get<Items<User>>("/users"), []);
  const license = useLoad(() => api.get<LicenseStatus>("/license"), []);
  const maxUsers = license.data?.max_users ?? null;
  const [editing, setEditing] = useState<User | null | "new">(null);
  const active = users.data?.items.filter((user) => user.active).length ?? 0;

  return (
    <>
      <div className="page-header">
        <h1>Usuarios</h1>
        <button className="btn btn-primary" onClick={() => setEditing("new")}>
          Nuevo usuario
        </button>
      </div>
      {maxUsers !== null && (
        <p className="muted">
          Su licencia permite {maxUsers} usuario{maxUsers === 1 ? "" : "s"} activo{maxUsers === 1 ? "" : "s"}; hay {active}.
        </p>
      )}
      <ErrorAlert error={users.error} />
      <section className="card table-wrap">
        {!users.data?.items.length ? (
          <Empty>Cargando…</Empty>
        ) : (
          <table>
            <thead>
              <tr>
                <th>Usuario</th>
                <th>Rol</th>
                <th>Estado</th>
                <th>Creado</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {users.data.items.map((user) => (
                <tr key={user.id}>
                  <td>
                    <strong>{user.full_name}</strong>
                    <div className="muted small">{user.username}</div>
                  </td>
                  <td>{ROLE_LABEL[user.role]}</td>
                  <td>
                    <span className={`badge ${user.active ? "badge-ok" : ""}`}>{user.active ? "Activo" : "Inactivo"}</span>
                  </td>
                  <td>{formatDateTime(user.created_at)}</td>
                  <td className="right">
                    <button className="btn btn-sm" onClick={() => setEditing(user)}>
                      Editar
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
      <RolePermissionsCard />
      {editing && (
        <UserForm
          user={editing === "new" ? null : editing}
          isSelf={editing !== "new" && editing.id === me.id}
          onClose={() => setEditing(null)}
          onSaved={() => {
            toast(editing === "new" ? "Usuario creado" : "Usuario actualizado");
            setEditing(null);
            void users.reload();
          }}
        />
      )}
    </>
  );
}

function UserForm(props: { user: User | null; isSelf: boolean; onClose: () => void; onSaved: () => void }) {
  const editing = props.user;
  const [form, setForm] = useState({
    username: editing?.username ?? "",
    full_name: editing?.full_name ?? "",
    role: editing?.role ?? ("cashier" as Role),
    active: editing?.active ?? true,
    password: "",
  });
  const { busy, error, run } = useAction();
  const set = (change: Partial<typeof form>) => setForm((current) => ({ ...current, ...change }));

  async function submit(event: FormEvent) {
    event.preventDefault();
    const done = await run(() =>
      editing
        ? api.patch(`/users/${editing.id}`, {
            full_name: form.full_name,
            ...(props.isSelf ? {} : { role: form.role, active: form.active }),
            ...(form.password ? { password: form.password } : {}),
          })
        : api.post("/users", {
            username: form.username,
            full_name: form.full_name,
            role: form.role,
            password: form.password,
          }),
    );
    if (done !== undefined) props.onSaved();
  }

  return (
    <Modal title={editing ? `Editar ${editing.username}` : "Nuevo usuario"} onClose={props.onClose}>
      <form onSubmit={submit}>
        <ErrorAlert error={error} />
        {!editing && (
          <Field label="Usuario para entrar" hint="Minúsculas, números, punto o guion; de 3 a 32 caracteres">
            <input className="input" value={form.username} onChange={(e) => set({ username: toUsername(e.target.value) })} autoFocus required />
          </Field>
        )}
        <Field label="Nombre completo">
          <input className="input" value={form.full_name} onChange={(e) => set({ full_name: e.target.value })} required />
        </Field>
        {!props.isSelf && (
          <Field label="Rol">
            <select className="input" value={form.role} onChange={(e) => set({ role: e.target.value as Role })}>
              <option value="cashier">Cajero: vende, opera su caja y atiende clientes</option>
              <option value="supervisor">Supervisor: además anula ventas, da descuentos, ve reportes y cierra cajas</option>
              <option value="admin">Administrador: acceso completo</option>
            </select>
          </Field>
        )}
        <Field label={editing ? "Nueva contraseña (opcional)" : "Contraseña"} hint="Mínimo 8 caracteres">
          <input
            className="input"
            type="password"
            autoComplete="new-password"
            value={form.password}
            onChange={(e) => set({ password: e.target.value })}
            required={!editing}
            minLength={8}
          />
        </Field>
        {editing && !props.isSelf && (
          <label className="check">
            <input type="checkbox" checked={form.active} onChange={(e) => set({ active: e.target.checked })} /> Activo
            (puede entrar al sistema)
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

export function ChangePasswordModal({ onClose }: { onClose: () => void }) {
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [repeat, setRepeat] = useState("");
  const { busy, error, setError, run } = useAction();

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (next !== repeat) {
      setError("Las contraseñas nuevas no coinciden");
      return;
    }
    const done = await run(() =>
      api.post("/auth/change-password", { current_password: current, new_password: next }),
    );
    if (done === undefined) return;
    toast("Contraseña actualizada");
    onClose();
  }

  return (
    <Modal title="Cambiar mi contraseña" onClose={onClose}>
      <form onSubmit={submit}>
        <ErrorAlert error={error} />
        <Field label="Contraseña actual">
          <input className="input" type="password" autoComplete="current-password" value={current} onChange={(e) => setCurrent(e.target.value)} autoFocus required />
        </Field>
        <Field label="Contraseña nueva" hint="Mínimo 8 caracteres">
          <input className="input" type="password" autoComplete="new-password" value={next} onChange={(e) => setNext(e.target.value)} minLength={8} required />
        </Field>
        <Field label="Repita la contraseña nueva">
          <input className="input" type="password" autoComplete="new-password" value={repeat} onChange={(e) => setRepeat(e.target.value)} required />
        </Field>
        <div className="modal-actions">
          <button className="btn btn-primary" disabled={busy}>
            Cambiar
          </button>
        </div>
      </form>
    </Modal>
  );
}
