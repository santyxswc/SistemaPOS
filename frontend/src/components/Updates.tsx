// Aviso de versión nueva para el administrador (se puede ocultar hasta la siguiente versión).

import { useState } from "react";
import { api } from "../api";
import type { UpdateStatus } from "../types";
import { useLoad } from "./ui";

const DISMISSED_KEY = "pos.update-dismissed";

function readDismissed(): string | null {
  try {
    return localStorage.getItem(DISMISSED_KEY);
  } catch {
    return null;
  }
}

export function UpdateBanner() {
  const { data } = useLoad(() => api.get<UpdateStatus>("/updates"), []);
  const [dismissed, setDismissed] = useState(readDismissed);
  const latest = data?.latest;
  if (!data?.available || !latest || dismissed === latest.version) return null;

  function dismiss() {
    try {
      localStorage.setItem(DISMISSED_KEY, latest!.version);
    } catch {
      // sin almacenamiento: el aviso vuelve a salir la próxima vez
    }
    setDismissed(latest!.version);
  }

  return (
    <div className="alert alert-info license-banner" role="status">
      <span>
        Hay una versión nueva del punto de venta: <strong>{latest.version}</strong> (usted tiene {data.current}).
        Instálela cuando cierre el día; sus datos se conservan.
      </span>
      <span className="row">
        <a className="btn btn-sm" href={latest.download_url ?? latest.url} target="_blank" rel="noreferrer">
          {latest.download_url ? "Descargar" : "Ver novedades"}
        </a>
        <button className="btn btn-sm" onClick={dismiss}>
          Ahora no
        </button>
      </span>
    </div>
  );
}
