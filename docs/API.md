# API HTTP

Todas las rutas, salvo el login, `/branding` y `/health`, piden el encabezado `Authorization: Bearer <token>`. El dinero viaja como texto (`"12500.00"`) para no perder exactitud.

```http
POST /api/v1/auth/login
{"username": "admin", "password": "..."}

POST /api/v1/sales
Idempotency-Key: 6f1c2a0e-...   (opcional, recomendado: la misma clave en cada reintento)
{
  "items": [{"product_id": "…", "quantity": 2}],
  "payments": [{"method": "nequi", "amount": "3000"}, {"method": "efectivo", "amount": "5000"}]
}
```

| Módulo | Rutas (prefijo `/api/v1`) |
| --- | --- |
| Acceso | `POST /auth/login`, `GET /auth/me`, `POST /auth/change-password` |
| Usuarios | `GET /users`, `POST /users`, `PATCH /users/{id}`, `GET /roles`, `PUT /roles/{rol}` (`{"permissions": [...]}` o `{"reset": true}`) |
| Configuración | `GET /settings`, `PATCH /settings`, `GET /updates`, `GET /modules` |
| Marca | `GET /branding` (público), `GET /branding/logo` (público), `PUT /branding/logo` (archivo en `file`), `DELETE /branding/logo` |
| Licencia (módulo) | `GET /license`, `POST /license` (`{"code": "POS1...."}`) |
| Respaldos | `GET /backups`, `POST /backups` |
| Catálogo | `GET/POST /categories`, `GET/POST /products`, `GET /products/lookup?code=`, `GET/PATCH /products/{id}`, `GET /products/export` (Excel), `GET /products/import-template`, `POST /products/import?dry_run=true&update_existing=false` (archivo en `file`) |
| Inventario | `POST /inventory/purchases`, `POST /inventory/adjustments`, `GET /inventory/low-stock`, `GET /inventory/movements?product_id=` |
| Caja | `POST /cash-sessions`, `GET /cash-sessions`, `GET /cash-sessions/current`, `POST /cash-sessions/current/movements`, `POST /cash-sessions/current/close`, `POST /cash-sessions/{id}/close`, `GET /cash-sessions/{id}` |
| Ventas | `POST /sales`, `GET /sales?from=&to=`, `GET /sales/{id}`, `POST /sales/{id}/void`, `POST /sales/{id}/print` (`{"copy": true}` para reimprimir) |
| Impresión | `GET /printing/printers`, `POST /printing/test`, `POST /cash-drawer/open` |
| Proveedores | `GET/POST /suppliers`, `GET/PATCH /suppliers/{id}`, `GET /suppliers/{id}/statement`, `POST /suppliers/{id}/payments`, `GET /suppliers/payables` |
| Compras | `POST /purchases` (forma de pago `cash_drawer`, `external` o `credit`), `GET /purchases?pending=1&supplier_id=`, `GET /purchases/{id}` |
| Facturación electrónica | `GET /invoicing`, `GET /invoicing/documents?status=failed,rejected`, `POST /invoicing/documents/{id}/retry` |
| Clientes | `GET/POST /customers`, `GET/PATCH /customers/{id}`, `GET /customers/{id}/statement`, `POST /customers/{id}/payments` |
| Reportes | `GET /reports/sales-summary?from=&to=&group_by=month`, `GET /reports/top-products?from=&to=`, `GET /reports/export?from=&to=` (Excel para el contador) |

Todos los errores tienen la misma forma, con mensajes listos para mostrar al usuario:

```json
{"error": {"code": "insufficient_stock", "message": "Stock insuficiente de «Arroz 500 g»: hay 1 y se piden 2"}}
```

400 dato inválido, 401 sin sesión, 403 sin permiso, 404 no existe (también las rutas de un módulo apagado), 409 duplicado o conflicto, 422 regla de negocio, 429 demasiados intentos de inicio de sesión.
