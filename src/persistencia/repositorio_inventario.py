"""Repositorios de inventario, compras y reposición (pohlsi)."""

from dataclasses import fields
from typing import Any, TypeVar

from src.dominio.inventario.modelos import (
    DetalleNecesidad,
    DetalleOrdenCompra,
    DetalleOrdenReposicion,
    EstadoNecesidad,
    EstadoOrdenCompra,
    EstadoOrdenReposicion,
    MovimientoStock,
    NecesidadReposicion,
    OrdenCompra,
    OrdenReposicion,
    OrigenNecesidad,
    Stock,
    TipoMovimiento,
)
from src.persistencia.conexion import BaseDeDatos
from src.persistencia.repositorio_base import RepositorioBase

T = TypeVar("T")


class StockRepositorio(RepositorioBase[Stock]):
    """Una fila por producto y ubicación, con sus tres cantidades."""

    tabla = "stock"
    entidad = Stock
    orden = "ubicacion_id, producto_id"

    def de(self, ubicacion_id: int, producto_id: int) -> Stock | None:
        return self.buscar_uno_por(ubicacion_id=ubicacion_id, producto_id=producto_id)

    def de_ubicacion(self, ubicacion_id: int) -> list[Stock]:
        return self.buscar_por(ubicacion_id=ubicacion_id)


class MovimientoStockRepositorio(RepositorioBase[MovimientoStock]):
    """Libro de movimientos. Solo se inserta: la base rechaza UPDATE y DELETE."""

    tabla = "movimiento_stock"
    entidad = MovimientoStock
    orden = "fecha_hora, id"

    def _a_entidad(self, fila) -> MovimientoStock:
        return MovimientoStock(
            id=fila["id"],
            stock_id=fila["stock_id"],
            fecha_hora=fila["fecha_hora"],
            tipo=TipoMovimiento(fila["tipo"]),
            cantidad=fila["cantidad"],
            costo_unitario=fila["costo_unitario"],
            tipo_documento=fila["tipo_documento"],
            documento_id=fila["documento_id"],
            usuario=fila["usuario"],
        )

    def _a_fila(self, movimiento: MovimientoStock) -> dict[str, Any]:
        datos = super()._a_fila(movimiento)
        datos["tipo"] = str(movimiento.tipo)
        return datos

    def de_stock(self, stock_id: int) -> list[MovimientoStock]:
        return self.buscar_por(stock_id=stock_id)


# --- Documentos con renglones (orden de compra, necesidad y orden de reposición) -------------
# Cada documento tiene un repositorio para su cabecera y otro para sus renglones.
# El servicio los guarda juntos dentro de una transacción.


class _RepositorioDeCabecera(RepositorioBase[T]):
    """Cabecera de un documento: no guarda la lista `detalles` y convierte los estados a Enum."""

    enums: dict[str, type] = {}
    """Columna -> Enum que la representa en Python."""

    def _a_entidad(self, fila) -> T:
        columnas = fila.keys()
        datos = {campo.name: fila[campo.name] for campo in fields(self.entidad) if campo.name in columnas}
        for columna, enum in self.enums.items():
            datos[columna] = enum(datos[columna])
        return self.entidad(**datos)

    def _a_fila(self, documento: T) -> dict[str, Any]:
        datos = {
            campo.name: getattr(documento, campo.name)
            for campo in fields(self.entidad)
            if campo.name not in ("id", "detalles")
        }
        for columna in self.enums:
            datos[columna] = str(datos[columna])
        return datos


class OrdenCompraRepositorio(_RepositorioDeCabecera[OrdenCompra]):
    tabla = "orden_compra"
    entidad = OrdenCompra
    enums = {"estado": EstadoOrdenCompra}
    orden = "numero DESC"


class DetalleOrdenCompraRepositorio(RepositorioBase[DetalleOrdenCompra]):
    tabla = "detalle_orden_compra"
    entidad = DetalleOrdenCompra

    def de_orden(self, orden_compra_id: int) -> list[DetalleOrdenCompra]:
        return self.buscar_por(orden_compra_id=orden_compra_id)


