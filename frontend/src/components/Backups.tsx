// Respaldos: carpeta adicional (USB, OneDrive), respaldar ahora y los últimos respaldos.

import { type FormEvent, useState } from "react";
import { api } from "../api";
import { useSession } from "../session";
import type { BackupFile, BackupResult, Items, Settings } from "../types";
import { Empty, ErrorAlert, formatDateTime, toast, useAction, useLoad } from "./ui";

function formatSize(bytes: number): string {
  if (bytes < 1024 * 1024) return `${Math.max(1, Math.round(bytes / 1024))} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1).replace(".", ",")} MB`;
}

export function BackupsCard() {
  const { settings, reloadSettings } = useSession();
  const backups = useLoad(() => api.get<Items<BackupFile>>("/backups"), []);
  const [folder, setFolder] = useState(settings.backup_folder);
  const [warning, setWarning] = useState<string | null>(null);
  const save = useAction();
  const backup = useAction();

  async function saveFolder(event: FormEvent) {
    event.preventDefault();
    const done = await save.run(async () => {
      await api.patch<Settings>("/settings", { backup_folder: folder });
      await reloadSettings();
      return true;
    });
    if (done) toast(folder.trim() ? "Carpeta de respaldo guardada" : "Copia adicional desactivada");
  }

  async function backupNow() {
    setWarning(null);
    const result = await backup.run(() => api.post<BackupResult>("/backups"));
    if (!result) return;
    setWarning(result.extra_error);
    toast(result.extra_copy ? "Respaldo creado y copiado a la carpeta adicional" : "Respaldo creado");
    await backups.reload();
  }

  return (
    <section className="card" style={{ marginTop: 16 }} aria-labelledby="backups-title">
      <div className="page-header" style={{ marginBottom: 8 }}>
        <h2 id="backups-title" style={{ margin: 0 }}>
          Respaldos
        </h2>
        <button className="btn" type="button" onClick={backupNow} disabled={backup.busy}>
          {backup.busy ? "Respaldando…" : "Respaldar ahora"}
        </button>
      </div>
      <p className="muted small">
        El sistema se respalda solo al cerrar cada caja y todas las noches. Si el computador se daña o se pierde, los
        respaldos guardados en el mismo disco se pierden con él: elija también una USB o una carpeta de OneDrive o
        Google Drive.
      </p>
      <ErrorAlert error={backup.error} />
      {warning && <div className="alert alert-warn">{warning}</div>}
      <form onSubmit={saveFolder} className="field">
        <label htmlFor="backup-folder">Carpeta adicional</label>
        <div className="row">
          <input
            id="backup-folder"
            className="input"
            style={{ flex: 1, minWidth: 220 }}
            value={folder}
            onChange={(e) => setFolder(e.target.value)}
            spellCheck={false}
          />
          <button className="btn" disabled={save.busy || folder === settings.backup_folder}>
            Guardar carpeta
          </button>
        </div>
        <small className="muted">Ruta completa, por ejemplo E:\ o C:\Users\Tienda\OneDrive. Déjela vacía para no copiar.</small>
      </form>
      <ErrorAlert error={save.error ?? backups.error} />
      <h3>Últimos respaldos en este equipo</h3>
      {!backups.data?.items.length ? (
        <Empty>{backups.loading ? "Cargando…" : "Todavía no hay respaldos."}</Empty>
      ) : (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Fecha</th>
                <th>Archivo</th>
                <th className="num">Tamaño</th>
              </tr>
            </thead>
            <tbody>
              {backups.data.items.map((item) => (
                <tr key={item.name}>
                  <td>{formatDateTime(item.created_at)}</td>
                  <td className="small">{item.name}</td>
                  <td className="num">{formatSize(item.size_bytes)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
