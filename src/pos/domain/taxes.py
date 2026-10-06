"""Políticas de impuesto (patrón Strategy).

Cada negocio elige si sus precios ya incluyen el impuesto (tienda de barrio) o si
el impuesto se suma al precio (ventas entre empresas). Las ventas no cambian.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from .shared.values import Money, TaxRate


@dataclass(frozen=True)
class TaxBreakdown:
    base: Money
    tax: Money
    total: Money


class TaxPolicy(ABC):
    @abstractmethod
    def breakdown(self, amount: Money, rate: TaxRate) -> TaxBreakdown:
        """Separa un monto en base gravable, impuesto y total a pagar."""


class TaxIncludedPolicy(TaxPolicy):
    """El precio de venta ya trae el impuesto: $11.900 con IVA 19 % = $10.000 + $1.900."""

    def breakdown(self, amount: Money, rate: TaxRate) -> TaxBreakdown:
        base = Money(amount.amount / (1 + rate.fraction))
        return TaxBreakdown(base=base, tax=amount - base, total=amount)


class TaxExcludedPolicy(TaxPolicy):
    """El impuesto se suma al precio: $10.000 + IVA 19 % = $11.900."""

    def breakdown(self, amount: Money, rate: TaxRate) -> TaxBreakdown:
        tax = Money(amount.amount * rate.fraction)
        return TaxBreakdown(base=amount, tax=tax, total=amount + tax)
