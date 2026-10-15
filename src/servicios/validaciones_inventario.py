"""Validaciones de datos que comparten los servicios de inventario (pohlsi)."""

from decimal import Decimal, InvalidOperation

from src.excepciones import ValidacionError


def entero_positivo(valor, nombre: str = "La cantidad") -> int:
    if isinstance(valor, bool) or not isinstance(valor, int) or valor <= 0:
        raise ValidacionError(f"{nombre} debe ser un número entero mayor a cero.")
    return valor


def decimal_no_negativo(valor, nombre: str = "El costo unitario") -> Decimal:
    try:
        numero = Decimal(str(valor))
    except InvalidOperation:
        raise ValidacionError(f"{nombre} no es un número válido.") from None
    if not numero.is_finite() or numero < 0:
        raise ValidacionError(f"{nombre} no puede ser negativo.")
    return numero
