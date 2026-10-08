# Instalación, operación y soporte

Guía para instalar el sistema en el computador de un negocio, mantenerlo y resolver problemas comunes.

## Instalación rápida

El cliente **no necesita instalar Python ni nada más**.

1. Ejecute **`PuntoDeVenta-<versión>-setup.exe`**. No pide permisos de administrador; ofrece crear un acceso directo en el escritorio, abrir el sistema al encender el computador y programar el respaldo diario.
2. Abra **Punto de Venta**. La primera vez, el navegador pide el nombre del negocio y crea la cuenta del administrador.
3. Cargue los productos desde Excel (**Productos → Importar**; hay una plantilla de ejemplo, y `docs/ejemplos/productos-ejemplo.xlsx` trae 116 productos de minimercado para probar) y, en **Ajustes**, suba el logo y elija una carpeta de respaldo adicional (USB u OneDrive).
4. Si el cliente no contrató alguna función, apáguela: `PuntoDeVentaConsola.exe modules off proveedores reportes` y abra el sistema de nuevo.

El sistema no abre ventanas negras: queda como un **ícono junto al reloj de Windows** con un menú para abrirlo, respaldar ahora, abrir la carpeta de datos o apagarlo. Abrirlo de nuevo cuando ya está abierto solo abre el navegador. Los comandos de soporte (`modules`, `reset-password`) se ejecutan con **`PuntoDeVentaConsola.exe`**, que es el mismo programa con consola.

Sin instalador, el `.zip` sirve igual: descomprima la carpeta `PuntoDeVenta` y abra `PuntoDeVenta.exe`.

| Qué | Dónde |
| --- | --- |
| Programa | `%LOCALAPPDATA%\Programs\PuntoDeVenta` (lo reemplaza cada actualización) |
| Datos del negocio | `%LOCALAPPDATA%\PuntoDeVenta`: `.env`, `data\pos.sqlite3`, `data\backups`, `logs\pos.log` |

Actualizar es ejecutar el instalador de la versión nueva: los datos no se tocan y la base de datos se actualiza sola al abrir. Desinstalar tampoco borra los datos.

**Respaldos**: se hace uno al cerrar cada caja y, si se eligió al instalar, otro todos los días a las 10 p. m. (se conservan los últimos 30). En **Ajustes → Respaldos** se puede respaldar en cualquier momento y elegir una carpeta adicional (USB, OneDrive o Google Drive) donde se copia cada respaldo: así sobreviven a un disco dañado o a un robo. Para restaurar, cierre el sistema y reemplace `data\pos.sqlite3` por el respaldo elegido.

**Licencias**: vienen **apagadas**: no hay periodo de prueba ni límite de usuarios. Si algún día se necesitan, se encienden por cliente con `modules on licencias`; entonces rige el límite del plan y los códigos se emiten con `packaging/licencia.py`, que solo tiene el proveedor.

**Red local**: para usarlo desde otros computadores, ponga `POS_HOST=0.0.0.0` en el `.env` de la carpeta de datos y entre a `http://IP-DEL-SERVIDOR:8000`.

## Publicar una versión

1. Suba la versión en `src/pos/__init__.py`, `pyproject.toml` y `frontend/package.json`.
2. Cree y publique la etiqueta: `git tag v0.3.0 && git push origin v0.3.0`.
3. GitHub Actions ("Versión para Windows") compila la interfaz, empaqueta el `.exe`, lo **arranca y prueba**, y publica un *Release* con el `.zip` y el `setup.exe`. Si la etiqueta no coincide con la versión del código, falla.

