# Historial de versiones

Formato basado en [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/). Las versiones siguen
[versionado semántico](https://semver.org/lang/es/).

## [0.4.0] — 2026-10-06

### Agregado
- **Módulos por cliente**: clientes, fiado, proveedores, reportes, descuentos, permisos por rol, Excel, impresión
  directa, facturación, aviso de versiones y licencias se encienden o apagan por instalación
  (`modules off proveedores`). Un módulo apagado no registra rutas, quita sus permisos y desaparece de la interfaz.
- **Logo del negocio** (PNG, JPG o WebP) en el menú, la pantalla de inicio y el tiquete; viaja con los respaldos.
- Unidades vendidas por producto en Ventas y en el turno de Caja.
- La venta en curso se conserva al cambiar de pantalla.
- Catálogo de ejemplo con 116 productos de minimercado (`docs/ejemplos/productos-ejemplo.xlsx`).

### Cambiado
- Las licencias pasan a ser un módulo **apagado de fábrica**: sin periodo de prueba ni límite de usuarios.

## [0.3.0] — 2026-10-06

### Agregado
- **Proveedores**: compras de mercancía, pago desde la caja, por fuera o a crédito, y cuentas por pagar con vencimientos.
- **Permisos por rol** editables desde la pantalla de Usuarios y nuevo rol **Supervisor**.
- **Facturación electrónica**: bandeja de salida (*outbox*) con reintentos y nota crédito al anular, lista para
  conectar un proveedor autorizado por la DIAN.
- **Impresión directa ESC/POS** por la cola de Windows o por red, con apertura del cajón monedero.
- Ícono junto al reloj de Windows (sin ventana de consola) y arranque automático opcional.
- Aviso de versión nueva para el administrador.
- **Licencias firmadas con Ed25519**.
- Respaldo al cerrar la caja y copia en una carpeta adicional (USB, OneDrive o Google Drive).
- Importación de productos desde Excel/CSV con vista previa, y exportación de catálogo y reportes a Excel.
- Recuperación de contraseña desde la consola de soporte.

### Corregido
- Pruebas del frontend con Node 25 o superior.

## [0.2.0]

### Agregado
- Ejecutable de Windows e instalador (PyInstaller + Inno Setup) construidos y probados en GitHub Actions.
- Asistente de configuración inicial en el navegador y comando `start`.
- Interfaz web en React + TypeScript para cajeros y administradores.
- Instalación en un paso y respaldos verificados de la base de datos.

## [0.1.0]

### Agregado
- Backend con arquitectura limpia: dominio, casos de uso, SQLite y API HTTP.
- Ventas idempotentes (un reintento de la caja no duplica la venta).
- Reportes calculados en la base de datos y consultas en transacciones de solo lectura.
- Límite de intentos fallidos de inicio de sesión.
