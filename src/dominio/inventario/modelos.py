"""Clases de dominio de inventario (pohlsi): stock, movimientos, compras y reposición.

El stock de un producto en una ubicación se reparte en tres "baldes":

    pendiente  -> llegó o va en camino, pero todavía no se verificó (no se puede vender)
    disponible -> verificado, se puede vender (V1 y V3)
    merma      -> rechazado (precinto roto)

Cada cambio de stock deja un `MovimientoStock`, que nunca se modifica.
"""

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum


class TipoMovimiento(StrEnum):
    INGRESO_COMPRA = "INGRESO_COMPRA"                  # el proveedor entrega al CD: sube disponible del CD
    EGRESO_DESPACHO = "EGRESO_DESPACHO"                # el CD despacha un bulto: baja disponible del CD
    INGRESO_PENDIENTE = "INGRESO_PENDIENTE"            # llega al local, sin verificar: sube pendiente
    CONFIRMACION_VERIFICADO = "CONFIRMACION_VERIFICADO"  # bulto verificado: pendiente -> disponible
    MERMA_RECHAZO = "MERMA_RECHAZO"                    # bulto rechazado: pendiente -> merma
    EGRESO_VENTA = "EGRESO_VENTA"                      # venta: baja disponible
    REINGRESO_DEVOLUCION = "REINGRESO_DEVOLUCION"      # devolución: sube disponible
    AJUSTE = "AJUSTE"                                  # reservado para inventarios físicos (opcional)


@dataclass(frozen=True)
class Referencia:
    """Documento que originó un movimiento de stock (el `ref` del contrato de `StockService`).

        Referencia("VENTA", venta_id)
        Referencia("REMITO", remito_id, usuario="turco")
    """

    tipo_documento: str
    documento_id: int | None = None
    usuario: str = "sistema"


@dataclass
class Stock:
    producto_id: int
    ubicacion_id: int
    cantidad_disponible: int = 0
    cantidad_pendiente: int = 0
    cantidad_merma: int = 0
    id: int | None = None

    def hay_disponible(self, cantidad: int) -> bool:
        """¿Alcanza el stock verificado para entregar `cantidad` unidades?"""
        return 0 < cantidad <= self.cantidad_disponible


@dataclass
class MovimientoStock:
    stock_id: int
    tipo: TipoMovimiento
    cantidad: int
    costo_unitario: Decimal
    tipo_documento: str
    fecha_hora: datetime
    documento_id: int | None = None
    usuario: str = "sistema"
    id: int | None = None


# --- Compras (proveedor -> CD) -------------------------------------------------------------


class EstadoOrdenCompra(StrEnum):
    PENDIENTE = "PENDIENTE"
    RECIBIDA = "RECIBIDA"
    ANULADA = "ANULADA"


@dataclass
class DetalleOrdenCompra:
    producto_id: int
    cantidad: int
    costo_unitario: Decimal
    id: int | None = None
    orden_compra_id: int | None = None

    def subtotal(self) -> Decimal:
        return self.costo_unitario * self.cantidad


@dataclass
class OrdenCompra:
    numero: int
    proveedor_id: int
    destino_id: int  # Centro de Distribución que recibe la mercadería
    fecha_emision: date
    estado: EstadoOrdenCompra = EstadoOrdenCompra.PENDIENTE
    detalles: list[DetalleOrdenCompra] = field(default_factory=list)
    id: int | None = None

    def total(self) -> Decimal:
        return sum((detalle.subtotal() for detalle in self.detalles), Decimal("0"))


# --- Reposición (CD -> sucursal) ------------------------------------------------------------


class OrigenNecesidad(StrEnum):
    MANUAL = "MANUAL"
    AUTOMATICA = "AUTOMATICA"  # la generó el Observer al bajar del stock mínimo


class EstadoNecesidad(StrEnum):
    PENDIENTE = "PENDIENTE"
    CONSOLIDADA = "CONSOLIDADA"  # ya forma parte de una orden de reposición
    ANULADA = "ANULADA"


class EstadoOrdenReposicion(StrEnum):
    PENDIENTE = "PENDIENTE"
    EN_PREPARACION = "EN_PREPARACION"
    DESPACHADA = "DESPACHADA"
    CERRADA_COMPLETA = "CERRADA_COMPLETA"
    CERRADA_CON_FALTANTES = "CERRADA_CON_FALTANTES"


NOMBRES_ESTADO = {
    "PENDIENTE": "Pendiente",
    "RECIBIDA": "Recibida",
    "ANULADA": "Anulada",
    "CONSOLIDADA": "Consolidada",
    "EN_PREPARACION": "En preparación",
    "DESPACHADA": "Despachada",
    "CERRADA_COMPLETA": "Cerrada completa",
    "CERRADA_CON_FALTANTES": "Cerrada con faltantes",
}


def nombre_estado(estado: StrEnum | str) -> str:
    """Estado para mostrar al usuario: EN_PREPARACION -> «En preparación»."""
    return NOMBRES_ESTADO.get(str(estado), str(estado))


@dataclass
class DetalleNecesidad:
    producto_id: int
    cantidad_solicitada: int
    id: int | None = None
    necesidad_reposicion_id: int | None = None


@dataclass
class NecesidadReposicion:
    ubicacion_id: int  # sucursal que necesita la mercadería
    fecha: date
    origen: OrigenNecesidad
    estado: EstadoNecesidad = EstadoNecesidad.PENDIENTE
    orden_reposicion_id: int | None = None
    detalles: list[DetalleNecesidad] = field(default_factory=list)
    id: int | None = None


@dataclass
class DetalleOrdenReposicion:
    producto_id: int
    cantidad_solicitada: int
    cantidad_preparada: int = 0  # la arma el CD (empaquetado)
    cantidad_recibida: int = 0   # unidades verificadas en el local
    id: int | None = None
    orden_reposicion_id: int | None = None

    def faltante(self) -> int:
        return max(self.cantidad_solicitada - self.cantidad_recibida, 0)


@dataclass
class OrdenReposicion:
    numero: int
    fecha_emision: datetime
    origen_id: int   # Centro de Distribución
    destino_id: int  # sucursal
    estado: EstadoOrdenReposicion = EstadoOrdenReposicion.PENDIENTE
    detalles: list[DetalleOrdenReposicion] = field(default_factory=list)
    id: int | None = None

    def esta_completa(self) -> bool:
        """¿Se recibió y verificó todo lo que se pidió?"""
        return all(detalle.faltante() == 0 for detalle in self.detalles)
