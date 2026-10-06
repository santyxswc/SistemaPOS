"""Movimientos de inventario: historial inmutable de cada entrada y salida (kárdex)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum
from uuid import UUID

from .shared.entity import Entity
from .shared.values import Money


class MovementType(str, Enum):
    INITIAL = "initial"
    PURCHASE = "purchase"
    ADJUSTMENT = "adjustment"
    SALE = "sale"
    SALE_VOID = "sale_void"


@dataclass(kw_only=True, eq=False)
class StockMovement(Entity):
    product_id: UUID
    type: MovementType
    quantity: Decimal  # positivo entra, negativo sale
    stock_after: Decimal
    user_id: UUID
    created_at: datetime
    unit_cost: Money | None = None
    reference: str | None = None
    note: str = ""
