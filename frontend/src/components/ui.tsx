// Piezas de interfaz reutilizables.

import { type ReactNode, useCallback, useEffect, useRef, useState } from "react";
import { errorMessage } from "../api";

export function Modal(props: {
  title: string;
  onClose: () => void;
  children: ReactNode;
  wide?: boolean;
}) {
  const { onClose } = props;
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <div className="modal-backdrop" onMouseDown={(event) => event.target === event.currentTarget && onClose()}>
      <div className={`modal ${props.wide ? "modal-wide" : ""}`} role="dialog" aria-modal="true" aria-label={props.title}>
        <div className="modal-header">
          <h2>{props.title}</h2>
          <button className="btn btn-sm" onClick={onClose} aria-label="Cerrar">
            ✕
          </button>
        </div>
        {props.children}
      </div>
    </div>
  );
}

/** Pregunta de sí o no con el estilo del sistema (en lugar del cuadro gris del navegador). */
export function ConfirmDialog(props: {
  title: string;
  message: ReactNode;
  confirmLabel: string;
  danger?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  return (
    <Modal title={props.title} onClose={props.onCancel}>
      <p>{props.message}</p>
      <div className="modal-actions">
        <button type="button" className="btn" onClick={props.onCancel}>
          No, volver
        </button>
        <button
          type="button"
          className={`btn ${props.danger ? "btn-danger-solid" : "btn-primary"}`}
          onClick={props.onConfirm}
          autoFocus
        >
          {props.confirmLabel}
        </button>
      </div>
    </Modal>
  );
}

export function Field(props: { label: string; children: ReactNode; hint?: string }) {
  return (
    <label className="field">
      <span>{props.label}</span>
      {props.children}
      {props.hint && <small className="muted">{props.hint}</small>}
    </label>
  );
}

export function ErrorAlert({ error }: { error: string | null }) {
  if (!error) return null;
  return (
    <div className="alert alert-error" role="alert">
      {error}
    </div>
  );
}

export function Empty({ children }: { children: ReactNode }) {
  return <div className="empty">{children}</div>;
}

export function Stat({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className="stat">
      <div className="stat-label">{label}</div>
      <div className="stat-value">{value}</div>
    </div>
  );
}

/** Carga datos y expone cargando, error y una función para recargar. */
export function useLoad<T>(loader: () => Promise<T>, deps: unknown[]) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const latest = useRef(0);

  const reload = useCallback(async () => {
    const call = ++latest.current;
    setLoading(true);
    try {
      const result = await loader();
      if (call === latest.current) {
        setData(result);
        setError(null);
      }
    } catch (err) {
      if (call === latest.current) setError(errorMessage(err));
    } finally {
      if (call === latest.current) setLoading(false);
    }
  }, deps);

  useEffect(() => {
    void reload();
  }, [reload]);

  return { data, error, loading, reload, setData };
}

/** Ejecuta una acción mostrando su error y evitando doble clic mientras corre. */
export function useAction() {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const run = useCallback(async <T,>(action: () => Promise<T>): Promise<T | undefined> => {
    setBusy(true);
    setError(null);
    try {
      return await action();
    } catch (err) {
      setError(errorMessage(err));
      return undefined;
    } finally {
      setBusy(false);
    }
  }, []);
  return { busy, error, setError, run };
}

let showToast: (message: string) => void = () => {};

export function toast(message: string): void {
  showToast(message);
}

export function Toaster() {
  const [message, setMessage] = useState<string | null>(null);
  useEffect(() => {
    let timer: number | undefined;
    showToast = (text) => {
      setMessage(text);
      window.clearTimeout(timer);
      timer = window.setTimeout(() => setMessage(null), 3500);
    };
    return () => window.clearTimeout(timer);
  }, []);
  if (!message) return null;
  return (
    <div className="toast" role="status">
      {message}
    </div>
  );
}

export function formatDateTime(value: string | null): string {
  if (!value) return "—";
  return new Date(value).toLocaleString("es-CO", { dateStyle: "short", timeStyle: "short" });
}

export function todayISO(): string {
  const now = new Date();
  const offset = now.getTimezoneOffset() * 60000;
  return new Date(now.getTime() - offset).toISOString().slice(0, 10);
}

/** Lo que el servidor acepta como usuario: "Dueño Ana" → "duenoana". */
export function toUsername(text: string): string {
  return text
    .normalize("NFD")
    .replace(/\p{M}/gu, "") // tildes y diéresis que NFD separa de la letra
    .toLowerCase()
    .replace(/[^a-z0-9._-]/g, "");
}
