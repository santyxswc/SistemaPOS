// Importar productos desde Excel o CSV: primero una revisión sin guardar nada, luego la importación.

import { type FormEvent, useState } from "react";
import { api } from "../api";
import { ErrorAlert, Modal, useAction } from "./ui";

interface ImportReport {
  dry_run: boolean;
  total_rows: number;
  created: number;
  updated: number;
  unchanged: number;
  skipped_existing: number;
  new_categories: string[];
  errors: { line: number; message: string }[];
}

const MAX_ERRORS_SHOWN = 100;

function plural(count: number, singular: string, pluralForm: string): string {
  return `${count.toLocaleString("es-CO")} ${count === 1 ? singular : pluralForm}`;
}

export function ImportProductsDialog(props: { onClose: () => void; onImported: (report: ImportReport) => void }) {
  const [file, setFile] = useState<File | null>(null);
  const [updateExisting, setUpdateExisting] = useState(false);
  const [preview, setPreview] = useState<ImportReport | null>(null);
  const { busy, error, run } = useAction();
  const template = useAction();

  const upload = (dryRun: boolean) =>
    api.upload<ImportReport>("/products/import", file!, { dry_run: dryRun, update_existing: updateExisting });

  async function review(event: FormEvent) {
    event.preventDefault();
    const report = await run(() => upload(true));
    if (report) setPreview(report);
  }

  async function confirm() {
    const report = await run(() => upload(false));
    if (report) props.onImported(report);
  }

  const toSave = preview ? preview.created + preview.updated : 0;

  return (
    <Modal title="Importar productos" onClose={props.onClose} wide>
      {!preview ? (
        <form onSubmit={review}>
          <p>
            Cargue su lista de productos desde un archivo de <strong>Excel (.xlsx)</strong> o <strong>CSV</strong>. La
            primera fila debe tener los encabezados: Código, Nombre, Precio, Costo, IVA %, Código de barras, Categoría,
            Unidad, Existencias y Stock mínimo. Solo Nombre y Precio son obligatorios; si no tiene código, se usa el
            código de barras.
          </p>
          <p>
            <button
              type="button"
              className="btn btn-sm"
              disabled={template.busy}
              onClick={() => template.run(() => api.download("/products/import-template", undefined, "plantilla-productos.xlsx"))}
            >
              Descargar plantilla de ejemplo
            </button>
          </p>
          <ErrorAlert error={template.error} />
          <label className="field">
            <span>Archivo</span>
            <input
              className="input"
              type="file"
              accept=".xlsx,.csv,.txt"
              onChange={(e) => setFile(e.target.files?.[0] ?? null)}
            />
          </label>
          <label className="check">
            <input type="checkbox" checked={updateExisting} onChange={(e) => setUpdateExisting(e.target.checked)} />
            Actualizar los productos que ya existen (precio, costo, nombre…). Las existencias de esos productos no se
            tocan: para corregirlas use el ajuste de inventario.
          </label>
          <ErrorAlert error={error} />
          <div className="modal-actions">
            <button type="button" className="btn" onClick={props.onClose}>
              Cancelar
            </button>
            <button className="btn btn-primary" disabled={busy || !file}>
              {busy ? "Revisando…" : "Revisar archivo"}
            </button>
          </div>
        </form>
      ) : (
        <>
          <p className="muted">Revisión de «{file?.name}». Todavía no se ha guardado nada.</p>
          <ul className="import-summary">
            <li>
              <strong>{plural(preview.created, "producto nuevo", "productos nuevos")}</strong>
            </li>
            {updateExisting && <li>{plural(preview.updated, "producto se actualizará", "productos se actualizarán")}</li>}
            {preview.unchanged > 0 && <li>{plural(preview.unchanged, "producto sin cambios", "productos sin cambios")}</li>}
            {preview.skipped_existing > 0 && (
              <li>{plural(preview.skipped_existing, "producto ya existe y se omitirá", "productos ya existen y se omitirán")}</li>
            )}
            {preview.new_categories.length > 0 && <li>Categorías nuevas: {preview.new_categories.join(", ")}</li>}
            {preview.errors.length > 0 && (
              <li className="text-danger">{plural(preview.errors.length, "fila con errores", "filas con errores")} (no se importarán)</li>
            )}
          </ul>
          {preview.errors.length > 0 && (
            <div className="table-wrap import-errors">
              <table>
                <thead>
                  <tr>
                    <th className="num">Fila</th>
                    <th>Problema</th>
                  </tr>
                </thead>
                <tbody>
                  {preview.errors.slice(0, MAX_ERRORS_SHOWN).map((issue) => (
                    <tr key={issue.line}>
                      <td className="num">{issue.line}</td>
                      <td>{issue.message}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {preview.errors.length > MAX_ERRORS_SHOWN && (
                <p className="muted small">Y {preview.errors.length - MAX_ERRORS_SHOWN} más. Corrija el archivo y revíselo de nuevo.</p>
              )}
            </div>
          )}
          <ErrorAlert error={error} />
          <div className="modal-actions">
            <button type="button" className="btn" onClick={() => setPreview(null)}>
              Elegir otro archivo
            </button>
            <button className="btn btn-primary" onClick={confirm} disabled={busy || toSave === 0}>
              {busy ? "Importando…" : `Importar ${plural(toSave, "producto", "productos")}`}
            </button>
          </div>
        </>
      )}
    </Modal>
  );
}
