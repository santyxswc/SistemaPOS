# Adaptar y extender el sistema

El mismo código sirve para negocios distintos. Este documento explica qué se ajusta sin programar y dónde se agrega código cuando hace falta.

## Sin escribir código

Sin escribir código, el técnico apaga lo que el cliente no contrató (`modules off ...`, ver [`docs/MODULOS.md`](docs/MODULOS.md)) y el dueño ajusta el resto desde **Ajustes** (o `PATCH /api/v1/settings`):

| Necesidad del cliente | Ajuste |
| --- | --- |
| Restaurante con impuesto al consumo del 8 % | Impuesto por defecto `8` |
| Precios sin impuesto (ventas a empresas) | Desmarcar "Los precios ya incluyen el impuesto" |
| Acepta Bancolombia o transferencias | Agregar un método de tipo electrónico |
| No fía | Desmarcar "Permitir ventas fiadas" |
| Vende aunque el sistema marque cero existencias | Marcar la opción correspondiente |
| Datos del tiquete | Nombre, NIT, dirección, teléfono y mensaje al pie |
| Copia de los respaldos fuera del computador | Ajustes → Respaldos → Carpeta adicional |
| Encargado de turno que anula ventas pero no cambia precios | Usuario con rol Supervisor |
| Que el cajero vea reportes, o que no reciba abonos | Usuarios → Permisos por rol |
| Imprimir sin el cuadro del navegador y abrir el cajón | Ajustes → Impresora de tiquetes (Windows o de red) |
| Compras a crédito a los proveedores | Proveedores → Registrar compra, forma de pago "A crédito" |
| Logo en el menú, la pantalla de inicio y el tiquete | Ajustes → Logo del negocio |
| No quiere proveedores, reportes o fiado | `modules off proveedores reportes fiado` (el técnico) |
| Límite de usuarios según el plan vendido | `modules on licencias` y una licencia emitida con `packaging/licencia.py` |

Con código, en los puntos de extensión previstos:

- **Facturación electrónica DIAN**: crear una clase con el método `issue(document, sale, settings)` que llame al API de un proveedor autorizado, registrarla en `PROVIDERS` (`infrastructure/invoicing.py`) y activarla con `POS_INVOICE_PROVIDER`. La bandeja de salida, los reintentos, la nota crédito de las anulaciones y la pantalla de revisión ya funcionan (pruébelos con `POS_INVOICE_PROVIDER=simulado`).
- **PostgreSQL o la nube**: implementar los repositorios, `SalesReportQueries` y la unidad de trabajo de `application/ports.py` en `infrastructure/persistence/postgres/` y cambiar una línea en `bootstrap.py`.
- **Varios servidores**: reemplazar `InMemoryLoginThrottle` por una implementación compartida (p. ej. Redis).
- **Permisos de fábrica de un rol**: `ROLE_PERMISSIONS` en `domain/users.py` (cada negocio los ajusta después en Usuarios).
- **Otra impresora** (PDF, tiquete por WhatsApp): otra implementación de `ReceiptPrinter` que traduzca el `ReceiptDocument`.
- **Alertas por WhatsApp o correo**: suscribir un manejador a `StockLow` o `CashSessionClosed` en `bootstrap.py`.

## Recetas para extender el código

| Quiero... | Pasos |
| --- | --- |
| **Una pantalla nueva** | Crear `frontend/src/pages/MiPantalla.tsx` y agregar una entrada a `ROUTES` en `frontend/src/App.tsx` (con su permiso). El menú se arma solo. |
| **Un caso de uso nuevo** | Clase con `execute()` en `application/use_cases/<módulo>.py` → registrarla en `Container` y `build_container` (`bootstrap.py`) → ruta en `presentation/http/routes/` → prueba en `tests/`. |
| **Un dato nuevo en una tabla** | Nueva migración al final de `MIGRATIONS` → actualizar el repositorio (`repositories.py`) → el campo en la entidad del dominio → prueba de migración sobre una base existente (ver `tests/integration/test_migrations.py`). |
| **Un método de pago nuevo** (Bancolombia, Bre‑B...) | No requiere código: Ajustes → Métodos de pago → Agregar, tipo "Electrónico". |
| **Un tipo de pago con comportamiento nuevo** (bonos, puntos) | Nuevo valor en `PaymentKind` y su `PaymentBehavior` en `domain/payments.py`. Ventas y caja no cambian. |
| **Reaccionar a algo** (avisar por WhatsApp cuando falte stock) | Manejador para el evento (`StockLow`, `SaleCompleted`, `CashSessionClosed`, `PurchaseRegistered`) y `bus.subscribe(...)` en `bootstrap.py`. |
| **Una tarea de fondo** (enviar algo cada cierto tiempo) | Un `PeriodicWorker` (`infrastructure/background.py`) en `background_workers` del contenedor: la línea de comandos lo inicia con el servidor. `wake()` lo despierta al instante. |
| **Un proveedor de facturación electrónica** | Clase con `issue(...)`, entrada en `PROVIDERS`, `POS_INVOICE_PROVIDER` en el `.env`. |
| **Otro formato de tiquete** (PDF, WhatsApp) | Implementar `ReceiptPrinter` (`application/ports.py`) traduciendo el `ReceiptDocument` de `application/receipts.py`. |
| **Otra base de datos** | Implementar los repositorios, `SalesReportQueries` y `UnitOfWork` de `application/ports.py`; cambiar la fábrica `uow` en `bootstrap.py`. |
| **Cambiar la política de licencias** (días de prueba, usuarios al vencer) | Constantes al inicio de `domain/licensing.py`. Las pruebas de `tests/unit/test_licensing.py` dicen qué se espera. |
| **Cobrar aparte por una función** (p. ej. módulo de restaurante) | Agregar el dato a la licencia (`License` y `_payload` en `infrastructure/licensing.py`), y preguntar a `LicensePolicy` en el caso de uso de esa función. |
| **Otra columna en la importación de productos** | Agregarla a `PRODUCT_COLUMNS` (`presentation/http/workbooks.py`) y leerla en `catalog_import.py`. |
| **Otro destino de respaldo** (nube) | Implementar `BackupService` (`application/ports.py`) o envolver `SqliteBackupService` para subir el archivo después de crearlo. |
| **Un rol nuevo** | Valor nuevo en `Role`, `ROLE_LABELS`, `EDITABLE_ROLES` y su entrada en `ROLE_PERMISSIONS` (`domain/users.py`); en el frontend, `ROLE_LABEL` (`types.ts`) y la opción en `Users.tsx`. |
| **Un permiso nuevo** | Valor en `Permission` y su texto en `PERMISSION_LABELS`; dárselo a los roles de fábrica que corresponda; revisarlo con `actor.require(...)` en el caso de uso; en el frontend, el tipo `Permission` (`types.ts`). Los negocios que personalizaron el rol no lo reciben solos: el administrador lo marca en Permisos por rol. |
