// Nombre y logo del negocio: en el menú, en la pantalla de inicio y en el tiquete. El logo
// se sube en Ajustes y vive en la base de datos, así que viaja con los respaldos.

import { useRef } from "react";
import { api } from "../api";
import { useSession } from "../session";
import type { Branding } from "../types";
import { ErrorAlert, toast, useAction } from "./ui";

/** Dirección del logo; cambia con cada logo nuevo para que el navegador no muestre el anterior. */
export function logoUrl(version: string): string {
  return `/api/v1/branding/logo?v=${encodeURIComponent(version)}`;
}

export function BrandMark({ branding, className = "brand" }: { branding: Branding; className?: string }) {
  return (
    <div className={className}>
      {branding.logo_version && <img className="brand-logo" src={logoUrl(branding.logo_version)} alt="" />}
      <span>{branding.business_name}</span>
    </div>
  );
}

export function LogoCard() {
  const { branding, reloadBranding } = useSession();
  const input = useRef<HTMLInputElement>(null);
  const { busy, error, run } = useAction();

  async function upload(file: File | undefined) {
    if (!file) return;
    const done = await run(async () => {
      await api.upload("/branding/logo", file, undefined, "PUT");
      await reloadBranding();
      return true;
    });
    if (input.current) input.current.value = "";
    if (done !== undefined) toast("Logo guardado");
  }

  async function remove() {
    const done = await run(async () => {
      await api.delete("/branding/logo");
      await reloadBranding();
      return true;
    });
    if (done !== undefined) toast("Logo quitado");
  }

  return (
    <section className="card" style={{ marginTop: 16 }} aria-labelledby="logo-title">
      <h2 id="logo-title">Logo del negocio</h2>
      <p className="muted small">
        Aparece en el menú, en la pantalla de inicio de sesión y en el tiquete. PNG, JPG o WebP de hasta 1 MB; mejor
        con fondo transparente o blanco.
      </p>
      <ErrorAlert error={error} />
      <div className="row">
        {branding.logo_version ? (
          <img className="logo-preview" src={logoUrl(branding.logo_version)} alt={`Logo de ${branding.business_name}`} />
        ) : (
          <span className="muted">Todavía no hay logo.</span>
        )}
        <span className="spacer" />
        <input
          ref={input}
          type="file"
          accept="image/png,image/jpeg,image/webp"
          hidden
          onChange={(e) => void upload(e.target.files?.[0])}
          aria-label="Archivo del logo"
        />
        <button className="btn" disabled={busy} onClick={() => input.current?.click()}>
          {branding.logo_version ? "Cambiar logo" : "Subir logo"}
        </button>
        {branding.logo_version && (
          <button className="btn btn-danger" disabled={busy} onClick={remove}>
            Quitar
          </button>
        )}
      </div>
    </section>
  );
}
