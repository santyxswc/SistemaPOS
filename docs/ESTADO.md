# Estado del proyecto: qué se hizo y qué falta

Actualizado el **6 de octubre de 2026**, versión **0.4.0**. Para el detalle técnico y las recetas, vea [`HOJA_DE_RUTA.md`](HOJA_DE_RUTA.md); para quitar o poner funciones por cliente, [`MODULOS.md`](MODULOS.md).

## Lo que se hizo en la 0.4.0

### 1. Sistema de módulos por cliente

El objetivo era poder entregarle a un cliente el sistema "sin X función o sin Y pestaña" el mismo día, sin tocar el código.

- Once funciones opcionales quedaron como **módulos**: `clientes`, `fiado`, `proveedores`, `reportes`, `descuentos`, `permisos`, `excel`, `impresion`, `facturacion`, `actualizaciones` y `licencias`.
- Se apagan o se encienden en el computador del cliente con `PuntoDeVentaConsola.exe modules off proveedores reportes` (o con dos líneas en su `.env`). Hay que cerrar y abrir el sistema para aplicar el cambio.
- Al apagar un módulo, en un solo lugar y sin `if` repartidos:
  - sus rutas de la API no se registran (responden 404);
  - sus permisos se le quitan a todos los usuarios, así que el servidor niega sus acciones aunque alguien llame la API a mano;
  - la interfaz quita sus pestañas, botones y secciones de Ajustes.
- Los datos nunca se borran: encender de nuevo el módulo los muestra igual. Los permisos por rol que el dueño había configurado para un módulo apagado también se conservan.
- Los requisitos se respetan solos: sin `clientes` no hay `fiado`.
- Un nombre mal escrito en el `.env` no pasa en silencio: el sistema muestra cuáles nombres existen.

**Dónde está en el código:** `src/pos/application/modules.py` (catálogo), `src/pos/config.py` (lectura del `.env`), `src/pos/presentation/http/app.py` (`OPTIONAL_ROUTES`), `frontend/src/App.tsx` (`ROUTES` con `module`) y `frontend/src/pages/Settings.tsx` (`SECTIONS`).

### 2. Licencias apagadas

- El sistema **ya no pide clave**: sin el módulo `licencias` no hay periodo de prueba, aviso ni límite de usuarios.
- El código de licencias se conservó completo (con sus pruebas), por si algún día se vende por planes: `modules on licencias`.
- Las instalaciones 0.3.0 que se actualicen pierden el límite de usuarios y el aviso de prueba. Si ya tenían una licencia instalada, queda guardada.

### 3. Logo del negocio

- **Ajustes → Logo del negocio**: PNG, JPG o WebP de hasta 1 MB. SVG no se acepta a propósito, porque puede llevar código.
- Sale en el menú lateral, en la pantalla de inicio de sesión y en el tiquete que se imprime desde el navegador.
- Se guarda dentro de la base de datos, así que viaja con los respaldos.

### 4. Mejoras pedidas al probar

- **Ventas:** cada venta muestra cuántas unidades de cada producto se vendieron ("5 × Arroz Diana 500 g") y una columna con el total de unidades.
- **Caja:** muestra las unidades vendidas en el turno y una tabla de productos vendidos.
- **Vender:** la venta en curso ya no se pierde al ir a otra pantalla y volver. Se vacía al salir de la sesión.
- **Catálogo de ejemplo:** `docs/ejemplos/productos-ejemplo.xlsx` trae 116 productos de minimercado (IVA 0, 5 y 19 %; venta por unidad, kg y libra).

### 5. Calidad

- 218 pruebas de backend y 28 de interfaz, todas pasan. Las nuevas cubren:
  - módulos apagados: rutas, permisos, fiado y permisos ocultos que se conservan;
  - el sistema sin licencias;
  - el logo, incluido el rechazo de archivos que no son imagen.
- Se probó el servidor real con módulos apagados y se tomaron capturas en Edge: pantalla de inicio con logo, menú sin Proveedores ni Reportes y Ajustes con la sección del logo.
- Todos los commits están a nombre de S4ntyx, sin coautoría.

## Lo que falta

### Para probar usted (no se puede hacer sin el hardware o sin el cliente)

- [ ] **Instalar la 0.4.0** encima de la 0.3.0 en su computador (el `setup.exe` está en GitHub Releases). Revise que sus datos de prueba sigan ahí y suba el logo de Dulce Eva.
- [ ] **Imprimir un tiquete real** en la impresora térmica: desde el navegador (con el logo) y con impresión directa.
- [ ] **Probar con un lector de código de barras real.**
- [ ] **Probar el instalador en un computador limpio** (o una máquina virtual con Windows recién instalado).
- [ ] **Antes de usar con clientes:** deje en blanco la base de datos de prueba (cierre el sistema y borre `%LOCALAPPDATA%\PuntoDeVenta\data\pos.sqlite3`).

### Funciones que no existen todavía (en orden sugerido)

1. **Perfiles de módulos.** Hoy se apagan uno por uno. Un perfil (`tienda`, `restaurante`, `minimercado`) encendería un grupo de una vez, con `modules perfil restaurante`. Es poco trabajo: un diccionario en `modules.py` y un comando más.
2. **Funciones de restaurante**, como módulos nuevos: mesas, comandas a cocina, propinas y división de cuentas. Hoy el sistema sirve para restaurantes de mostrador, pero no para servicio a la mesa. La receta para agregar un módulo está en `MODULOS.md`.
3. **Logo en el tiquete de impresión directa** (ESC/POS). Hoy el logo sale en el tiquete del navegador, pero no en la impresión directa: hay que convertir la imagen a mapa de bits para la impresora.
4. **Módulo de inventario.** Hoy el control de existencias es parte del núcleo; un negocio que no lo quiera debe marcar sus productos "sin control de existencias". Se podría volver un módulo.
5. **Facturación electrónica DIAN con un proveedor real.** La bandeja está lista; falta el contrato con un proveedor autorizado y su adaptador. Consulte primero a un contador.
6. **Recordar la venta en curso al recargar la página (F5).** Hoy se conserva al cambiar de pantalla, no al recargar; habría que volver a consultar precios al restaurarla.
7. **Varias sedes o en la nube** (PostgreSQL). La arquitectura lo permite (ver la hoja de ruta), pero no está hecho.

### DevOps (para más adelante, como se habló)

- [ ] Imagen Docker y despliegue en un servidor (para clientes con varias cajas en red o en la nube).
- [ ] Registros estructurados (JSON) y monitoreo de las instalaciones (que avisen si un respaldo falla).
- [ ] Firma digital del instalador, para quitar el aviso "Windows protegió su PC".
- [ ] Revisión de tipos con mypy en el CI y análisis de dependencias vulnerables (Dependabot).
- [ ] Ambiente de pruebas automático de la versión publicada (instalar el `setup.exe` en una máquina virtual de GitHub Actions).
