"""Catálogo: categorías y productos. El producto lleva su propia existencia en inventario."""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from uuid import UUID

from .shared.entity import AggregateRoot, Entity
from .shared.errors import BusinessRuleViolation, InsufficientStock, ValidationError
from .shared.events import DomainEvent
from .shared.values import Money, TaxRate, format_quantity, parse_enum, required_text, to_quantity


class Unit(StrEnum):
    UNIT = "unit"
    KILOGRAM = "kg"
    POUND = "lb"
    LITER = "l"

    @property
    def fractional(self) -> bool:
        return self is not Unit.UNIT


@dataclass(frozen=True, kw_only=True)
class StockLow(DomainEvent):
    product_id: UUID
    product_name: str
    stock: Decimal
    min_stock: Decimal


@dataclass(kw_only=True, eq=False)
class Category(Entity):
    name: str
    active: bool = True

    def __post_init__(self) -> None:
        self.name = required_text(self.name, "nombre de la categoría")


@dataclass(kw_only=True, eq=False)
class Product(AggregateRoot):
    EDITABLE_FIELDS = frozenset(
        {"sku", "name", "price", "cost", "tax_rate", "unit", "barcode",
         "category_id", "track_stock", "min_stock", "active"}
    )

    sku: str
    name: str
    price: Money
    tax_rate: TaxRate
    created_at: datetime
    cost: Money = field(default_factory=Money.zero)
    unit: Unit = Unit.UNIT
    barcode: str | None = None
    category_id: UUID | None = None
    track_stock: bool = True
    stock: Decimal = Decimal(0)
    min_stock: Decimal = Decimal(0)
    active: bool = True
    updated_at: datetime | None = None

    def __post_init__(self) -> None:
        self.sku = required_text(self.sku, "SKU").upper()
        self.name = required_text(self.name, "nombre del producto")
        self.barcode = (self.barcode or "").strip() or None
        self.unit = parse_enum(Unit, self.unit, "unidad")
        if self.price.is_negative or self.cost.is_negative:
            raise ValidationError("El precio y el costo no pueden ser negativos")
        self.stock = to_quantity(self.stock, "stock")
        self.min_stock = to_quantity(self.min_stock, "stock mínimo")
        if self.min_stock < 0:
            raise ValidationError("El stock mínimo no puede ser negativo")
        if self.updated_at is None:
            self.updated_at = self.created_at

    @property
    def is_low_stock(self) -> bool:
        return self.track_stock and self.active and self.stock <= self.min_stock

    def check_quantity(self, quantity: object) -> Decimal:
        """Valida una cantidad vendible: positiva y entera si el producto va por unidades."""
        qty = to_quantity(quantity)
        if qty <= 0:
            raise ValidationError(f"La cantidad de «{self.name}» debe ser mayor que cero")
        if not self.unit.fractional and qty != qty.to_integral_value():
            raise ValidationError(f"«{self.name}» se vende por unidades enteras")
        return qty

    def update(self, *, at: datetime, **changes: object) -> None:
        """Aplica cambios validando el resultado completo antes de tocar el producto."""
        unknown = set(changes) - self.EDITABLE_FIELDS
        if unknown:
            raise ValidationError(f"No se pueden editar estos campos: {', '.join(sorted(unknown))}")
        candidate = dataclasses.replace(self, **changes)  # type: ignore[arg-type]
        for name in changes:
            setattr(self, name, getattr(candidate, name))
        self.updated_at = at

    def remove_stock(self, quantity: Decimal, *, allow_negative: bool, at: datetime) -> None:
        if not self.track_stock:
            return
        if not allow_negative and quantity > self.stock:
            raise InsufficientStock(
                f"Stock insuficiente de «{self.name}»: hay {format_quantity(self.stock)} "
                f"y se piden {format_quantity(quantity)}"
            )
        self._set_stock(self.stock - quantity, at)

    def add_stock(self, quantity: Decimal, *, at: datetime, unit_cost: Money | None = None) -> None:
        """Entrada de mercancía. Con costo unitario recalcula el costo promedio ponderado."""
        if quantity <= 0:
            raise ValidationError("La cantidad debe ser mayor que cero")
        if unit_cost is not None:
            if unit_cost.is_negative:
                raise ValidationError("El costo no puede ser negativo")
            self.cost = self._average_cost(quantity, unit_cost)
        if self.track_stock:
            self._set_stock(self.stock + quantity, at)
        else:
            self.updated_at = at

    def adjust_stock(self, counted: object, *, at: datetime) -> Decimal:
        """Ajuste por conteo físico. Devuelve la diferencia (positiva sobra, negativa falta)."""
        if not self.track_stock:
            raise BusinessRuleViolation(f"«{self.name}» no controla inventario")
        counted_qty = to_quantity(counted, "cantidad contada")
        if counted_qty < 0:
            raise ValidationError("La cantidad contada no puede ser negativa")
        difference = counted_qty - self.stock
        self._set_stock(counted_qty, at)
        return difference

    def _average_cost(self, quantity: Decimal, unit_cost: Money) -> Money:
        if not self.track_stock or self.stock <= 0:
            return unit_cost
        total_units = self.stock + quantity
        return Money((self.cost.amount * self.stock + unit_cost.amount * quantity) / total_units)

    def _set_stock(self, new_stock: Decimal, at: datetime) -> None:
        was_low = self.is_low_stock
        self.stock = new_stock
        self.updated_at = at
        if self.is_low_stock and not was_low:
            self.record(
                StockLow(
                    occurred_at=at,
                    product_id=self.id,
                    product_name=self.name,
                    stock=self.stock,
                    min_stock=self.min_stock,
                )
            )
