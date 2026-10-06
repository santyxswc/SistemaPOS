"""Catálogo: categorías y productos."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID

from ...domain.catalog import Category, Product, Unit
from ...domain.inventory import MovementType, StockMovement
from ...domain.shared.errors import ConflictError, NotFoundError, ValidationError
from ...domain.shared.values import Money, TaxRate, to_quantity
from ...domain.users import Permission
from ..actor import Actor
from ..common import get_or_404, page_size, require_settings
from ..ports import Clock, UnitOfWork, UnitOfWorkFactory


def ensure_unique_codes(uow: UnitOfWork, product: Product) -> None:
    same_sku = uow.products.get_by_sku(product.sku)
    if same_sku is not None and same_sku.id != product.id:
        raise ConflictError(f"Ya existe un producto con el SKU {product.sku}")
    if product.barcode:
        same_barcode = uow.products.get_by_barcode(product.barcode)
        if same_barcode is not None and same_barcode.id != product.id:
            raise ConflictError(f"Ya existe un producto con el código de barras {product.barcode}")


def ensure_category(uow: UnitOfWork, category_id: UUID | None) -> None:
    if category_id is None:
        return
    category = uow.categories.get(category_id)
    if category is None or not category.active:
        raise NotFoundError("La categoría no existe o está inactiva")


class CreateCategory:
    def __init__(self, uow: UnitOfWorkFactory) -> None:
        self._uow = uow

    def execute(self, actor: Actor, name: str) -> Category:
        actor.require(Permission.MANAGE_CATALOG)
        category = Category(name=name)
        with self._uow() as uow:
            if uow.categories.get_by_name(category.name) is not None:
                raise ConflictError(f"La categoría «{category.name}» ya existe")
            uow.categories.add(category)
            uow.commit()
        return category


class ListCategories:
    def __init__(self, uow: UnitOfWorkFactory) -> None:
        self._uow = uow

    def execute(self, include_inactive: bool = False) -> list[Category]:
        with self._uow(read_only=True) as uow:
            return uow.categories.list_all(include_inactive=include_inactive)


@dataclass(frozen=True)
class CreateProductCommand:
    sku: str
    name: str
    price: Money
    tax_rate: TaxRate | None = None  # None = impuesto por defecto del negocio
    cost: Money | None = None
    unit: Unit = Unit.UNIT
    barcode: str | None = None
    category_id: UUID | None = None
    track_stock: bool = True
    initial_stock: Decimal = Decimal(0)
    min_stock: Decimal = Decimal(0)


class CreateProduct:
    def __init__(self, uow: UnitOfWorkFactory, clock: Clock) -> None:
        self._uow = uow
        self._clock = clock

    def execute(self, actor: Actor, command: CreateProductCommand) -> Product:
        actor.require(Permission.MANAGE_CATALOG)
        now = self._clock.now()
        with self._uow() as uow:
            settings = require_settings(uow)
            product = Product(
                sku=command.sku,
                name=command.name,
                price=command.price,
                tax_rate=command.tax_rate or settings.default_tax_rate,
                cost=command.cost or Money.zero(),
                unit=command.unit,
                barcode=command.barcode,
                category_id=command.category_id,
                track_stock=command.track_stock,
                min_stock=command.min_stock,
                created_at=now,
            )
            ensure_unique_codes(uow, product)
            ensure_category(uow, product.category_id)

            initial = to_quantity(command.initial_stock, "stock inicial")
            if initial < 0:
                raise ValidationError("El stock inicial no puede ser negativo")
            if initial > 0 and not product.track_stock:
                raise ValidationError("Un producto sin control de inventario no lleva stock inicial")
            if initial > 0:
                product.add_stock(product.check_quantity(initial), at=now)

            uow.products.add(product)
            if initial > 0:
                uow.stock_movements.add(
                    StockMovement(
                        product_id=product.id,
                        type=MovementType.INITIAL,
                        quantity=initial,
                        stock_after=product.stock,
                        user_id=actor.user_id,
                        created_at=now,
                        note="Inventario inicial",
                    )
                )
            uow.commit()
        return product


class UpdateProduct:
    """Edita datos del producto. La existencia solo cambia por movimientos de inventario."""

    def __init__(self, uow: UnitOfWorkFactory, clock: Clock) -> None:
        self._uow = uow
        self._clock = clock

    def execute(self, actor: Actor, product_id: UUID, changes: Mapping[str, object]) -> Product:
        actor.require(Permission.MANAGE_CATALOG)
        with self._uow() as uow:
            product = get_or_404(uow.products.get(product_id), "Producto no encontrado")
            product.update(at=self._clock.now(), **changes)
            ensure_unique_codes(uow, product)
            if "category_id" in changes:
                ensure_category(uow, product.category_id)
            uow.products.save(product)
            uow.commit()
        return product


class GetProduct:
    def __init__(self, uow: UnitOfWorkFactory) -> None:
        self._uow = uow

    def execute(self, product_id: UUID) -> Product:
        with self._uow(read_only=True) as uow:
            return get_or_404(uow.products.get(product_id), "Producto no encontrado")


class FindProductByCode:
    """Lo que usa el lector de código de barras: busca por código de barras y luego por SKU."""

    def __init__(self, uow: UnitOfWorkFactory) -> None:
        self._uow = uow

    def execute(self, code: str) -> Product:
        cleaned = (code or "").strip()
        if not cleaned:
            raise ValidationError("Escriba o escanee un código")
        with self._uow(read_only=True) as uow:
            product = uow.products.get_by_barcode(cleaned) or uow.products.get_by_sku(cleaned.upper())
        if product is None or not product.active:
            raise NotFoundError(f"No hay un producto activo con el código {cleaned}")
        return product


class SearchProducts:
    def __init__(self, uow: UnitOfWorkFactory) -> None:
        self._uow = uow

    def execute(
        self,
        *,
        text: str | None = None,
        category_id: UUID | None = None,
        include_inactive: bool = False,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Product]:
        with self._uow(read_only=True) as uow:
            return uow.products.search(
                text=text,
                category_id=category_id,
                include_inactive=include_inactive,
                limit=page_size(limit),
                offset=max(0, offset),
            )


@dataclass(frozen=True)
class CatalogExport:
    products: list[Product]
    category_names: dict[UUID, str]


class ExportCatalog:
    """Todo el catálogo para Excel, con los mismos encabezados que entiende la importación:
    se exporta, se cambian precios en Excel y se vuelve a importar."""

    def __init__(self, uow: UnitOfWorkFactory) -> None:
        self._uow = uow

    def execute(self, actor: Actor, *, include_inactive: bool = False) -> CatalogExport:
        actor.require(Permission.MANAGE_CATALOG)  # incluye costos: no es para cualquier usuario
        with self._uow(read_only=True) as uow:
            products = uow.products.list_all(include_inactive=include_inactive)
            categories = uow.categories.list_all(include_inactive=True)
        return CatalogExport(products=products, category_names={c.id: c.name for c in categories})