Para construirla en su propio computador (necesita Node; el `setup.exe` solo si tiene [Inno Setup 6](https://jrsoftware.org/isinfo.php)):

```bash
pip install -r requirements-build.txt
python packaging/build.py          # resultado en dist/
```

Windows mostrará "Windows protegió su PC" al abrir un instalador sin firma digital: el cliente debe pulsar *Más información → Ejecutar de todas formas*. Para quitar el aviso hace falta un certificado de firma de código.

## Sin instalador, desde el código fuente

Con [Python 3.11+](https://www.python.org/downloads/): `instalar.bat` prepara el entorno e `iniciar-pos.bat` abre el sistema. `respaldo.bat` hace la copia de seguridad.

## Guía paso a paso en el negocio

**Antes de ir:**
1. Solo si el cliente tiene el módulo de licencias encendido: emita su código con `packaging/licencia.py`.
2. Pida la lista de productos y pásela a la plantilla (Productos → Importar → "Descargar plantilla de ejemplo"). Solo Nombre y Precio son obligatorios.
3. Lleve el `setup.exe` en una USB.

**En el computador del negocio:**
1. Ejecute el `setup.exe`. Si aparece "Windows protegió su PC": **Más información → Ejecutar de todas formas**.
2. Deje marcadas las tres opciones: acceso directo en el escritorio, abrir al encender el computador y respaldo diario a las 10 p. m. El sistema queda como un ícono verde junto al reloj (si Windows lo esconde en la flecha "^", arrástrelo afuera).
3. Al abrirse, el navegador muestra el asistente: nombre del negocio, nombre del dueño, usuario y contraseña. Anótele al dueño el usuario y la contraseña.
4. **Ajustes:**
   - Datos del tiquete: NIT, dirección, teléfono, mensaje al pie.
   - Impuestos: 19 por defecto; si es restaurante, 8 (impuesto al consumo). Precios con impuesto incluido, salvo que venda a empresas.
   - Métodos de pago: desactive los que no use y agregue los suyos (p. ej. Bancolombia, tipo electrónico).
   - **Respaldos → Carpeta adicional:** la carpeta de OneDrive del computador (p. ej. `C:\Users\<usuario>\OneDrive`) o una USB que se quede conectada. Pulse "Guardar carpeta" y luego **"Respaldar ahora"** para confirmar que funciona.
   - **Licencia** (solo con el módulo encendido): pegue el código y pulse "Activar licencia".
5. **Productos → Importar:** suba la plantilla, revise el resultado (filas con error y por qué) e importe.
6. **Usuarios:** cree un usuario por cajero (rol Cajero) y, si hay encargado, uno con rol Supervisor. Si el dueño quiere otra cosa (p. ej. que el cajero vea reportes), ajústelo en **Permisos por rol**.
   - **Proveedores** (opcional): cree los que le fían mercancía, para registrar las compras a crédito y ver qué facturas vencen.
7. **Impresora térmica:** instale su controlador en Windows y, en **Ajustes → Impresora de tiquetes**, elija "Impresora instalada en este computador" (o "de red" con su IP), el papel, y marque "Imprimir automáticamente" y "Abrir el cajón". Pulse **Imprimir prueba** antes de guardar.
   - Si la impresión directa no funciona con esa impresora, use "Desde el navegador": déjela como **predeterminada** y, en la primera impresión, elija en el diálogo de Chrome o Edge papel de 80 mm, márgenes "Ninguno" y quite "Encabezados y pies de página" (el navegador lo recuerda).
8. **Prueba completa con el dueño:** abrir caja con la base, vender escaneando con el lector, pagar en efectivo con vueltas, imprimir el tiquete, hacer una venta fiada, anular una venta y cerrar la caja. Después del cierre, Ajustes → Respaldos debe mostrar un respaldo nuevo.
9. **Varias cajas en la misma red (opcional):** en `%LOCALAPPDATA%\PuntoDeVenta\.env` cambie `POS_HOST=0.0.0.0`, reinicie el sistema y acepte el aviso del firewall de Windows ("Redes privadas"). Desde los otros equipos entre a `http://IP-DEL-COMPUTADOR:8000`. La base de datos nunca debe estar en una carpeta compartida.

**Antes de irse, explíquele al dueño:**
- El ícono verde junto al reloj es el sistema: "Apagar el punto de venta" lo detiene para todas las cajas. Abre solo al prender el computador.
- Se respalda al cerrar cada caja y en la noche, con copia en OneDrive o en la USB.
- Si algo falla, que le envíe el archivo `%LOCALAPPDATA%\PuntoDeVenta\logs\pos.log`.
- Si olvida la contraseña, soporte la restablece (ver [Soporte](#soporte-problemas-típicos)).
- Lleve un registro de clientes: negocio, plan, fecha de instalación y, si aplica, id y vencimiento de la licencia.

## Referencia de comandos

| Tarea | Comando |
| --- | --- |
| Iniciar en desarrollo | `python manage.py runserver` (con `POS_ENV=development` en `.env`) + `cd frontend && npm run dev` |
| Iniciar como el cliente | `python manage.py start` |
| Iniciar con el ícono del reloj (en desarrollo) | `python manage.py start --tray` |
| Respaldo | `python manage.py backup` (o `PuntoDeVentaConsola.exe backup`) |
| Recuperar una contraseña | `python manage.py reset-password --username dueno` (o `PuntoDeVentaConsola.exe reset-password ...`) |
| Estado / instalar licencia | `python manage.py license [CODIGO]` (o `PuntoDeVentaConsola.exe license ...`) |
| Probar la facturación electrónica | `POS_INVOICE_PROVIDER=simulado` en el `.env` y reiniciar |
| Emitir una licencia (solo el proveedor) | `python packaging/licencia.py emitir --negocio "..." --plan ... --usuarios N --meses 12` |
| Construir el instalador | `python packaging/build.py` (resultado en `dist/`) |
| Publicar versión | `git tag vX.Y.Z && git push origin vX.Y.Z` |

## Dónde está cada cosa en el equipo del cliente

| Qué | Ruta |
| --- | --- |
| Programa | `%LOCALAPPDATA%\Programs\PuntoDeVenta` |
| Configuración (clave secreta, puerto) | `%LOCALAPPDATA%\PuntoDeVenta\.env` |
| Base de datos | `%LOCALAPPDATA%\PuntoDeVenta\data\pos.sqlite3` |
| Respaldos | `%LOCALAPPDATA%\PuntoDeVenta\data\backups` |
| Registro (para soporte) | `%LOCALAPPDATA%\PuntoDeVenta\logs\pos.log` |

## Soporte: problemas típicos

| Síntoma | Qué hacer |
| --- | --- |
| "El puerto 8000 está ocupado" | Otro programa usa el puerto. Cambiar `POS_PORT=8001` en el `.env` de datos. |
| Olvidó la contraseña | En el computador del negocio, abrir una consola en la carpeta del programa (`%LOCALAPPDATA%\Programs\PuntoDeVenta`) y ejecutar `PuntoDeVentaConsola.exe reset-password --username dueno`. Si no sabe el usuario, ejecútelo con cualquier nombre: el error lista los administradores. Si el usuario estaba inactivo, lo reactiva. Si quedó bloqueado por intentos fallidos, reinicie el sistema. No hay acceso directo en el menú a propósito: no debe quedar a la mano de los empleados. |
| La licencia no aparece o venció | Ajustes → Licencia muestra el estado. Envíele un código nuevo, o instálelo con `PuntoDeVentaConsola.exe license CODIGO`. Sin código muestra el estado. |
| No imprime (impresión directa) | Ajustes → Impresora de tiquetes → Imprimir prueba: el mensaje dice si no encuentra la impresora o no responde por la red. Revise que esté encendida, con papel y, si es de red, que la IP no haya cambiado (déjela fija en el router). Mientras tanto, cambie a "Desde el navegador". |
| Aviso rojo de facturación electrónica | Ajustes → Facturación electrónica muestra el motivo de cada documento rechazado. Corrija el dato (p. ej. el NIT del negocio) y pulse Reintentar. |
| No aparece el ícono del reloj | Windows a veces lo esconde en la flecha "^" junto al reloj; arrástrelo afuera para dejarlo siempre visible. |
| Restaurar un respaldo | Cerrar el sistema, renombrar `data\pos.sqlite3` y copiar el respaldo elegido con ese nombre. |
| Algo falla y no se sabe qué | Pedir el archivo `logs\pos.log`. |
| Pasar a un computador nuevo | Instalar en el nuevo y copiar la carpeta `%LOCALAPPDATA%\PuntoDeVenta` completa (incluye el `.env` con la clave secreta). |

---
