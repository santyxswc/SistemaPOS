"""Módulos: las partes del sistema que se encienden o apagan para cada cliente.

Lo mismo para todos los negocios es el núcleo (vender, caja, ventas, productos,
inventario, usuarios, ajustes y respaldos). Todo lo demás es un módulo opcional
declarado en `CATALOG`. El técnico decide qué módulos tiene cada cliente en el `.env`
de su carpeta de datos (`POS_MODULES_DISABLED` / `POS_MODULES_ENABLED`, o con el
comando `modules`); el dueño del negocio no lo puede cambiar.

Apagar un módulo hace tres cosas, sin `if` repartidos por el código:
- sus rutas de la API no se registran (responden 404);
- sus permisos desaparecen de todos los usuarios, así que los casos de uso que los
  piden se niegan y la interfaz oculta lo que dependa de ellos;
- la interfaz, que recibe la lista de módulos, quita sus pestañas y secciones.

Para agregar un módulo: una entrada en `Module` y otra en `CATALOG`, sus rutas en
`OPTIONAL_ROUTES` (presentation/http/app.py) y su `module` en las rutas de la
interfaz (frontend/src/modules.ts). Ver docs/MODULOS.md.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum

from ..domain.shared.errors import NotFoundError, ValidationError
from ..domain.users import Permission


class Module(StrEnum):
    # Los valores son lo que el técnico escribe en el .env: en español y sin tildes.
    CUSTOMERS = "clientes"
    CREDIT = "fiado"
    SUPPLIERS = "proveedores"
    REPORTS = "reportes"
    DISCOUNTS = "descuentos"
    ROLE_PERMISSIONS = "permisos"
    SPREADSHEETS = "excel"
    DIRECT_PRINTING = "impresion"
    INVOICING = "facturacion"
    UPDATES = "actualizaciones"
    LICENSING = "licencias"


@dataclass(frozen=True)
class ModuleInfo:
    module: Module
    name: str
    description: str
    enabled_by_default: bool = True
    requires: tuple[Module, ...] = ()
    permissions: frozenset[Permission] = frozenset()  # solo existen si el módulo está encendido


CATALOG: tuple[ModuleInfo, ...] = (
    ModuleInfo(
        Module.CUSTOMERS,
        "Clientes",
        "Pestaña Clientes: datos de contacto y estado de cuenta.",
        permissions=frozenset({Permission.MANAGE_CUSTOMERS}),
    ),
    ModuleInfo(
        Module.CREDIT,
        "Fiado",
        "Ventas fiadas con cupo por cliente y abonos.",
        requires=(Module.CUSTOMERS,),
        permissions=frozenset({Permission.GRANT_CREDIT, Permission.COLLECT_PAYMENTS}),
    ),
    ModuleInfo(
        Module.SUPPLIERS,
        "Proveedores",
        "Pestaña Proveedores: compras de mercancía y cuentas por pagar.",
        permissions=frozenset({Permission.MANAGE_SUPPLIERS}),
    ),
    ModuleInfo(
        Module.REPORTS,
        "Reportes",
        "Pestaña Reportes: ventas por periodo, productos más vendidos y Excel para el contador.",
        permissions=frozenset({Permission.VIEW_REPORTS}),
    ),
    ModuleInfo(
        Module.DISCOUNTS,
        "Descuentos",
        "Descuentos por producto al vender.",
        permissions=frozenset({Permission.APPLY_DISCOUNTS}),
    ),
    ModuleInfo(
        Module.ROLE_PERMISSIONS,
        "Permisos por rol",
        "El dueño ajusta qué puede hacer el supervisor y el cajero. Apagado, rigen los permisos de fábrica.",
    ),
    ModuleInfo(
        Module.SPREADSHEETS,
        "Excel de productos",
        "Importar productos desde Excel o CSV y exportar el catálogo.",
    ),
    ModuleInfo(
        Module.DIRECT_PRINTING,
        "Impresión directa",
        "Imprimir en la impresora térmica sin el cuadro del navegador y abrir el cajón.",
    ),
    ModuleInfo(
        Module.INVOICING,
        "Facturación electrónica",
        "Bandeja de documentos electrónicos (DIAN). Además necesita POS_INVOICE_PROVIDER.",
    ),
    ModuleInfo(
        Module.UPDATES,
        "Aviso de versiones",
        "Avisa al administrador cuando hay una versión nueva publicada.",
    ),
    ModuleInfo(
        Module.LICENSING,
        "Licencias",
        "Límite de usuarios por plan con códigos firmados. Apagado, no hay límite ni periodo de prueba.",
        enabled_by_default=False,
    ),
)

_BY_MODULE = {info.module: info for info in CATALOG}
_ALL_MODULE_PERMISSIONS = frozenset().union(*(info.permissions for info in CATALOG))


def module_info(module: Module) -> ModuleInfo:
    return _BY_MODULE[module]


def parse_module_names(text: str) -> set[Module]:
    """'proveedores, reportes' → {Module.SUPPLIERS, Module.REPORTS}. Un nombre desconocido es un error."""
    modules: set[Module] = set()
    for raw in text.replace(";", ",").split(","):
        name = raw.strip().lower()
        if not name:
            continue
        try:
            modules.add(Module(name))
        except ValueError:
            valid = ", ".join(m.value for m in Module)
            raise ValidationError(f"No existe el módulo «{name}». Módulos: {valid}") from None
    return modules


@dataclass(frozen=True)
class ModuleSet:
    """Los módulos encendidos en esta instalación (inmutable: se arma una vez al iniciar)."""

    enabled: frozenset[Module]

    @classmethod
    def defaults(cls) -> ModuleSet:
        return cls.configure()

    @classmethod
    def all(cls) -> ModuleSet:
        return cls.configure(enable=Module)

    @classmethod
    def configure(cls, *, disable: Iterable[Module] = (), enable: Iterable[Module] = ()) -> ModuleSet:
        """Parte de los de fábrica, apaga `disable` y enciende `enable` (apagar gana si están en ambos).

        Un módulo cuyo requisito quedó apagado se apaga también: sin clientes no hay a quién fiarle.
        """
        disabled = set(disable)
        chosen = {info.module for info in CATALOG if info.enabled_by_default} | set(enable)
        chosen -= disabled
        changed = True
        while changed:
            missing = {m for m in chosen if any(r not in chosen for r in _BY_MODULE[m].requires)}
            chosen -= missing
            changed = bool(missing)
        return cls(frozenset(chosen))

    def is_enabled(self, module: Module) -> bool:
        return module in self.enabled

    def require(self, module: Module) -> None:
        """Para los casos de uso de un módulo apagado: se comportan como si no existieran."""
        if module not in self.enabled:
            raise NotFoundError(f"La función «{_BY_MODULE[module].name}» no está disponible en este sistema")

    @property
    def available_permissions(self) -> frozenset[Permission]:
        """Los permisos del núcleo y los de los módulos encendidos."""
        enabled = frozenset().union(*(_BY_MODULE[m].permissions for m in self.enabled))
        return frozenset(Permission) - (_ALL_MODULE_PERMISSIONS - enabled)

    def blocked_by(self, module: Module) -> Module | None:
        """Si `module` está apagado por un requisito apagado, cuál es (para explicarlo en la consola)."""
        if module in self.enabled:
            return None
        return next((r for r in _BY_MODULE[module].requires if r not in self.enabled), None)
