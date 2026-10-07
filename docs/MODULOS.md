# Módulos: quitar o poner funciones a cada cliente

Cada cliente puede tener un sistema distinto **sin cambiar el código**. Lo que es igual para todos es el **núcleo**:

> Vender · Caja · Ventas · Productos e inventario · Usuarios · Ajustes · Respaldos · Logo

Todo lo demás es un **módulo** que usted (el técnico) enciende o apaga en el computador de cada cliente. El dueño del negocio no lo ve ni lo puede cambiar.

## Los módulos

| Módulo | Qué es | De fábrica |
| --- | --- | --- |
| `clientes` | Pestaña Clientes: datos de contacto y estado de cuenta | encendido |
| `fiado` | Ventas fiadas con cupo por cliente y abonos (necesita `clientes`) | encendido |
| `proveedores` | Pestaña Proveedores: compras de mercancía y cuentas por pagar | encendido |
| `reportes` | Pestaña Reportes y Excel para el contador | encendido |
| `descuentos` | Descuentos por producto al vender | encendido |
| `permisos` | Usuarios → Permisos por rol (sin él rigen los permisos de fábrica) | encendido |
| `excel` | Importar productos desde Excel/CSV y exportar el catálogo | encendido |
| `impresion` | Impresión directa en la impresora térmica y botón Abrir cajón | encendido |
| `facturacion` | Bandeja de documentos electrónicos DIAN (además necesita `POS_INVOICE_PROVIDER`) | encendido |
| `actualizaciones` | Aviso al administrador cuando hay una versión nueva | encendido |
| `licencias` | Límite de usuarios por plan con códigos firmados | **apagado** |

## Quitar una función a un cliente (1 minuto)

En el computador del cliente, en una consola:

```
cd "%LOCALAPPDATA%\Programs\PuntoDeVenta"
PuntoDeVentaConsola.exe modules off proveedores reportes
```

Luego cierre el sistema (ícono junto al reloj → Apagar) y ábralo de nuevo. Listo: las pestañas ya no aparecen.

Otros usos:

```
PuntoDeVentaConsola.exe modules                 lista cómo está cada módulo en este cliente
PuntoDeVentaConsola.exe modules on proveedores  lo vuelve a encender
PuntoDeVentaConsola.exe modules on licencias    enciende uno que viene apagado
```

Si prefiere hacerlo a mano, el comando solo escribe dos líneas en `%LOCALAPPDATA%\PuntoDeVenta\.env`:

```
POS_MODULES_DISABLED=proveedores,reportes
POS_MODULES_ENABLED=licencias
```

Un nombre mal escrito no pasa en silencio: el sistema no arranca y el mensaje dice cuáles nombres existen.

## Qué pasa al apagar un módulo

1. **Sus rutas de la API no existen** (responden 404), aunque alguien las llame a mano.
2. **Sus permisos desaparecen de todos los usuarios**. Los casos de uso que los piden se niegan, y la interfaz oculta lo que depende de ellos (por ejemplo, sin `descuentos` desaparece la columna de descuento al vender; sin `fiado`, el botón Fiado al cobrar).
3. **La interfaz quita sus pestañas y secciones de Ajustes**.
4. **Los datos no se borran.** Si el cliente tenía proveedores y apaga el módulo, siguen en la base de datos; al encenderlo de nuevo aparecen igual. Lo mismo con los permisos por rol: lo que el dueño había configurado para un módulo apagado se conserva.
5. Un módulo que necesita otro se apaga con él: sin `clientes` no hay `fiado`.

## Agregar un módulo nuevo (para el programador)

Ejemplo: un módulo `mesas` para restaurantes.

1. **Backend, catálogo:** en `src/pos/application/modules.py` agregue `TABLES = "mesas"` al enum `Module` y su `ModuleInfo` a `CATALOG` (nombre, descripción, si viene encendido, de qué depende y qué permisos trae).
2. **Backend, código:** dominio, casos de uso y repositorio como cualquier otra función (ver `docs/HOJA_DE_RUTA.md`, sección 7). Las rutas van en su propio archivo `presentation/http/routes/tables.py`.
3. **Backend, rutas:** en `presentation/http/app.py` agregue `Module.TABLES: (tables,)` a `OPTIONAL_ROUTES`.
4. **Interfaz:** agregue `"mesas"` al tipo `ModuleId` (`frontend/src/types.ts`) y su pantalla a `ROUTES` en `App.tsx` con `module: "mesas"`. Si tiene una sección en Ajustes, agréguela a `SECTIONS` en `pages/Settings.tsx` con `module: "mesas"`.
5. **Pruebas:** una prueba con el módulo apagado (`modules = ModuleSet.configure(disable={Module.TABLES})`, ver `tests/integration/test_modules.py`).

No hace falta tocar nada más: el menú, los permisos y la consola (`modules`) lo toman del catálogo.
