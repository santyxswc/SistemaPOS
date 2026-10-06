"""Carga masiva de productos desde una hoja de cálculo.

Cargar 500 productos a mano es la mayor barrera del primer día. Este caso de uso
recibe filas ya separadas en campos (la lectura del archivo es de la presentación)
y las valida con las mismas reglas que el formulario de productos.

- Primero se puede pedir una vista previa (`dry_run`): dice qué se crearía, qué se
  actualizaría y qué filas tienen errores, sin guardar nada.
- Al importar, las filas válidas se guardan juntas en una sola transacción y las
  filas con errores se saltan (el reporte dice cuáles y por qué).
- Las existencias solo se cargan en productos nuevos (como inventario inicial). Para
  corregir las de un producto existente está el ajuste de inventario, que deja rastro.
"""

from __future__ import annotations

import unicodedata
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from ...domain.catalog import Category, Product, Unit
from ...domain.inventory import MovementType, StockMovement
from ...domain.settings import BusinessSettings
from ...domain.shared.errors import DomainError, ValidationError
from ...domain.shared.values import Money, TaxRate, parse_local_decimal, to_quantity
from ...domain.users import Permission
from ..actor import Actor
from ..common import require_settings
from ..ports import Clock, UnitOfWork, UnitOfWorkFactory
from .catalog import ensure_unique_codes

MAX_IMPORT_ROWS = 20_000

# Campos que entiende la importación (la presentación traduce los encabezados del archivo a estos nombres).
IMPORT_FIELDS = ("sku", "name", "price", "cost", "tax_rate", "barcode", "category", "unit", "stock", "min_stock")

_UNIT_WORDS: dict[str, Unit] = {
    **dict.fromkeys(("", "unidad", "unidades", "und", "un", "u", "ud", "unit", "pieza", "pza"), Unit.UNIT),
    **dict.fromkeys(("kg", "kilo", "kilos", "kilogramo", "kilogramos"), Unit.KILOGRAM),
    **dict.fromkeys(("lb", "libra", "libras"), Unit.POUND),
    **dict.fromkeys(("l", "lt", "lts", "litro", "litros"), Unit.LITER),
}
_TAX_FREE_WORDS = {"exento", "excluido", "no", "sin iva", "0%"}


@dataclass(frozen=True)
class ProductImportRow:
    line: int  # número de fila en el archivo, para que el mensaje de error apunte al lugar exacto
    values: Mapping[str, object]  # campo de IMPORT_FIELDS -> texto o número


@dataclass(frozen=True)
class ImportIssue:
    line: int
    message: str


@dataclass
class ProductImportReport:
    dry_run: bool
    created: int = 0
    updated: int = 0
    unchanged: int = 0
    skipped_existing: int = 0
    new_categories: list[str] = field(default_factory=list)
    errors: list[ImportIssue] = field(default_factory=list)

    @property
    def total_rows(self) -> int:
        return self.created + self.updated + self.unchanged + self.skipped_existing + len(self.errors)


def _text(values: Mapping[str, object], key: str) -> str:
    value = values.get(key)
    if value is None:
        return ""
    if isinstance(value, Decimal):
        return format(value.normalize(), "f")  # un código numérico en Excel: 7702511000014, sin ".0"
    return str(value).strip()


def _plain(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch)).casefold().strip()


class _RowReader:
    """Convierte los textos de una fila en datos del dominio, con mensajes que nombran la columna."""

    def __init__(self, values: Mapping[str, object]) -> None:
        self._values = values

    def text(self, key: str) -> str:
        return _text(self._values, key)

    def has(self, key: str) -> bool:
        return bool(self.text(key))

    def money(self, key: str, label: str) -> Money:
        amount = parse_local_decimal(self._raw(key), label)
        return Money(amount)

    def quantity(self, key: str, label: str) -> Decimal:
        return to_quantity(parse_local_decimal(self._raw(key), label), label)

    def tax_rate(self) -> TaxRate:
        if _plain(self.text("tax_rate")) in _TAX_FREE_WORDS:
            return TaxRate.of(0)
        return TaxRate(parse_local_decimal(self._raw("tax_rate"), "IVA"))

    def unit(self) -> Unit:
        word = _plain(self.text("unit")).rstrip(".")
        if word not in _UNIT_WORDS:
            raise ValidationError(f"Unidad «{self.text('unit')}» no reconocida: use unidad, kg, lb o litro")
        return _UNIT_WORDS[word]

    def _raw(self, key: str) -> object:
        value = self._values.get(key)
        return value.strip() if isinstance(value, str) else value


class ImportProducts:
    def __init__(self, uow: UnitOfWorkFactory, clock: Clock) -> None:
        self._uow = uow
        self._clock = clock

    def execute(
        self,
        actor: Actor,
        rows: Sequence[ProductImportRow],
        *,
        update_existing: bool = False,
        dry_run: bool = True,
    ) -> ProductImportReport:
        actor.require(Permission.MANAGE_CATALOG)
        if not rows:
            raise ValidationError("El archivo no tiene productos debajo de los encabezados")
        if len(rows) > MAX_IMPORT_ROWS:
            raise ValidationError(f"Se pueden importar hasta {MAX_IMPORT_ROWS} productos por archivo")
        report = ProductImportReport(dry_run=dry_run)
        now = self._clock.now()
        with self._uow() as uow:
            session = _ImportSession(uow, actor, require_settings(uow), now, report, update_existing)
            for row in rows:
                session.apply(row)
            if not dry_run:
                uow.commit()
        # En vista previa la transacción se descarta al salir: nada queda guardado.
        return report


