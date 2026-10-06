import { type ComponentType, useCallback, useEffect, useMemo, useState } from "react";
import { api, getToken, setToken, setUnauthorizedHandler } from "./api";
import { InvoicingBanner } from "./components/Invoicing";
import { LicenseBanner } from "./components/License";
import { Toaster } from "./components/ui";
import { CashPage } from "./pages/Cash";
import { CustomersPage } from "./pages/Customers";
import { LoginPage } from "./pages/Login";
import { ProductsPage } from "./pages/Products";
import { ReportsPage } from "./pages/Reports";
import { SalesPage } from "./pages/Sales";
import { SellPage } from "./pages/Sell";
import { SettingsPage } from "./pages/Settings";
import { SetupPage } from "./pages/Setup";
import { SuppliersPage } from "./pages/Suppliers";
import { ChangePasswordModal, UsersPage } from "./pages/Users";
import { type Session, SessionContext } from "./session";
import { type Me, type Permission, ROLE_LABEL, type Settings } from "./types";

interface Route {
  path: string;
  label: string;
  icon: string;
  shortcut?: string;
  permission?: Permission | Permission[]; // con una lista basta tener cualquiera de los permisos
  page: ComponentType;
}

// Para agregar una pantalla basta con una entrada aquí: el menú y los permisos salen de esta lista.
const ROUTES: Route[] = [
  { path: "vender", label: "Vender", icon: "🛒", shortcut: "F1", permission: "sell", page: SellPage },
  { path: "caja", label: "Caja", icon: "💵", shortcut: "F2", permission: "operate_cash", page: CashPage },
  { path: "ventas", label: "Ventas", icon: "🧾", shortcut: "F3", permission: "sell", page: SalesPage },
  { path: "productos", label: "Productos", icon: "📦", shortcut: "F4", page: ProductsPage },
  { path: "clientes", label: "Clientes", icon: "👥", page: CustomersPage },
  {
    path: "proveedores",
    label: "Proveedores",
    icon: "🚚",
    permission: ["manage_suppliers", "manage_inventory"],
    page: SuppliersPage,
  },
  { path: "reportes", label: "Reportes", icon: "📊", permission: "view_reports", page: ReportsPage },
  { path: "usuarios", label: "Usuarios", icon: "🔑", permission: "manage_users", page: UsersPage },
  { path: "ajustes", label: "Ajustes", icon: "⚙️", permission: "manage_settings", page: SettingsPage },
];

function useHashPath(): [string, (path: string) => void] {
  const read = () => window.location.hash.replace(/^#\/?/, "");
  const [path, setPath] = useState(read);
  useEffect(() => {
    const onChange = () => setPath(read());
    window.addEventListener("hashchange", onChange);
    return () => window.removeEventListener("hashchange", onChange);
  }, []);
  return [path, (next) => (window.location.hash = `/${next}`)];
}

export function App() {
  const [token, setTokenState] = useState(getToken);
  const [me, setMe] = useState<Me | null>(null);
  const [settings, setSettings] = useState<Settings | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [needsSetup, setNeedsSetup] = useState<boolean | null>(null);

  const logout = useCallback(() => {
    setToken(null);
    setTokenState(null);
    setMe(null);
  }, []);

  useEffect(() => setUnauthorizedHandler(logout), [logout]);

  const reloadSettings = useCallback(async () => {
    setSettings(await api.get<Settings>("/settings"));
  }, []);

  useEffect(() => {
    if (!token) return;
    setLoadError(null);
    Promise.all([api.get<Me>("/auth/me"), api.get<Settings>("/settings")])
      .then(([user, config]) => {
        setMe(user);
        setSettings(config);
      })
      .catch((error: Error) => setLoadError(error.message));
  }, [token]);

  useEffect(() => {
    if (token) return;
    api
      .get<{ needs_setup: boolean }>("/setup")
      .then((status) => setNeedsSetup(status.needs_setup))
      .catch(() => setNeedsSetup(false));
  }, [token]);

  const signIn = useCallback((newToken: string) => {
    setToken(newToken);
    setTokenState(newToken);
  }, []);

  if (!token && needsSetup === null) return <div className="empty">Cargando…</div>;
  if (!token && needsSetup) return <SetupPage onDone={signIn} />;
  if (!token) {
    return (
      <LoginPage
        onLogin={signIn}
      />
    );
  }
  if (loadError) {
    return (
      <div className="login">
        <div className="card">
          <div className="alert alert-error">{loadError}</div>
          <button className="btn" onClick={logout}>
            Volver a iniciar sesión
          </button>
        </div>
      </div>
    );
  }
  if (!me || !settings) return <div className="empty">Cargando…</div>;

  return <Shell me={me} settings={settings} logout={logout} reloadSettings={reloadSettings} />;
}

function Shell(props: { me: Me; settings: Settings; logout: () => void; reloadSettings: () => Promise<void> }) {
  const { me, settings, logout, reloadSettings } = props;
  const [path, navigate] = useHashPath();
  const [changingPassword, setChangingPassword] = useState(false);

  const session = useMemo<Session>(
    () => ({ me, settings, logout, reloadSettings, can: (p) => me.permissions.includes(p) }),
    [me, settings, logout, reloadSettings],
  );
  const allowed = (route: Route) =>
    route.permission === undefined || [route.permission].flat().some((permission) => session.can(permission));
  const routes = ROUTES.filter(allowed);
  const current = routes.find((route) => route.path === path) ?? routes[0];

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      const route = routes.find((r) => r.shortcut === event.key);
      if (route) {
        event.preventDefault();
        navigate(route.path);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  });

  const Page = current.page;
  return (
    <SessionContext.Provider value={session}>
      <div className="app">
        <nav className="sidebar" aria-label="Menú principal">
          <div className="brand">{settings.business_name}</div>
          {routes.map((route) => (
            <a
              key={route.path}
              href={`#/${route.path}`}
              className={`nav-link ${route === current ? "active" : ""}`}
              aria-current={route === current ? "page" : undefined}
            >
              <span aria-hidden>{route.icon}</span>
              {route.label}
              {route.shortcut && <span className="nav-key">{route.shortcut}</span>}
            </a>
          ))}
          <div className="sidebar-footer">
            <div>{me.full_name}</div>
            <div className="small" style={{ opacity: 0.75 }}>
              {ROLE_LABEL[me.role]}
            </div>
            <button className="btn btn-sm" onClick={() => setChangingPassword(true)}>
              Mi contraseña
            </button>
            <button className="btn btn-sm" onClick={logout}>
              Salir
            </button>
          </div>
        </nav>
        <main className="main">
          {session.can("manage_settings") && (
            <>
              <LicenseBanner onOpenSettings={() => navigate("ajustes")} />
              <InvoicingBanner onOpenSettings={() => navigate("ajustes")} />
            </>
          )}
          <Page key={current.path} />
        </main>
      </div>
      {changingPassword && <ChangePasswordModal onClose={() => setChangingPassword(false)} />}
      <Toaster />
    </SessionContext.Provider>
  );
}
