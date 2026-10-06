# Hoja de ruta del Punto de Venta

Documento de trabajo para retomar el proyecto. Estado al **6 de octubre de 2026**, versión **0.2.0**.

---

## 1. Dónde quedamos

### Lo que ya funciona

| Área | Estado |
| --- | --- |
| Backend (Python + Flask + SQLite) | Ventas, caja con arqueo, inventario con kárdex, clientes con fiado, usuarios con roles, reportes. Arquitectura limpia, SOLID. |
| Interfaz web (React + TypeScript) | Vender (lector de código de barras, pago mixto, vueltas, fiado, tiquete de 80 mm), caja, ventas, productos, clientes, reportes, usuarios, ajustes. |
| Primera vez | Asistente en el navegador: nombre del negocio y administrador, sin consola. |
| Instalador Windows | `setup.exe` y `.zip` con PyInstaller + Inno Setup. El cliente no necesita Python. Probado: instalar, usar, respaldar, desinstalar sin perder datos. |
| Robustez | Ventas idempotentes (un reintento no duplica), consultas que no bloquean las ventas, límite de intentos de login, reportes calculados en SQL, respaldos verificados. |
| Calidad | 137 pruebas de backend + 20 de frontend. GitHub Actions las corre en Windows y Linux. |

### Cambios sin publicar (irán en la versión 0.3.0)

Hechos el 6 de octubre de 2026. Ya tienen commit, pero **no se han subido a GitHub** (sección 11).