class NecesidadReposicionRepositorio(_RepositorioDeCabecera[NecesidadReposicion]):
    tabla = "necesidad_reposicion"
    entidad = NecesidadReposicion
    enums = {"origen": OrigenNecesidad, "estado": EstadoNecesidad}
    orden = "fecha DESC, id DESC"

    def con_producto_pendiente(self, ubicacion_id: int, producto_id: int) -> bool:
        """¿Hay una necesidad todavía sin consolidar que ya pida este producto para esa sucursal?"""
        fila = self.db.consultar_uno(
            "SELECT 1 FROM necesidad_reposicion n JOIN detalle_necesidad d ON d.necesidad_reposicion_id = n.id "
            "WHERE n.ubicacion_id = ? AND n.estado = 'PENDIENTE' AND d.producto_id = ? LIMIT 1",
            (ubicacion_id, producto_id),
        )
        return fila is not None


class DetalleNecesidadRepositorio(RepositorioBase[DetalleNecesidad]):
    tabla = "detalle_necesidad"
    entidad = DetalleNecesidad

    def de_necesidad(self, necesidad_id: int) -> list[DetalleNecesidad]:
        return self.buscar_por(necesidad_reposicion_id=necesidad_id)


class OrdenReposicionRepositorio(_RepositorioDeCabecera[OrdenReposicion]):
    tabla = "orden_reposicion"
    entidad = OrdenReposicion
    enums = {"estado": EstadoOrdenReposicion}
    orden = "numero DESC"


class DetalleOrdenReposicionRepositorio(RepositorioBase[DetalleOrdenReposicion]):
    tabla = "detalle_orden_reposicion"
    entidad = DetalleOrdenReposicion

    def de_orden(self, orden_reposicion_id: int) -> list[DetalleOrdenReposicion]:
        return self.buscar_por(orden_reposicion_id=orden_reposicion_id)


class LecturaMaestros:
    """Consultas de solo lectura sobre los maestros de brache que necesita inventario.

    No modifica nada de maestros: solo lee lo necesario para validar.
    """

    def __init__(self, db: BaseDeDatos | None = None) -> None:
        self.db = db or BaseDeDatos()

    def producto(self, producto_id: int):
        return self.db.consultar_uno(
            "SELECT id, nombre, costo_actual, activo FROM producto WHERE id = ?", (producto_id,)
        )

    def ubicacion(self, ubicacion_id: int):
        return self.db.consultar_uno("SELECT id, nombre, tipo, activa FROM ubicacion WHERE id = ?", (ubicacion_id,))

    def proveedor(self, proveedor_id: int):
        return self.db.consultar_uno("SELECT id, razon_social, activo FROM proveedor WHERE id = ?", (proveedor_id,))

    def centro_distribucion_activo(self):
        return self.db.consultar_uno("SELECT id, nombre FROM ubicacion WHERE tipo = 'CD' AND activa = 1")

    def proximo_numero(self, tabla: str) -> int:
        """Siguiente número correlativo de `orden_compra` u `orden_reposicion`."""
        if tabla not in ("orden_compra", "orden_reposicion"):
            raise ValueError(f"Tabla sin numeración: {tabla}")
        return int(self.db.consultar_uno(f"SELECT COALESCE(MAX(numero), 0) + 1 AS n FROM {tabla}")["n"])

    def minimos_de_sucursal(self, ubicacion_id: int, producto_id: int | None = None):
        """Productos activos con stock mínimo en la sucursal, junto con su disponible y pendiente actuales."""
        sql = (
            "SELECT sm.producto_id, sm.cantidad_minima, "
            "COALESCE(s.cantidad_disponible, 0) AS disponible, COALESCE(s.cantidad_pendiente, 0) AS pendiente "
            "FROM stock_minimo sm JOIN producto p ON p.id = sm.producto_id "
            "LEFT JOIN stock s ON s.producto_id = sm.producto_id AND s.ubicacion_id = sm.ubicacion_id "
            "WHERE sm.ubicacion_id = ? AND sm.cantidad_minima > 0 AND p.activo = 1"
        )
        parametros: list[Any] = [ubicacion_id]
        if producto_id is not None:
            sql += " AND sm.producto_id = ?"
            parametros.append(producto_id)
        return self.db.consultar(sql + " ORDER BY p.nombre", parametros)
