// Sesión del usuario: quién es, qué puede hacer y la configuración del negocio.

import { createContext, useContext } from "react";
import type { Me, Permission, Settings } from "./types";

export interface Session {
  me: Me;
  settings: Settings;
  can: (permission: Permission) => boolean;
  reloadSettings: () => Promise<void>;
  logout: () => void;
}

export const SessionContext = createContext<Session | null>(null);

export function useSession(): Session {
  const session = useContext(SessionContext);
  if (!session) throw new Error("useSession debe usarse dentro de SessionContext");
  return session;
}