| Cambio | Detalle |
| --- | --- |
| Licencias firmadas (3.1) | El límite de usuarios ya no se puede cambiar por la API: sale de una licencia firmada con Ed25519. Prueba de 30 días; vencida, el negocio sigue vendiendo pero no puede crear usuarios. Pantalla en Ajustes → Licencia y aviso para el administrador. |
| Recuperar contraseña | `PuntoDeVenta.exe reset-password --username dueno` desde la consola del equipo del negocio. |
| Respaldos (3.3) | Respaldo automático al cerrar cada caja; copia adicional a una USB, OneDrive o Google Drive (Ajustes → Respaldos); botón "Respaldar ahora" y lista de los últimos respaldos. Si la USB no está conectada, el respaldo principal se hace igual. |
| Importar productos (mejora #6) | Productos → Importar: Excel (.xlsx) o CSV, con plantilla de ejemplo. Entiende encabezados en español con o sin tildes ("Código", "Precio de venta", "Existencias"...) y números como los escribe la gente ("$2.500", "2.500,50"). Primero muestra una revisión (nuevos, actualizados, filas con error y por qué) sin guardar nada; luego importa las filas válidas en una sola transacción. Puede actualizar precios de productos existentes. |
| Exportar a Excel (mejora #7) | Productos → Exportar (mismo formato que la importación: exportar, cambiar precios en Excel y volver a importar). Reportes → Exportar: resumen, ventas por día, cada venta con base, impuestos y pagos, y productos vendidos. Archivos .xlsx reales (no CSV), así que Excel en español muestra bien los números. |
| Rol Supervisor (mejora #5, versión corta) | Encargado de turno: vende, anula ventas, da descuentos, cierra cajas de otros, registra entradas de mercancía y ve reportes. No cambia precios, usuarios ni ajustes. |
| Arranque con Windows (mejora #3) | Nueva opción en el instalador: abre el sistema (minimizado y sin abrir el navegador) al iniciar sesión en Windows. |
| Revisión visual | Se recorrieron todas las pantallas en un navegador real (Chromium), en computador y en celular, incluida una venta completa con tiquete y el cierre de caja. Se corrigieron: los botones "Mi contraseña" y "Salir" se veían en blanco (texto blanco sobre fondo blanco), las fechas de Reportes y Ventas ocupaban todo el ancho, y "Cancelar venta" usaba el cuadro gris del navegador (ahora es un diálogo del sistema). |
| Pruebas con Node 25+ | Node 25 trae un `localStorage` propio que tapaba el del navegador simulado y hacía fallar 5 pruebas. Arreglado con `frontend/src/test-setup.ts`. |

### Historial de commits (todos a nombre de S4ntyx)

```
abbdc9b Empaqueta el sistema como ejecutable de Windows con instalador
a43df23 Agrega asistente de configuracion inicial y el comando start
ad938b7 Actualiza el README con la interfaz, la instalacion y la arquitectura
ae7d2a8 Agrega instaladores para Windows e integracion continua
96f2bbf Agrega la interfaz web para cajeros y administradores
daebecb Agrega instalacion en un paso y respaldos de la base de datos
8070bc9 Calcula los reportes en la base de datos (modelo de lectura)
a86c6b3 Limita los intentos fallidos de inicio de sesion
b270002 Evita ventas duplicadas cuando la caja reintenta
3284839 Usa transacciones de solo lectura en las consultas
09fc913 Mueve required_text al nucleo compartido del dominio
79f3e73 Corrige avisos de ruff y normaliza finales de linea
e7332a8 Agrega el backend del POS: dominio, casos de uso, SQLite y API HTTP
```

---

## 2. Pendiente inmediato (esta semana)

Cosas cortas que quedaron sin hacer o sin verificar.

- [ ] **Subir los commits a GitHub.** Nada se ha subido todavía. El paso a paso completo para generar y probar el instalador desde Linux está en la sección 12.
  ```bash
  git push origin main
  ```
- [ ] **Revisar que el CI pase en GitHub** (pestaña *Actions*, flujo "CI"). Nunca se ha ejecutado allá.
- [ ] **Publicar la primera versión** y comprobar que GitHub genera el `setup.exe`:
  ```bash
  git tag v0.2.0 && git push origin v0.2.0
  ```
  Revise el flujo "Versión para Windows". Si falla, el registro dice en qué paso.
- [x] ~~Revisar la interfaz en un navegador.~~ Hecho con Chromium (ver "Cambios sin publicar"). Igual conviene que usted la recorra en el computador de un cliente con Windows, con la pantalla y la resolución reales.
- [ ] **Imprimir un tiquete real** en una impresora térmica de 80 mm. El diseño no se ha probado en papel.
- [ ] **Probar el instalador en un computador limpio** (otro PC, o una máquina virtual con Windows 10/11 recién instalado). Solo se ha probado en el equipo de desarrollo.
- [ ] **Probar con un lector de código de barras real.** El lector "escribe" el código y presiona Enter; así está programado, pero no se ha probado con hardware.
- [ ] **Confirmar el correo de git.** Los commits usan `wsantyx@gmail.com`. Si ese correo no está agregado a la cuenta de GitHub `santyxswc`, los commits aparecen sin su foto. Se agrega en GitHub → *Settings → Emails*.

---

## 3. Antes de vender: lo que falta (en orden de prioridad)

### 3.1 Proteger el plan que vende (licencias) — ✅ **hecho** (falta la versión publicada)

**Cómo quedó:**
- `domain/licensing.py` tiene **todas las reglas comerciales** en constantes: `TRIAL_DAYS = 30`, `TRIAL_MAX_USERS = 3`, `EXPIRED_MAX_USERS = 1`, `WARN_DAYS_BEFORE_EXPIRY = 15`. Cámbielas ahí si quiere otra política.
- Sin licencia: prueba completa por 30 días desde la instalación. Las instalaciones que ya existían reciben sus 30 días la primera vez que abran la versión nueva: **instale la licencia de sus clientes actuales dentro de ese plazo**.
- Licencia o prueba vencida: **el negocio sigue vendiendo** (nunca se detiene una caja ni se secuestran datos), pero no se pueden crear ni reactivar usuarios por encima de 1, y el administrador ve un aviso rojo arriba de cada pantalla.
- El código es texto corto (`POS1.xxxx.yyyy`) que se envía por WhatsApp o correo. El cliente lo pega en **Ajustes → Licencia**, o soporte lo instala con `PuntoDeVenta.exe license CODIGO`. Si el chat parte el código en varias líneas, igual funciona.
- `max_users` dejó de existir en los ajustes: `PATCH /api/v1/settings` con `max_users` responde 400.

**Su clave privada:** está **solo en su USB** (la de Ventoy), en `punto-de-venta-licencias/clave-licencias.pem`. Se movió allí el 6 de octubre de 2026 y se comprobó que corresponde a la clave pública del programa (`src/pos/infrastructure/license_key.py`). Ya no hay copia en el computador.
- [x] ~~Guardar la clave privada en una USB.~~
- [ ] **Haga una segunda copia** en otro lugar seguro (otra USB guardada aparte, o un gestor de contraseñas que acepte archivos). Hoy existe una sola copia: si esa USB se daña, se pierde o se reformatea (Ventoy reformatea la USB al reinstalarse), no podrá emitir licencias que acepten las instalaciones existentes.
- [ ] Opcional: protéjala con contraseña antes de vender la primera licencia (`POS_LICENSE_PASSPHRASE=... python packaging/licencia.py claves --reemplazar`); después, reemplazarla invalida las licencias emitidas.

**Emitir una licencia** (con la USB conectada; `--clave` indica dónde está, o defina `POS_LICENSE_KEY` con esa ruta):
```bash
export POS_LICENSE_KEY=/run/media/yefersoncaicedo/Ventoy/punto-de-venta-licencias/clave-licencias.pem
python packaging/licencia.py emitir --negocio "Tienda Doña Rosa" --plan Mediano --usuarios 3 --meses 12
python packaging/licencia.py emitir --negocio "Minimercado X" --plan Ilimitado --usuarios 0     # sin límite y sin vencimiento
python packaging/licencia.py ver POS1....                                                        # revisar un código
```
Lleve un registro (hoja de cálculo) con negocio, id de la licencia, plan y vencimiento: el programa no lo hace por usted.

**Limitaciones conocidas (para más adelante):**
- La licencia no está atada al computador: un cliente podría copiar su código a otro negocio. El código lleva el nombre del negocio y se muestra en Ajustes, lo que desanima el abuso. Si llega a pasar, la solución es atarla a un identificador del equipo o activarla en línea.
- Quien sepa editar la base de datos SQLite puede cambiar la fecha de instalación y alargar la prueba. Aceptable: el plan pago es la licencia firmada, que no se puede falsificar.
- El límite se aplica al crear o reactivar usuarios; los usuarios que ya estaban activos siguen funcionando.

<details><summary>Planteamiento original</summary>


**Problema:** el límite de usuarios (`max_users`) es un ajuste más, y el administrador del cliente lo puede cambiar con `PATCH /api/v1/settings`. No se muestra en la interfaz, pero cualquiera que sepa usar la API se sube el plan gratis. Lo mismo pasaría con cualquier función que quiera cobrar aparte.

**Solución sugerida:** un **archivo de licencia firmado por usted**.
- Usted genera un par de claves (Ed25519). La clave privada **nunca** sale de su computador; la pública va dentro del programa.
- La licencia es un pequeño JSON firmado: `{"negocio": "...", "plan": "mediano", "max_usuarios": 3, "vence": "2027-10-06"}`.
- El sistema verifica la firma al arrancar. Sin licencia válida, funciona en modo prueba (por ejemplo 15 días o 1 usuario).
- `max_users` deja de ser editable por la API y pasa a salir de la licencia.

Dónde encaja en la arquitectura: un puerto `LicenseProvider` en `application/ports.py`, una implementación en `infrastructure/licensing.py` y un comando `python packaging/licencia.py --negocio ... --plan ...` que solo usted tiene.

</details>

### 3.2 Facturación electrónica (DIAN) — **consulte a un contador antes**

En Colombia la DIAN exige el **documento equivalente electrónico** para el tiquete POS (Resolución 000165 de 2023, con entrada gradual). Según el tipo de negocio de su cliente, vender sin esto puede no estar permitido. **Verifique con un contador** qué aplica a sus clientes objetivo antes de venderles.

Cómo se integraría (el sistema ya está preparado):
1. Elegir un **proveedor tecnológico autorizado** por la DIAN que tenga API (no se le habla directamente a la DIAN).
2. Crear `infrastructure/invoicing_<proveedor>.py` con el método `issue_for_sale(sale_id)` y pasarlo a `build_container` como `invoice_provider`.
3. **Agregar una bandeja de salida (patrón *outbox*)**. Hoy, si el envío falla, solo queda en el registro y **no se reintenta**. Se necesita:
   - una tabla `invoice_outbox` que se llena dentro de la misma transacción de la venta;
   - un proceso que reintenta los pendientes cada cierto tiempo;
   - una pantalla con los documentos pendientes o rechazados.
4. Mostrar el CUFE o código QR en el tiquete cuando el proveedor lo devuelva.

### 3.3 Que el cliente no pierda sus datos — ✅ **mejorado** (falta la nube)

- [x] **Respaldo al cerrar la caja.** Cada cierre deja un respaldo, aunque apaguen el computador antes de las 10 p. m. Si el respaldo falla, el cierre de caja no se ve afectado (queda en el registro).
- [x] **Carpeta adicional** en Ajustes → Respaldos: una USB (`E:\`) o la carpeta de OneDrive o Google Drive de escritorio. Se guarda en una subcarpeta `Respaldos Punto de Venta` y conserva los últimos 30. Al guardarla se comprueba que exista y que se pueda escribir. Si el día del respaldo la USB no está, el respaldo principal se hace igual y el sistema avisa.
- [x] **"Respaldar ahora"** y lista de los últimos respaldos (fecha, archivo, tamaño) en Ajustes.
- [x] La tarea programada de la noche ahora deja constancia en `logs\pos.log` y también copia a la carpeta adicional.
- [ ] **Al instalar donde un cliente, configure la carpeta adicional** (OneDrive es lo más práctico: queda en la nube sin que nadie se acuerde).
- [ ] **Ideal (servicio que puede cobrar):** respaldo automático a la nube, en un bucket suyo, cifrado. Encaja como otra implementación de `BackupService` (`application/ports.py`) o como un paso extra después del respaldo local.
- [ ] Restaurar un respaldo desde la interfaz. Hoy es manual (ver Soporte, sección 8): a propósito, porque restaurar mal borra ventas.

### 3.4 Firma digital del instalador

Sin firma, Windows muestra "Windows protegió su PC" y el cliente debe pulsar *Más información → Ejecutar de todas formas*. Esto genera desconfianza en clientes no técnicos.
- Requiere un certificado de firma de código (costo anual). Los certificados OV son más baratos; los EV quitan el aviso de inmediato.
- Se firma después de PyInstaller y después de Inno Setup, con `signtool`. Agregar ese paso en `packaging/build.py` y en GitHub Actions, con el certificado guardado como *secret*.

### 3.5 Prueba piloto con un negocio real

Antes de vender a varios clientes, instale el sistema **gratis o con descuento en 1 o 2 negocios conocidos** durante 2 a 4 semanas.
- Esté presente el primer día (apertura, ventas, cierre).
- Anote cada duda o queja del cajero: eso guía las mejoras de usabilidad.
- Mida: ventas por hora, errores de cierre de caja, preguntas frecuentes.

---

## 4. Mejoras después del lanzamiento

Ordenadas por impacto para el cliente.

| # | Mejora | Por qué | Esfuerzo |
| --- | --- | --- | --- |
| 1 | **Impresión directa ESC/POS** | Hoy imprime con el diálogo del navegador (un clic extra por venta). Abrir el cajón monedero también requiere ESC/POS. | Medio |
| 2 | **Ícono junto al reloj de Windows** (pendiente; no se puede probar sin Windows) | Quitar la ventana negra; menú con "Abrir", "Respaldar ahora" y "Salir". Librería `pystray`. | Bajo |
| 3 | ✅ ~~Arranque automático con Windows~~ (opción del instalador) | Que el sistema esté listo al encender. Opción en el instalador (carpeta *Inicio*). | Bajo |
| 4 | **Actualización automática** | Avisar en la interfaz cuando haya una versión nueva en GitHub Releases. | Medio |
| 5 | **Permisos por rol desde Ajustes** (✅ se agregó el rol Supervisor; falta poder editarlos) | Hoy se cambian en código (`ROLE_PERMISSIONS` en `domain/users.py`). Algunos clientes querrán un rol "supervisor". | Medio |
| 6 | ✅ ~~Importar productos desde Excel/CSV~~ | Cargar 500 productos a mano es la mayor barrera del primer día. | Bajo |
| 7 | ✅ ~~Exportar reportes a Excel~~ | Lo piden los contadores. | Bajo |
| 8 | **Proveedores y cuentas por pagar** | Completa el inventario: compras a crédito a proveedores. | Medio |
| 9 | **Modo restaurante** | Mesas, comandas a cocina, división de cuentas. Sería otro plan para cobrar. | Alto |
| 10 | **Varias sedes / nube (PostgreSQL)** | Para cadenas pequeñas. Implementar los puertos de `application/ports.py` en `infrastructure/persistence/postgres/`. Requiere además separar los datos por negocio (*multi-tenant*). | Alto |

---

## 5. Limitaciones conocidas y riesgos técnicos

Cosas que funcionan, pero que conviene tener presentes.

| Tema | Detalle | Cuándo atenderlo |
| --- | --- | --- |
| Red local sin HTTPS | Con `POS_HOST=0.0.0.0` otros equipos se conectan por HTTP sin cifrar. En la red de la tienda es aceptable; por Wi‑Fi abierto o internet, no. | Antes de ofrecer acceso remoto |
| Sesión en `localStorage` | El token de sesión se guarda en el navegador. Es estándar en aplicaciones locales; si algún día hay acceso público por internet, migrar a cookies `HttpOnly`. | Con la versión en la nube |
| Freno de login en memoria | El conteo de intentos fallidos se pierde al reiniciar y no se comparte entre servidores. Correcto para un servidor por negocio. | Con varios servidores |
| SQLite | Excelente para 1 a 5 cajas en un mismo local. Para más carga o varias sedes, PostgreSQL. **Nunca** poner la base de datos en una carpeta compartida de red: los demás equipos deben entrar por el navegador. | Con varias sedes |
| Ventana negra | Cerrarla apaga el sistema. Explíquelo al cliente o implemente la mejora #2. | Pronto |
| Respaldo nocturno | Muestra una ventana de consola un instante a las 10 p. m. | Junto con la mejora #2 |
| Python 3.14 en desarrollo | El proyecto exige 3.11+ y el CI prueba 3.11 y 3.13. Si usa algo propio de 3.14, el CI lo detecta. | — |
| Aviso de npm `allow-scripts` | npm 11 bloquea el script de instalación de `esbuild`; la compilación funciona igual. Si algún día falla: `npm approve-scripts esbuild`. | Si aparece un error |
| `.venv` local | La carpeta `.venv` del proyecto se creó para las pruebas. Está ignorada por git. | — |
| Excel antiguo (.xls) | La importación lee .xlsx y .csv, no el formato de Excel 97-2003. El mensaje de error le pide al usuario guardarlo como .xlsx. | Si un cliente lo pide |
| Números en CSV | En un CSV, "12.345" se lee como doce mil trescientos cuarenta y cinco (punto de miles, como se escribe en Colombia). Para kilos con decimales use coma ("12,345") o un archivo .xlsx, donde los números no son ambiguos. | — |

---

## 6. Reglas para no romper nada

1. **Nunca edite una migración ya publicada** (`infrastructure/persistence/sqlite/migrations.py`). Agregue una nueva al final de la lista. Las bases de datos de los clientes se actualizan solas al abrir el programa.
2. **Nunca cambie el `AppId`** de `packaging/instalador.iss`. Si lo cambia, las actualizaciones se instalan como un programa distinto.
3. **Para subir la versión**, cámbiela en los tres lugares: `src/pos/__init__.py`, `pyproject.toml` y `frontend/package.json`. La etiqueta debe coincidir (`v0.3.0`); si no, el build de GitHub falla a propósito.
4. **El dinero nunca va en `float`.** Backend: `Money` y `Decimal`. Frontend: centavos enteros (`money.ts`). La API recibe y envía texto (`"12500.00"`).
5. **Los permisos se revisan en los casos de uso**, no en las rutas ni en la interfaz. Ocultar un botón no es seguridad.
6. **El historial no se edita:** kárdex, movimientos de caja y estado de cuenta solo se agregan. Las correcciones son movimientos nuevos (ajuste o anulación).
7. **Antes de cada commit:**
   ```bash
   .venv\Scripts\python -m ruff check .
   .venv\Scripts\python -m pytest -q
   cd frontend && npm test && npx tsc --noEmit
   ```

---

## 7. Cómo extender el sistema (recetas)

| Quiero... | Pasos |
| --- | --- |
| **Una pantalla nueva** | Crear `frontend/src/pages/MiPantalla.tsx` y agregar una entrada a `ROUTES` en `frontend/src/App.tsx` (con su permiso). El menú se arma solo. |
| **Un caso de uso nuevo** | Clase con `execute()` en `application/use_cases/<módulo>.py` → registrarla en `Container` y `build_container` (`bootstrap.py`) → ruta en `presentation/http/routes/` → prueba en `tests/`. |
| **Un dato nuevo en una tabla** | Nueva migración al final de `MIGRATIONS` → actualizar el repositorio (`repositories.py`) → el campo en la entidad del dominio → prueba de migración sobre una base existente (ver `tests/integration/test_migrations.py`). |
| **Un método de pago nuevo** (Bancolombia, Bre‑B...) | No requiere código: Ajustes → Métodos de pago → Agregar, tipo "Electrónico". |
| **Un tipo de pago con comportamiento nuevo** (bonos, puntos) | Nuevo valor en `PaymentKind` y su `PaymentBehavior` en `domain/payments.py`. Ventas y caja no cambian. |
| **Reaccionar a algo** (avisar por WhatsApp cuando falte stock) | Manejador para el evento (`StockLow`, `SaleCompleted`, `CashSessionClosed`) y `bus.subscribe(...)` en `bootstrap.py`. |
| **Otra base de datos** | Implementar los repositorios, `SalesReportQueries` y `UnitOfWork` de `application/ports.py`; cambiar la fábrica `uow` en `bootstrap.py`. |
| **Cambiar la política de licencias** (días de prueba, usuarios al vencer) | Constantes al inicio de `domain/licensing.py`. Las pruebas de `tests/unit/test_licensing.py` dicen qué se espera. |
| **Cobrar aparte por una función** (p. ej. módulo de restaurante) | Agregar el dato a la licencia (`License` y `_payload` en `infrastructure/licensing.py`), y preguntar a `LicensePolicy` en el caso de uso de esa función. |
| **Otra columna en la importación de productos** | Agregarla a `PRODUCT_COLUMNS` (`presentation/http/workbooks.py`) y leerla en `catalog_import.py`. |
| **Otro destino de respaldo** (nube) | Implementar `BackupService` (`application/ports.py`) o envolver `SqliteBackupService` para subir el archivo después de crearlo. |
| **Un rol nuevo** | Valor nuevo en `Role` y su entrada en `ROLE_PERMISSIONS` (`domain/users.py`); en el frontend, `ROLE_LABEL` (`types.ts`) y la opción en `Users.tsx`. |

---

## 8. Referencia rápida

### Comandos

| Tarea | Comando |
| --- | --- |
| Iniciar en desarrollo | `python manage.py runserver` (con `POS_ENV=development` en `.env`) + `cd frontend && npm run dev` |
| Iniciar como el cliente | `python manage.py start` |
| Respaldo | `python manage.py backup` (o `PuntoDeVenta.exe backup`) |
| Recuperar una contraseña | `python manage.py reset-password --username dueno` (o `PuntoDeVenta.exe reset-password ...`) |
| Estado / instalar licencia | `python manage.py license [CODIGO]` |
| Emitir una licencia (solo usted) | `python packaging/licencia.py emitir --negocio "..." --plan ... --usuarios N --meses 12` |
| Construir el instalador | `python packaging/build.py` (resultado en `dist/`) |
| Publicar versión | `git tag vX.Y.Z && git push origin vX.Y.Z` |

### Dónde está cada cosa en el equipo del cliente

| Qué | Ruta |
| --- | --- |
| Programa | `%LOCALAPPDATA%\Programs\PuntoDeVenta` |
| Configuración (clave secreta, puerto) | `%LOCALAPPDATA%\PuntoDeVenta\.env` |
| Base de datos | `%LOCALAPPDATA%\PuntoDeVenta\data\pos.sqlite3` |
| Respaldos | `%LOCALAPPDATA%\PuntoDeVenta\data\backups` |
| Registro (para soporte) | `%LOCALAPPDATA%\PuntoDeVenta\logs\pos.log` |

### Soporte: problemas típicos

| Síntoma | Qué hacer |
| --- | --- |
| "El puerto 8000 está ocupado" | Otro programa usa el puerto. Cambiar `POS_PORT=8001` en el `.env` de datos. |
| Olvidó la contraseña | En el computador del negocio, abrir una consola en la carpeta del programa (`%LOCALAPPDATA%\Programs\PuntoDeVenta`) y ejecutar `PuntoDeVenta.exe reset-password --username dueno`. Si no sabe el usuario, ejecútelo con cualquier nombre: el error lista los administradores. Si el usuario estaba inactivo, lo reactiva. Si quedó bloqueado por intentos fallidos, reinicie el sistema. No hay acceso directo en el menú a propósito: no debe quedar a la mano de los empleados. |
| La licencia no aparece o venció | Ajustes → Licencia muestra el estado. Envíele un código nuevo, o instálelo con `PuntoDeVenta.exe license CODIGO`. `PuntoDeVenta.exe license` sin código muestra el estado. |
| Restaurar un respaldo | Cerrar el sistema, renombrar `data\pos.sqlite3` y copiar el respaldo elegido con ese nombre. |
| Algo falla y no se sabe qué | Pedir el archivo `logs\pos.log`. |
| Pasar a un computador nuevo | Instalar en el nuevo y copiar la carpeta `%LOCALAPPDATA%\PuntoDeVenta` completa (incluye el `.env` con la clave secreta). |

---

## 9. Asuntos de negocio (no técnicos)

- **Planes y precios.** El código ya distingue el límite de usuarios. Defina qué incluye cada plan (Básico, Mediano...) y cobre por instalación + mensualidad de soporte y respaldo en la nube. La licencia del punto 3.1 es lo que hace cumplir esos planes.
- **Contrato y soporte.** Defina por escrito qué incluye el soporte (horario, tiempo de respuesta, visitas) y quién es responsable de los respaldos.
- **Protección de datos (Ley 1581 de 2012, Habeas Data).** El sistema guarda nombre, cédula y teléfono de los clientes del negocio. Su cliente es el responsable de esos datos; usted, como proveedor, debería tener una política de tratamiento de datos, sobre todo si ofrece respaldo en la nube. Consúltelo con un abogado.
- **Facturación electrónica.** Ver el punto 3.2: es probablemente lo primero que preguntará un cliente formal.
- **Material para el cliente.** Una guía de una página con fotos (abrir caja, vender, cerrar caja) reduce mucho las llamadas de soporte.

---

## 10. Orden recomendado para continuar

1. Pendientes inmediatos (sección 2): push, CI, primera versión, revisión visual, impresora y lector.
2. ~~Comando para recuperar la contraseña del administrador~~ ✅
3. ~~Licencias (3.1)~~ ✅ — la clave privada está en la USB; falta una segunda copia.
4. ~~Respaldo adicional en USB o nube y respaldo al cerrar la caja (3.3)~~ ✅ (la nube sigue pendiente).
5. **Prueba piloto** en 1 o 2 negocios (3.5). La importación de productos (#6) ya está; el ícono junto al reloj (#2) sigue pendiente.
6. Firma digital (3.4) cuando empiece a vender en serie.
7. Facturación electrónica (3.2), según lo que diga el contador.
8. Lo demás de la sección 4, guiado por lo que pidan los clientes del piloto.

---

## 11. Commits de este trabajo

Los cambios del 6 de octubre quedaron en dos commits:

1. `Corrige las pruebas del frontend con Node 25 o superior`
2. `Agrega licencias, respaldos fuera del equipo, importacion y exportacion de Excel y rol supervisor`

Todavía **no se han subido** a GitHub (`git push origin main`, ver sección 12). La copia de esta hoja de ruta que había en la raíz del proyecto se borró: la única es `docs/HOJA_DE_RUTA.md`.

---

## 12. Paso a paso: del código al computador del cliente

### A. Generar el instalador (desde Linux, sin Windows)

El `setup.exe` se construye en GitHub, en una máquina Windows de GitHub Actions:

1. Suba los commits: `git push origin main`.
2. En GitHub, pestaña **Actions** → revise que el flujo **CI** termine en verde.
3. En **Actions → "Versión para Windows" → Run workflow** (rama `main`). Tarda unos 10 minutos.
4. Al terminar, abra esa ejecución y descargue el artefacto: trae `PuntoDeVenta-<versión>-setup.exe` y el `.zip`.
5. Cuando todo esté probado, publique la versión: suba el número a `0.3.0` en `src/pos/__init__.py`, `pyproject.toml` y `frontend/package.json`, haga commit y luego `git tag v0.3.0 && git push origin main v0.3.0`. GitHub crea el *Release* con el instalador.

### B. Probar el instalador en una máquina virtual (en su Linux)

Tiene `virt-manager` instalado y la ISO de Windows 11 en la USB de Ventoy.

1. Instale el emulador de TPM que pide Windows 11: `sudo pacman -S swtpm` (y que el servicio `libvirtd` esté activo).
2. En virt-manager: **Nueva máquina → ISO** `Win11_25H2_Spanish_Mexico_x64_v2.iso`, 4 GB de RAM, 2 CPU, 64 GB de disco. Marque **"Personalizar antes de instalar"**: firmware **UEFI** (con arranque seguro) y agregue un **TPM** emulado, versión 2.0.
3. Instale Windows (para probar no hace falta activarlo). Dentro de la máquina virtual, entre a GitHub y descargue el artefacto del paso A.4.
4. Recorra la sección C como si fuera el cliente. Verifique en especial: el aviso "Windows protegió su PC", las tres opciones del instalador, que el sistema abra solo al reiniciar Windows, el respaldo de las 10 p. m. (o ejecute la tarea a mano en el *Programador de tareas*), y que desinstalar y volver a instalar conserve los datos.

### C. Instalación donde el cliente

**Antes de ir:**
1. Emita la licencia con la USB conectada (sección 3.1), con el nombre del negocio tal como debe salir, y guarde el código en un mensaje para pegarlo.
2. Pida la lista de productos y pásela a la plantilla (Productos → Importar → "Descargar plantilla de ejemplo"). Solo Nombre y Precio son obligatorios.
3. Lleve el `setup.exe` en una USB.

**En el computador del negocio:**
1. Ejecute el `setup.exe`. Si aparece "Windows protegió su PC": **Más información → Ejecutar de todas formas**.
2. Deje marcadas las tres opciones: acceso directo en el escritorio, abrir al encender el computador y respaldo diario a las 10 p. m.
3. Al abrirse, el navegador muestra el asistente: nombre del negocio, nombre del dueño, usuario y contraseña. Anótele al dueño el usuario y la contraseña.
4. **Ajustes:**
   - Datos del tiquete: NIT, dirección, teléfono, mensaje al pie.
   - Impuestos: 19 por defecto; si es restaurante, 8 (impuesto al consumo). Precios con impuesto incluido, salvo que venda a empresas.
   - Métodos de pago: desactive los que no use y agregue los suyos (p. ej. Bancolombia, tipo electrónico).
   - **Respaldos → Carpeta adicional:** la carpeta de OneDrive del computador (p. ej. `C:\Users\<usuario>\OneDrive`) o una USB que se quede conectada. Pulse "Guardar carpeta" y luego **"Respaldar ahora"** para confirmar que funciona.
   - **Licencia:** pegue el código y pulse "Activar licencia".
5. **Productos → Importar:** suba la plantilla, revise el resultado (filas con error y por qué) e importe.
6. **Usuarios:** cree un usuario por cajero (rol Cajero) y, si hay encargado, uno con rol Supervisor.
7. **Impresora térmica:** instale su controlador en Windows, déjela como **predeterminada** y, en la primera impresión del tiquete, elija en el diálogo de Chrome o Edge papel de 80 mm, márgenes "Ninguno" y quite "Encabezados y pies de página" (el navegador lo recuerda).
   - Opcional, para imprimir sin el diálogo: cree un acceso directo de Chrome con `--kiosk-printing --app=http://127.0.0.1:8000`.
8. **Prueba completa con el dueño:** abrir caja con la base, vender escaneando con el lector, pagar en efectivo con vueltas, imprimir el tiquete, hacer una venta fiada, anular una venta y cerrar la caja. Después del cierre, Ajustes → Respaldos debe mostrar un respaldo nuevo.
9. **Varias cajas en la misma red (opcional):** en `%LOCALAPPDATA%\PuntoDeVenta\.env` cambie `POS_HOST=0.0.0.0`, reinicie el sistema y acepte el aviso del firewall de Windows ("Redes privadas"). Desde los otros equipos entre a `http://IP-DEL-COMPUTADOR:8000`. La base de datos nunca debe estar en una carpeta compartida.

**Antes de irse, explíquele al dueño:**
- La ventana negra es el sistema: si la cierra, se apaga. Abre solo al prender el computador.
- Se respalda al cerrar cada caja y en la noche, con copia en OneDrive o en la USB.
- Si algo falla, que le envíe el archivo `%LOCALAPPDATA%\PuntoDeVenta\logs\pos.log`.
- Si olvida la contraseña: usted la restablece (sección 8, Soporte).
- Anote en su registro de clientes: negocio, id de la licencia, plan, vencimiento y fecha de instalación.
