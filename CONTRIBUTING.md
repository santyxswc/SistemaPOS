# Guía de desarrollo

## Preparar el entorno

```bash
python -m venv .venv
source .venv/bin/activate              # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
cp .env.example .env                   # POS_ENV=development
python manage.py runserver             # API en http://127.0.0.1:8000
cd frontend && npm install && npm run dev   # interfaz con recarga en http://localhost:5173
```

Requisitos: Python 3.11+ y Node 22+.

## Reglas del proyecto

1. **Nunca edite una migración ya publicada** (`infrastructure/persistence/sqlite/migrations.py`). Agregue una nueva al final de la lista. Las bases de datos de los clientes se actualizan solas al abrir el programa.
2. **Nunca cambie el `AppId`** de `packaging/instalador.iss`. Si lo cambia, las actualizaciones se instalan como un programa distinto.
3. **Para subir la versión**, cámbiela en los tres lugares: `src/pos/__init__.py`, `pyproject.toml` y `frontend/package.json`. La etiqueta debe coincidir (`v0.3.0`); si no, el build de GitHub falla a propósito.
4. **El dinero nunca va en `float`.** Backend: `Money` y `Decimal`. Frontend: centavos enteros (`money.ts`). La API recibe y envía texto (`"12500.00"`).
5. **Los permisos se revisan en los casos de uso**, no en las rutas ni en la interfaz. Ocultar un botón no es seguridad.
6. **El historial no se edita:** kárdex, movimientos de caja y estado de cuenta solo se agregan. Las correcciones son movimientos nuevos (ajuste o anulación).
7. **Antes de cada commit:**
   ```bash
   python -m ruff check .
   python -m pytest -q
   cd frontend && npm test && npx tsc --noEmit
   ```

---

## Cómo agregar funciones

Las recetas (pantalla nueva, caso de uso, migración, permiso, rol, evento, tarea de fondo...) están en
[`docs/PERSONALIZACION.md`](docs/PERSONALIZACION.md#recetas-para-extender-el-código). Para un módulo opcional
nuevo, vea [`docs/MODULOS.md`](docs/MODULOS.md).

## Commits

- Un cambio por commit, con el mensaje en presente y en español ("Agrega...", "Corrige...").
- Nunca suba archivos `.env`, claves (`*.pem`, `*.key`) ni bases de datos: `.gitignore` los excluye, pero revise
  `git status` antes de cada commit.
