// Sesión del usuario: quién es, qué puede hacer, qué módulos tiene este negocio y su configuración.

import { createContext, useContext } from "react";
import type { Branding, Me, ModuleId, Permission, Settings } from "./types";

export interface Session {
  me: Me;
  settings: Settings;
  branding: Branding;
  /** ¿El usuario tiene el permiso? (ya viene sin los permisos de los módulos apagados) */
  can: (permission: Permission) => boolean;
  /** ¿Este negocio tiene el módulo? (lo decide el técnico en el .env del cliente) */
  has: (module: ModuleId) => boolean;
  reloadSettings: () => Promise<void>;
  reloadBranding: () => Promise<void>;
  logout: () => void;
}

export const SessionContext = createContext<Session | null>(null);

export function useSession(): Session {
  const session = useContext(SessionContext);
  if (!session) throw new Error("useSession debe usarse dentro de SessionContext");
  return session;
}
