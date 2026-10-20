"""Entidades del proceso P7 y estrategias para pagos/comprobantes."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from enum import StrEnum


CENTAVO = Decimal("0.01")


def dinero(valor: Decimal | str | int) -> Decimal:
    """Normaliza importes a centavos sin introducir errores de punto flotante."""
    return Decimal(str(valor)).quantize(CENTAVO, rounding=ROUND_HALF_UP)


class CondicionIva(StrEnum):
    """Condición fiscal del cliente, usada por ComprobanteFactory."""

    CONSUMIDOR_FINAL = "CONSUMIDOR_FINAL"
    RESPONSABLE_INSCRIPTO = "RESPONSABLE_INSCRIPTO"
    MONOTRIBUTISTA = "MONOTRIBUTISTA"
    EXENTO = "EXENTO"


class EstadoVenta(StrEnum):
    """Estado persistido de la venta; solo CONFIRMADA afecta stock y caja."""

    CONFIRMADA = "CONFIRMADA"
    ANULADA = "ANULADA"


@dataclass
class Cliente:
    """Comprador opcional de una venta (P7 y datos fiscales del comprobante)."""

    documento: str
    nombre: str
    condicion_iva: CondicionIva = CondicionIva.CONSUMIDOR_FINAL
    id: int | None = None

    def es_consumidor_final(self) -> bool:
        """Permite que la fábrica elija el comprobante adecuado al comprador."""
        return self.condicion_iva == CondicionIva.CONSUMIDOR_FINAL


@dataclass
class DetalleVenta:
    """Renglón con precios y costo congelados al vender; soporta devolución V5."""

    producto_id: int
    cantidad: int
    precio_unitario: Decimal
    costo_unitario: Decimal
    cantidad_devuelta: int = 0
    recargo_asignado: Decimal = Decimal("0.00")
    monto_reintegrado: Decimal = Decimal("0.00")
    id: int | None = None

    def subtotal(self) -> Decimal:
        """Subtotal de mercadería, sin el recargo de los medios de pago."""
        return dinero(self.precio_unitario * self.cantidad)

    def cantidad_devolvible(self) -> int:
        """Unidades aún disponibles para una devolución válida (V5)."""
        return self.cantidad - self.cantidad_devuelta


@dataclass
class Cobro:
    """Pago de una venta; monto y recargo quedan auditables por medio (P7)."""

    medio_pago: str
    monto: Decimal
    recargo: Decimal = Decimal("0.00")
    nro_autorizacion: str = ""
    fecha_hora: datetime = field(default_factory=datetime.now)
    id: int | None = None


class MedioPago(ABC):
    """Strategy: cada forma de pago valida datos y calcula su recargo."""

    tipo: str

    @abstractmethod
    def calcular_recargo(self, monto: Decimal) -> Decimal:
        """Calcula el cargo adicional sobre el importe base asignado."""

    @abstractmethod
    def validar(self, datos: dict[str, str]) -> bool:
        """Indica si los datos operativos del pago alcanzan para registrarlo."""

    def permite_reintegro(self) -> bool:
        """Indica si el medio puede utilizarse para devolver dinero."""
        return True


class Efectivo(MedioPago):
    """Pago en efectivo sin recargo ni datos externos (P7)."""

    tipo = "EFECTIVO"

    def calcular_recargo(self, monto: Decimal) -> Decimal:
        return Decimal("0.00")

    def validar(self, datos: dict[str, str]) -> bool:
        return True


class TarjetaDebito(MedioPago):
    """Débito: requiere referencia de autorización y no agrega recargo."""

    tipo = "DEBITO"

    def calcular_recargo(self, monto: Decimal) -> Decimal:
        return Decimal("0.00")

    def validar(self, datos: dict[str, str]) -> bool:
        return bool(datos.get("autorizacion", "").strip())


class TarjetaCredito(MedioPago):
    """Crédito: calcula recargo por cuota adicional sin guardar datos de tarjeta."""

    tipo = "CREDITO"

    def __init__(self, cuotas: int = 1, recargo_por_cuota: Decimal = Decimal("0.03")) -> None:
        self.cuotas = cuotas
        self.recargo_por_cuota = Decimal(str(recargo_por_cuota))

    def calcular_recargo(self, monto: Decimal) -> Decimal:
        return dinero(monto * self.recargo_por_cuota * max(0, self.cuotas - 1))

    def validar(self, datos: dict[str, str]) -> bool:
        return 1 <= self.cuotas <= 12 and bool(datos.get("autorizacion", "").strip())


class Transferencia(MedioPago):
    """Transferencia: requiere registrar una referencia bancaria (P7)."""

    tipo = "TRANSFERENCIA"

    def calcular_recargo(self, monto: Decimal) -> Decimal:
        return Decimal("0.00")

    def validar(self, datos: dict[str, str]) -> bool:
        return bool(datos.get("referencia", "").strip())


def crear_medio_pago(tipo: str, cuotas: int = 1) -> MedioPago:
    """Crea la estrategia solicitada para un cobro mixto o individual (P7)."""
    estrategias: dict[str, type[MedioPago]] = {
        "EFECTIVO": Efectivo,
        "DEBITO": TarjetaDebito,
        "CREDITO": TarjetaCredito,
        "TRANSFERENCIA": Transferencia,
    }
    try:
        estrategia = estrategias[tipo.upper()]
    except KeyError as error:
        raise ValueError(f"Medio de pago no reconocido: {tipo}.") from error
    return TarjetaCredito(cuotas) if estrategia is TarjetaCredito else estrategia()


@dataclass
class Comprobante:
    """Documento numerado por punto de venta asociado a venta o devolución."""

    punto_venta: int
    numero: int
    fecha_emision: datetime
    total: Decimal
    id: int | None = None

    @property
    def tipo(self) -> str:
        return "COMPROBANTE"


class Ticket(Comprobante):
    """Ticket para operaciones sin cliente fiscal responsable inscripto (P7)."""

    @property
    def tipo(self) -> str:
        return "TICKET"


class FacturaA(Comprobante):
    """Factura A para cliente responsable inscripto (P7)."""

    @property
    def tipo(self) -> str:
        return "FACTURA_A"


class FacturaB(Comprobante):
    """Factura B para consumidores finales, monotributistas o exentos (P7)."""

    @property
    def tipo(self) -> str:
        return "FACTURA_B"


class NotaCredito(Comprobante):
    """Comprobante generado por cada devolución aceptada (V5)."""

    @property
    def tipo(self) -> str:
        return "NOTA_CREDITO"


class ComprobanteFactory:
    """Factory que selecciona el tipo fiscal según la condición del cliente."""

    @staticmethod
    def tipo_para_venta(cliente: Cliente | None) -> str:
        if cliente and cliente.condicion_iva == CondicionIva.RESPONSABLE_INSCRIPTO:
            return "FACTURA_A"
        if cliente and not cliente.es_consumidor_final():
            return "FACTURA_B"
        return "TICKET"

    @staticmethod
    def crear_para_venta(
        cliente: Cliente | None,
        punto_venta: int,
        numero: int,
        fecha_emision: datetime,
        total: Decimal,
    ) -> Comprobante:
        """Construye el tipo concreto de comprobante para una venta (Factory)."""
        clases: dict[str, type[Comprobante]] = {
            "TICKET": Ticket,
            "FACTURA_A": FacturaA,
            "FACTURA_B": FacturaB,
        }
        clase = clases[ComprobanteFactory.tipo_para_venta(cliente)]
        return clase(punto_venta, numero, fecha_emision, dinero(total))

    @staticmethod
    def crear_nota_credito(
        punto_venta: int, numero: int, fecha_emision: datetime, total: Decimal
    ) -> NotaCredito:
        """Construye la nota de crédito correlativa que exige V5."""
        return NotaCredito(punto_venta, numero, fecha_emision, dinero(total))


@dataclass
class MovimientoCaja:
    """Ingreso o egreso de caja enlazado con un cobro o devolución (P7)."""

    tipo: str
    monto: Decimal
    concepto: str
    medio_pago: str = ""
    fecha_hora: datetime = field(default_factory=datetime.now)
    id: int | None = None


@dataclass
class Caja:
    """Caja diaria de una sucursal; acumula cobros y reintegros (P7)."""

    ubicacion_id: int
    fecha_apertura: datetime
    saldo_inicial: Decimal
    fecha_cierre: datetime | None = None
    id: int | None = None

    def saldo_actual(self, ingresos: Decimal = Decimal("0.00"), egresos: Decimal = Decimal("0.00")) -> Decimal:
        """Saldo en efectivo contable a partir de movimientos persistidos."""
        return dinero(self.saldo_inicial + ingresos - egresos)


@dataclass
class DetalleDevolucion:
    """Unidades devueltas e indicación explícita de reingreso al stock (V5)."""

    detalle_venta_id: int
    cantidad: int
    reingresa_stock: bool = True
    monto_reintegrado: Decimal = Decimal("0.00")


@dataclass
class Devolucion:
    """Devolución trazable a la venta, con motivo y total de reintegro (V5)."""

    venta_id: int
    fecha_hora: datetime
    motivo: str
    detalles: list[DetalleDevolucion] = field(default_factory=list)
    total_reintegrar: Decimal = Decimal("0.00")
    comprobante: NotaCredito | None = None
    id: int | None = None


@dataclass
class Venta:
    """Venta confirmada con uno o más renglones, cobros y comprobante (P7)."""

    ubicacion_id: int
    numero: int
    fecha_hora: datetime
    vendedor: str
    estado: EstadoVenta = EstadoVenta.CONFIRMADA
    cliente_id: int | None = None
    detalles: list[DetalleVenta] = field(default_factory=list)
    cobros: list[Cobro] = field(default_factory=list)
    comprobante: Comprobante | None = None
    id: int | None = None

    def total(self) -> Decimal:
        """Total final de la venta, incluidos los recargos de sus estrategias de pago."""
        mercaderia = sum((detalle.subtotal() for detalle in self.detalles), Decimal("0.00"))
        recargos = sum((cobro.recargo for cobro in self.cobros), Decimal("0.00"))
        return dinero(mercaderia + recargos)

    def total_cobrado(self) -> Decimal:
        """Importe final cobrado incluyendo recargos y pagos mixtos."""
        return dinero(sum((pago.monto + pago.recargo for pago in self.cobros), Decimal("0.00")))