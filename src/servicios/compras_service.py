"""Compras a proveedores (pohlsi): la mercadería entra al Centro de Distribución.

Sin compras el CD no tendría stock para reponer a los locales. El flujo es:

    crear_orden(proveedor, CD, renglones)  ->  orden PENDIENTE
    recibir_orden(orden)                   ->  RECIBIDA: sube el disponible del CD (StockService)
    anular_orden(orden)                    ->  ANULADA (solo si todavía está PENDIENTE)

Al recibir, todos los ingresos de stock y el cambio de estado se hacen en una
sola transacción: si algo falla, no queda nada a medias.
"""

from collections.abc import Iterable
from datetime import date
from decimal import Decimal

from src.dominio.inventario.modelos import DetalleOrdenCompra, EstadoOrdenCompra, OrdenCompra, Referencia
from src.excepciones import EntidadNoEncontradaError, ValidacionError
from src.persistencia.conexion import BaseDeDatos
from src.persistencia.repositorio_inventario import (
    DetalleOrdenCompraRepositorio,
    LecturaMaestros,
    OrdenCompraRepositorio,
)
from src.servicios.stock_service import StockService
from src.servicios.validaciones_inventario import decimal_no_negativo, entero_positivo


class ComprasService:
    def __init__(self, db: BaseDeDatos | None = None, stock_service: StockService | None = None) -> None:
        self.db = db or BaseDeDatos()
        self._ordenes = OrdenCompraRepositorio(self.db)
        self._detalles = DetalleOrdenCompraRepositorio(self.db)
        self._maestros = LecturaMaestros(self.db)
        self._stock = stock_service or StockService(self.db)

    # --- Consultas -------------------------------------------------------------------

    def obtener(self, orden_id: int) -> OrdenCompra:
        orden = self._ordenes.obtener(orden_id)
        orden.detalles = self._detalles.de_orden(orden_id)
        return orden

    def listar(self, estado: EstadoOrdenCompra | None = None) -> list[OrdenCompra]:
        ordenes = self._ordenes.buscar_por(estado=str(estado)) if estado else self._ordenes.listar()
        for orden in ordenes:
            orden.detalles = self._detalles.de_orden(orden.id)
        return ordenes

    # --- Operaciones --------------------------------------------------------------------

    def crear_orden(
        self,
        proveedor_id: int,
        destino_id: int,
        renglones: Iterable[tuple[int, int, Decimal]],
        fecha: date | None = None,
    ) -> OrdenCompra:
        """Crea una orden PENDIENTE. Cada renglón es `(producto_id, cantidad, costo_unitario)`."""
        proveedor = self._maestros.proveedor(proveedor_id)
        if proveedor is None:
            raise EntidadNoEncontradaError(f"No existe un proveedor con id {proveedor_id}.")
        if not proveedor["activo"]:
            raise ValidacionError(f"El proveedor «{proveedor['razon_social']}» está dado de baja.")
        destino = self._maestros.ubicacion(destino_id)
        if destino is None:
            raise EntidadNoEncontradaError(f"No existe una ubicación con id {destino_id}.")
        if destino["tipo"] != "CD" or not destino["activa"]:
            raise ValidacionError("Las compras se reciben en el Centro de Distribución activo.")
        detalles = self._armar_detalles(renglones)

        with self.db.transaccion():
            orden = OrdenCompra(
                numero=self._maestros.proximo_numero("orden_compra"),
                proveedor_id=proveedor_id,
                destino_id=destino_id,
                fecha_emision=fecha or date.today(),
            )
            self._ordenes.guardar(orden)
            for detalle in detalles:
                detalle.orden_compra_id = orden.id
                self._detalles.guardar(detalle)
            orden.detalles = detalles
        return orden

    def recibir_orden(self, orden_id: int, usuario: str = "sistema") -> OrdenCompra:
        """La mercadería llegó al CD: sube el disponible de cada producto y la orden queda RECIBIDA."""
        with self.db.transaccion():
            orden = self.obtener(orden_id)
            self._exigir_pendiente(orden, "recibir")
            referencia = Referencia("ORDEN_COMPRA", orden.id, usuario)
            for detalle in orden.detalles:
                self._stock.ingresar_compra(
                    orden.destino_id, detalle.producto_id, detalle.cantidad, referencia, detalle.costo_unitario
                )
            orden.estado = EstadoOrdenCompra.RECIBIDA
            self._ordenes.guardar(orden)
        return orden

    def anular_orden(self, orden_id: int) -> OrdenCompra:
        with self.db.transaccion():
            orden = self.obtener(orden_id)
            self._exigir_pendiente(orden, "anular")
            orden.estado = EstadoOrdenCompra.ANULADA
            self._ordenes.guardar(orden)
        return orden

    # --- Internos ---------------------------------------------------------------------------

    @staticmethod
    def _exigir_pendiente(orden: OrdenCompra, accion: str) -> None:
        if orden.estado != EstadoOrdenCompra.PENDIENTE:
            raise ValidacionError(
                f"No se puede {accion} la orden de compra {orden.numero}: está {orden.estado}, "
                "solo se pueden modificar las PENDIENTES."
            )

    def _armar_detalles(self, renglones: Iterable[tuple[int, int, Decimal]]) -> list[DetalleOrdenCompra]:
        detalles: list[DetalleOrdenCompra] = []
        vistos: set[int] = set()
        for producto_id, cantidad, costo in renglones:
            producto = self._maestros.producto(producto_id)
            if producto is None:
                raise EntidadNoEncontradaError(f"No existe un producto con id {producto_id}.")
            if not producto["activo"]:
                raise ValidacionError(f"El producto «{producto['nombre']}» está dado de baja.")
            if producto_id in vistos:
                raise ValidacionError(f"El producto «{producto['nombre']}» está repetido en la orden.")
            vistos.add(producto_id)
            detalles.append(
                DetalleOrdenCompra(
                    producto_id=producto_id,
                    cantidad=entero_positivo(cantidad),
                    costo_unitario=decimal_no_negativo(costo),
                )
            )
        if not detalles:
            raise ValidacionError("La orden de compra necesita al menos un producto.")
        return detalles
