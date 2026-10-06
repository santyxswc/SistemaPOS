"""Inventario: compras, ajustes por conteo, alertas de stock bajo y kárdex."""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from ...domain.catalog import Product
from ...domain.inventory import MovementType, StockMovement
from ...domain.shared.errors import BusinessRuleViolation
from ...domain.shared.values import Money, required_text
from ...domain.users import Permission
from ..actor import Actor
from ..common import get_or_404, page_size
from ..ports import Clock, UnitOfWorkFactory


class RegisterPurchase:
    """Entrada de mercancía de un proveedor; actualiza existencia y costo promedio."""

    def __init__(self, uow: UnitOfWorkFactory, clock: Clock) -> None:
        self._uow = uow
        self._clock = clock

    def execute(
        self,
        actor: Actor,
        *,
        product_id: UUID,
        quantity: Decimal,
        unit_cost: Money | None = None,
        note: str = "",
    ) -> StockMovement:
        actor.require(Permission.MANAGE_INVENTORY)
        now = self._clock.now()
        with self._uow() as uow:
            product = get_or_404(uow.products.get(product_id), "Producto no encontrado")
            if not product.track_stock:
                raise BusinessRuleViolation(f"«{product.name}» no controla inventario")
            qty = product.check_quantity(quantity)
            product.add_stock(qty, at=now, unit_cost=unit_cost)
            movement = StockMovement(
                product_id=product.id,
                type=MovementType.PURCHASE,
                quantity=qty,
                stock_after=product.stock,
                unit_cost=unit_cost,
                user_id=actor.user_id,
                created_at=now,
                note=(note or "").strip(),
            )
            uow.products.save(product)
            uow.stock_movements.add(movement)
            uow.commit()
        return movement


class AdjustStock:
    """Ajuste por conteo físico; deja el motivo para auditoría."""

    def __init__(self, uow: UnitOfWorkFactory, clock: Clock) -> None:
        self._uow = uow
        self._clock = clock

    def execute(self, actor: Actor, *, product_id: UUID, counted_quantity: Decimal, reason: str) -> StockMovement:
        actor.require(Permission.MANAGE_INVENTORY)
        cleaned_reason = required_text(reason, "motivo del ajuste")
        now = self._clock.now()
        with self._uow() as uow:
            product = get_or_404(uow.products.get(product_id), "Producto no encontrado")
            difference = product.adjust_stock(counted_quantity, at=now)
            movement = StockMovement(
                product_id=product.id,
                type=MovementType.ADJUSTMENT,
                quantity=difference,
                stock_after=product.stock,
                user_id=actor.user_id,
                created_at=now,
                note=cleaned_reason,
            )
            uow.products.save(product)
            uow.stock_movements.add(movement)
            uow.commit()
        return movement


class ListLowStock:
    def __init__(self, uow: UnitOfWorkFactory) -> None:
        self._uow = uow

    def execute(self) -> list[Product]:
        with self._uow(read_only=True) as uow:
            return uow.products.list_low_stock()


class ListStockMovements:
    def __init__(self, uow: UnitOfWorkFactory) -> None:
        self._uow = uow

    def execute(self, actor: Actor, product_id: UUID, limit: int = 50) -> list[StockMovement]:
        actor.require(Permission.MANAGE_INVENTORY)
        with self._uow(read_only=True) as uow:
            get_or_404(uow.products.get(product_id), "Producto no encontrado")
            return uow.stock_movements.list_for_product(product_id, limit=page_size(limit))
