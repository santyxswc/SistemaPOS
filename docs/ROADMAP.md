# Hoja de ruta

Estado actual: versión **0.4.0**. Lo publicado en cada versión está en [`CHANGELOG.md`](../CHANGELOG.md).

## Próximas funciones

1. **Perfiles de módulos.** Hoy se apagan uno por uno. Un perfil (`tienda`, `restaurante`, `minimercado`) encendería un grupo de una vez, con `modules perfil restaurante`. Es poco trabajo: un diccionario en `modules.py` y un comando más.
2. **Funciones de restaurante**, como módulos nuevos: mesas, comandas a cocina, propinas y división de cuentas. Hoy el sistema sirve para restaurantes de mostrador, pero no para servicio a la mesa. La receta para agregar un módulo está en [`MODULOS.md`](MODULOS.md).
3. **Logo en el tiquete de impresión directa** (ESC/POS). Hoy el logo sale en el tiquete del navegador, pero no en la impresión directa: hay que convertir la imagen a mapa de bits para la impresora.
4. **Módulo de inventario.** Hoy el control de existencias es parte del núcleo; un negocio que no lo quiera debe marcar sus productos "sin control de existencias". Se podría volver un módulo.
5. **Facturación electrónica DIAN con un proveedor real.** La bandeja está lista; falta el contrato con un proveedor autorizado y su adaptador. Requiere validar el proceso con un contador.
6. **Recordar la venta en curso al recargar la página (F5).** Hoy se conserva al cambiar de pantalla, no al recargar; habría que volver a consultar precios al restaurarla.
7. **Varias sedes o en la nube** (PostgreSQL). La arquitectura lo permite (implementar los puertos de `application/ports.py`), pero no está hecho.

## Infraestructura y DevOps

- [ ] Imagen Docker y despliegue en un servidor (para clientes con varias cajas en red o en la nube).
- [ ] Registros estructurados (JSON) y monitoreo de las instalaciones (que avisen si un respaldo falla).
- [ ] Firma digital del instalador, para quitar el aviso "Windows protegió su PC".
- [x] Análisis de dependencias desactualizadas o vulnerables (Dependabot).
- [ ] Revisión de tipos con mypy en el CI.
- [ ] Ambiente de pruebas automático de la versión publicada (instalar el `setup.exe` en una máquina virtual de GitHub Actions).

## Limitaciones conocidas

Cosas que funcionan, pero que conviene tener presentes.

| Tema | Detalle | Cuándo atenderlo |
| --- | --- | --- |
| Red local sin HTTPS | Con `POS_HOST=0.0.0.0` otros equipos se conectan por HTTP sin cifrar. En la red de la tienda es aceptable; por Wi‑Fi abierto o internet, no. | Antes de ofrecer acceso remoto |
| Sesión en `localStorage` | El token de sesión se guarda en el navegador. Es estándar en aplicaciones locales; si algún día hay acceso público por internet, migrar a cookies `HttpOnly`. | Con la versión en la nube |
| Freno de login en memoria | El conteo de intentos fallidos se pierde al reiniciar y no se comparte entre servidores. Correcto para un servidor por negocio. | Con varios servidores |
| SQLite | Excelente para 1 a 5 cajas en un mismo local. Para más carga o varias sedes, PostgreSQL. **Nunca** poner la base de datos en una carpeta compartida de red: los demás equipos deben entrar por el navegador. | Con varias sedes |
| Impresión directa y varias cajas | La impresión directa sale por la impresora **del computador donde corre el sistema** o por una impresora de red. Una caja en otro computador con su impresora USB debe imprimir desde el navegador (o tener una impresora de red propia). | Si un cliente tiene varias cajas con impresora USB |
| Controladores solo XPS | La cola de Windows se usa en modo RAW. Casi todos los controladores de impresoras térmicas lo aceptan; si alguno no, use la impresora como "Genérica / Solo texto" o por red. | Si aparece |
| Compras | No se pueden anular ni editar: una compra equivocada se corrige con un ajuste de inventario (y, si fue a crédito, con un pago). | Si los clientes del piloto lo piden |
| Apagar el sistema | "Apagar el punto de venta" en el ícono del reloj detiene el servidor para todas las cajas. | — |
| Aviso de npm `allow-scripts` | npm 11 bloquea el script de instalación de `esbuild`; la compilación funciona igual. Si algún día falla: `npm approve-scripts esbuild`. | Si aparece un error |
| Excel antiguo (.xls) | La importación lee .xlsx y .csv, no el formato de Excel 97-2003. El mensaje de error le pide al usuario guardarlo como .xlsx. | Si un cliente lo pide |
| Números en CSV | En un CSV, "12.345" se lee como doce mil trescientos cuarenta y cinco (punto de miles, como se escribe en Colombia). Para kilos con decimales use coma ("12,345") o un archivo .xlsx, donde los números no son ambiguos. | — |
