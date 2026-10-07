// Cliente HTTP de la API. Los errores llegan con un mensaje listo para mostrar al usuario.

const TOKEN_KEY = "pos.token";

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly code: string,
  ) {
    super(message);
  }
}

let onUnauthorized: () => void = () => {};

export function setUnauthorizedHandler(handler: () => void): void {
  onUnauthorized = handler;
}

export function getToken(): string | null {
  try {
    return localStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

export function setToken(token: string | null): void {
  try {
    if (token) localStorage.setItem(TOKEN_KEY, token);
    else localStorage.removeItem(TOKEN_KEY);
  } catch {
    // Sin almacenamiento (navegación privada): la sesión dura lo que dure la pestaña.
  }
}

type Query = Record<string, string | number | boolean | null | undefined>;

interface RequestOptions {
  body?: unknown;
  query?: Query;
  headers?: Record<string, string>;
}

function buildUrl(path: string, query: Query = {}): URL {
  const url = new URL(`/api/v1${path}`, window.location.origin);
  for (const [key, value] of Object.entries(query)) {
    if (value !== null && value !== undefined && value !== "") url.searchParams.set(key, String(value));
  }
  return url;
}

async function send(method: string, path: string, options: RequestOptions): Promise<Response> {
  const headers: Record<string, string> = { ...options.headers };
  const token = getToken();
  if (token) headers.Authorization = `Bearer ${token}`;
  let body: BodyInit | undefined;
  if (options.body instanceof FormData) {
    body = options.body; // el navegador pone el Content-Type con su separador
  } else if (options.body !== undefined) {
    headers["Content-Type"] = "application/json";
    body = JSON.stringify(options.body);
  }

  let response: Response;
  try {
    response = await fetch(buildUrl(path, options.query), { method, headers, body });
  } catch {
    throw new ApiError("No hay conexión con el sistema. Revise que el servidor esté encendido.", 0, "network");
  }
  if (!response.ok) {
    const data = await response.json().catch(() => null);
    const error = data?.error ?? {};
    // 401 en estas rutas es una contraseña equivocada, no una sesión vencida.
    const checksPassword = path === "/auth/login" || path === "/auth/change-password";
    if (response.status === 401 && !checksPassword) onUnauthorized();
    const fallback = response.status === 413 ? "El archivo es demasiado grande" : "Ocurrió un error inesperado";
    throw new ApiError(error.message ?? fallback, response.status, error.code ?? "unknown");
  }
  return response;
}

async function request<T>(method: string, path: string, options: RequestOptions = {}): Promise<T> {
  const response = await send(method, path, options);
  // Sin contenido: null (no undefined) para distinguirlo de una acción que falló en useAction.
  if (response.status === 204) return null as T;
  return (await response.json().catch(() => null)) as T;
}

function fileName(response: Response, fallback: string): string {
  const match = /filename="?([^";]+)"?/.exec(response.headers.get("Content-Disposition") ?? "");
  return match?.[1] ?? fallback;
}

/** Descarga un archivo de la API (con la sesión) y lo entrega al navegador para guardarlo. */
async function download(path: string, query?: Query, fallbackName = "archivo"): Promise<true> {
  const response = await send("GET", path, { query });
  const url = URL.createObjectURL(await response.blob());
  const link = document.createElement("a");
  link.href = url;
  link.download = fileName(response, fallbackName);
  document.body.appendChild(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 10_000);
  return true;
}

export const api = {
  get: <T>(path: string, query?: Query) => request<T>("GET", path, { query }),
  post: <T>(path: string, body?: unknown, headers?: Record<string, string>) =>
    request<T>("POST", path, { body: body ?? {}, headers }),
  patch: <T>(path: string, body: unknown) => request<T>("PATCH", path, { body }),
  put: <T>(path: string, body: unknown) => request<T>("PUT", path, { body }),
  delete: <T>(path: string) => request<T>("DELETE", path),
  upload: <T>(path: string, file: File, query?: Query, method: "POST" | "PUT" = "POST") => {
    const form = new FormData();
    form.append("file", file);
    return request<T>(method, path, { body: form, query });
  },
  download,
};

export function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : "Ocurrió un error inesperado";
}