class _ImportSession:
    """Estado de una importación: códigos ya vistos en el archivo y categorías creadas."""

    def __init__(
        self,
        uow: UnitOfWork,
        actor: Actor,
        settings: BusinessSettings,
        now: datetime,
        report: ProductImportReport,
        update_existing: bool,
    ) -> None:
        self._uow = uow
        self._actor = actor
        self._settings = settings
        self._now = now
        self._report = report
        self._update_existing = update_existing
        self._seen_skus: dict[str, int] = {}
        self._seen_barcodes: dict[str, int] = {}
        self._categories: dict[str, Category] = {}

    def apply(self, row: ProductImportRow) -> None:
        try:
            self._apply(row)
        except DomainError as error:
            self._report.errors.append(ImportIssue(line=row.line, message=error.message))

    def _apply(self, row: ProductImportRow) -> None:
        data = _RowReader(row.values)
        sku = (data.text("sku") or data.text("barcode")).upper()
        if not sku:
            raise ValidationError("Falta el código (SKU) o el código de barras")
        self._remember(self._seen_skus, sku, row.line, "el código")
        if data.has("barcode"):
            self._remember(self._seen_barcodes, data.text("barcode"), row.line, "el código de barras")

        existing = self._uow.products.get_by_sku(sku)
        if existing is None:
            self._create(sku, data)
        elif self._update_existing:
            self._update(existing, data)
        else:
            self._report.skipped_existing += 1

    @staticmethod
    def _remember(seen: dict[str, int], code: str, line: int, label: str) -> None:
        if code in seen:
            raise ValidationError(f"Repite {label} {code} de la fila {seen[code]}")
        seen[code] = line

    def _create(self, sku: str, data: _RowReader) -> None:
        if not data.has("name"):
            raise ValidationError("Falta el nombre del producto")
        if not data.has("price"):
            raise ValidationError("Falta el precio de venta")
        product = Product(
            sku=sku,
            name=data.text("name"),
            price=data.money("price", "precio"),
            cost=data.money("cost", "costo") if data.has("cost") else Money.zero(),
            tax_rate=data.tax_rate() if data.has("tax_rate") else self._settings.default_tax_rate,
            unit=data.unit(),
            barcode=data.text("barcode") or None,
            min_stock=data.quantity("min_stock", "stock mínimo") if data.has("min_stock") else Decimal(0),
            category_id=self._category_id(data.text("category")),
            created_at=self._now,
        )
        stock = data.quantity("stock", "existencias") if data.has("stock") else Decimal(0)
        if stock < 0:
            raise ValidationError("Las existencias iniciales no pueden ser negativas")
        if stock > 0:
            product.add_stock(product.check_quantity(stock), at=self._now)
        ensure_unique_codes(self._uow, product)
        self._uow.products.add(product)
        if stock > 0:
            self._uow.stock_movements.add(
                StockMovement(
                    product_id=product.id,
                    type=MovementType.INITIAL,
                    quantity=stock,
                    stock_after=product.stock,
                    user_id=self._actor.user_id,
                    created_at=self._now,
                    note="Inventario inicial (importación)",
                )
            )
        self._report.created += 1

    def _update(self, product: Product, data: _RowReader) -> None:
        changes: dict[str, Any] = {}
        if data.has("name"):
            changes["name"] = data.text("name")
        if data.has("price"):
            changes["price"] = data.money("price", "precio")
        if data.has("cost"):
            changes["cost"] = data.money("cost", "costo")
        if data.has("tax_rate"):
            changes["tax_rate"] = data.tax_rate()
        if data.has("unit"):
            changes["unit"] = data.unit()
        if data.has("barcode"):
            changes["barcode"] = data.text("barcode")
        if data.has("min_stock"):
            changes["min_stock"] = data.quantity("min_stock", "stock mínimo")
        if data.has("category"):
            changes["category_id"] = self._category_id(data.text("category"))
        changes = {key: value for key, value in changes.items() if getattr(product, key) != value}
        if not changes:
            self._report.unchanged += 1
            return
        product.update(at=self._now, **changes)
        ensure_unique_codes(self._uow, product)
        self._uow.products.save(product)
        self._report.updated += 1

    def _category_id(self, name: str) -> UUID | None:
        cleaned = " ".join(name.split())
        if not cleaned:
            return None
        key = _plain(cleaned)
        category = self._categories.get(key) or self._uow.categories.get_by_name(cleaned)
        if category is not None and not category.active:
            raise ValidationError(f"La categoría «{category.name}» está inactiva")
        if category is None:
            category = Category(name=cleaned)
            self._uow.categories.add(category)
            self._report.new_categories.append(cleaned)
        self._categories[key] = category
        return category.id
