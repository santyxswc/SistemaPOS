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
| Calidad | 95 pruebas de backend + 18 de frontend. GitHub Actions las corre en Windows y Linux. |

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

- [ ] **Subir los commits a GitHub.** Nada se ha subido todavía.
  ```bash
  git push origin main
  ```
- [ ] **Revisar que el CI pase en GitHub** (pestaña *Actions*, flujo "CI"). Nunca se ha ejecutado allá.
- [ ] **Publicar la primera versión** y comprobar que GitHub genera el `setup.exe`:
  ```bash
  git tag v0.2.0 && git push origin v0.2.0
  ```
  Revise el flujo "Versión para Windows". Si falla, el registro dice en qué paso.
- [ ] **Revisar la interfaz con sus propios ojos.** No se pudo ver en un navegador durante el desarrollo: se verificó con pruebas automáticas y llamadas a la API, pero no visualmente. Recorra todas las pantallas y anote lo que se vea mal.
- [ ] **Imprimir un tiquete real** en una impresora térmica de 80 mm. El diseño no se ha probado en papel.
- [ ] **Probar el instalador en un computador limpio** (otro PC, o una máquina virtual con Windows 10/11 recién instalado). Solo se ha probado en el equipo de desarrollo.
- [ ] **Probar con un lector de código de barras real.** El lector "escribe" el código y presiona Enter; así está programado, pero no se ha probado con hardware.
- [ ] **Confirmar el correo de git.** Los commits usan `wsantyx@gmail.com`. Si ese correo no está agregado a la cuenta de GitHub `santyxswc`, los commits aparecen sin su foto. Se agrega en GitHub → *Settings → Emails*.

---

## 3. Antes de vender: lo que falta (en orden de prioridad)

### 3.1 Proteger el plan que vende (licencias) — **importante**

**Problema:** el límite de usuarios (`max_users`) es un ajuste más, y el administrador del cliente lo puede cambiar con `PATCH /api/v1/settings`. No se muestra en la interfaz, pero cualquiera que sepa usar la API se sube el plan gratis. Lo mismo pasaría con cualquier función que quiera cobrar aparte.

**Solución sugerida:** un **archivo de licencia firmado por usted**.
- Usted genera un par de claves (Ed25519). La clave privada **nunca** sale de su computador; la pública va dentro del programa.
- La licencia es un pequeño JSON firmado: `{"negocio": "...", "plan": "mediano", "max_usuarios": 3, "vence": "2027-10-06"}`.
- El sistema verifica la firma al arrancar. Sin licencia válida, funciona en modo prueba (por ejemplo 15 días o 1 usuario).
- `max_users` deja de ser editable por la API y pasa a salir de la licencia.

Dónde encaja en la arquitectura: un puerto `LicenseProvider` en `application/ports.py`, una implementación en `infrastructure/licensing.py` y un comando `python packaging/licencia.py --negocio ... --plan ...` que solo usted tiene.

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

### 3.3 Que el cliente no pierda sus datos

- Hoy el respaldo diario se guarda **en el mismo disco**. Si el disco se daña o le roban el computador, se pierde todo, incluido el respaldo.
- **Mínimo:** explicar a cada cliente que copie `%LOCALAPPDATA%\PuntoDeVenta\data\backups` a una USB cada semana.
- **Mejor:** agregar una opción en Ajustes para elegir una carpeta de respaldo adicional (USB, OneDrive o Google Drive de escritorio).
- **Ideal (servicio que puede cobrar):** respaldo automático a la nube, en un bucket suyo, cifrado.
- La tarea programada solo corre si el usuario de Windows tiene la sesión iniciada a las 10 p. m. Si apagan el computador antes, no hay respaldo ese día. Considere respaldar también al **cerrar la caja**: es un momento natural y seguro.

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
| 2 | **Ícono junto al reloj de Windows** | Quitar la ventana negra; menú con "Abrir", "Respaldar ahora" y "Salir". Librería `pystray`. | Bajo |
| 3 | **Arranque automático con Windows** | Que el sistema esté listo al encender. Opción en el instalador (carpeta *Inicio*). | Bajo |
| 4 | **Actualización automática** | Avisar en la interfaz cuando haya una versión nueva en GitHub Releases. | Medio |
| 5 | **Permisos por rol desde Ajustes** | Hoy se cambian en código (`ROLE_PERMISSIONS` en `domain/users.py`). Algunos clientes querrán un rol "supervisor". | Medio |
| 6 | **Importar productos desde Excel/CSV** | Cargar 500 productos a mano es la mayor barrera del primer día. | Bajo |
| 7 | **Exportar reportes a Excel** | Lo piden los contadores. | Bajo |
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

---

## 8. Referencia rápida

### Comandos

| Tarea | Comando |
| --- | --- |
| Iniciar en desarrollo | `python manage.py runserver` (con `POS_ENV=development` en `.env`) + `cd frontend && npm run dev` |
| Iniciar como el cliente | `python manage.py start` |
| Respaldo | `python manage.py backup` (o `PuntoDeVenta.exe backup`) |
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
| Olvidó la contraseña el único administrador | Cerrar el sistema y ejecutar `PuntoDeVenta.exe create-admin` no sirve si ya hay usuarios. **Falta una herramienta de recuperación** (anótela como pendiente): un comando que restablezca la contraseña de un administrador desde la consola del equipo. |
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
2. **Comando para recuperar la contraseña del administrador** (pequeño y necesario para dar soporte).
3. **Licencias** (3.1).
4. **Respaldo adicional en USB o nube y respaldo al cerrar la caja** (3.3).
5. **Prueba piloto** en 1 o 2 negocios (3.5), con las mejoras #2 (ícono junto al reloj) y #6 (importar productos) si hay tiempo.
6. Firma digital (3.4) cuando empiece a vender en serie.
7. Facturación electrónica (3.2), según lo que diga el contador.
8. Lo demás de la sección 4, guiado por lo que pidan los clientes del piloto.
