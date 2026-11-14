"""Auxiliares de las rutas: leer los datos que manda el navegador y dar formato a los que vuelven."""

from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from flask import current_app, request

from src.excepciones import ValidacionError
from src.web.servicios import Servicios


def servicios() -> Servicios:
    return current_app.extensions["servicios"]


def cuerpo() -> dict[str, Any]:
    """Datos JSON del pedido (POST o PUT)."""
    return request.get_json(silent=True) or {}


def texto(valor: Any) -> str:
    return str(valor).strip() if valor is not None else ""


def texto_opcional(valor: Any) -> str | None:
    return texto(valor) or None


def entero(valor: Any, campo: str, opcional: bool = False) -> int | None:
    if valor is None or texto(valor) == "":
        if opcional:
            return None
        raise ValidacionError(f"Completá el campo «{campo}».")
    try:
        return int(texto(valor))
    except ValueError:
        raise ValidacionError(f"«{campo}» debe ser un número entero.") from None


def decimal(valor: Any, campo: str) -> Decimal:
    if valor is None or texto(valor) == "":
        raise ValidacionError(f"Completá el campo «{campo}».")
    try:
        return Decimal(texto(valor).replace(",", "."))
    except InvalidOperation:
        raise ValidacionError(f"«{campo}» debe ser un número.") from None


def fecha(valor: Any, campo: str, por_defecto: date) -> date:
    if valor is None or texto(valor) == "":
        return por_defecto
    try:
        return date.fromisoformat(texto(valor))
    except ValueError:
        raise ValidacionError(f"«{campo}» no es una fecha válida.") from None


def arg_entero(nombre: str, campo: str, opcional: bool = True) -> int | None:
    return entero(request.args.get(nombre), campo, opcional)


# --- Formato para mostrar (reportes y exportación) ---------------------------------------------


def dinero(valor: Decimal | int | float | None) -> str:
    """Decimal('-1234.5') -> '-$ 1.234,50'."""
    if valor is None:
        return ""
    valor = Decimal(str(valor))
    numero = f"{abs(valor):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"{'-' if valor < 0 else ''}$ {numero}"


def porcentaje(valor: Decimal | float | None) -> str:
    return "—" if valor is None else f"{Decimal(str(valor)):.1f} %".replace(".", ",")


def fecha_hora(valor: datetime | None) -> str:
    return valor.strftime("%d/%m/%Y %H:%M") if valor else "—"


def miles(valor: int) -> str:
    return f"{valor:,}".replace(",", ".")


NOMBRES_COMPROBANTE = {
    "TICKET": "Ticket",
    "FACTURA_A": "Factura A",
    "FACTURA_B": "Factura B",
    "NOTA_CREDITO": "Nota de crédito",
}

NOMBRES_MEDIO = {
    "EFECTIVO": "Efectivo",
    "DEBITO": "Débito",
    "CREDITO": "Crédito",
    "TRANSFERENCIA": "Transferencia",
}


def comprobante(tipo: str, punto_venta: int, numero: int) -> str:
    """('FACTURA_B', 1, 36) -> 'Factura B 0001-00000036'."""
    return f"{NOMBRES_COMPROBANTE.get(tipo, tipo)} {int(punto_venta):04d}-{int(numero):08d}"
