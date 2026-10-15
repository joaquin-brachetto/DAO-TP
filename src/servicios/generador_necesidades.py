"""Segundo observador del stock (pohlsi): crea la necesidad de reposición automática.

Cuando una sucursal queda en su stock mínimo, `StockService` (el Subject) lo
notifica y este observador genera una `NecesidadReposicion` con origen AUTOMATICA.

- Solo reacciona a sucursales: si es el CD el que baja del mínimo, lo que hace
  falta es una compra al proveedor, no una reposición.
- No duplica: si la sucursal ya tiene una necesidad sin consolidar que pide ese producto, no crea otra.
"""

from src.dominio.inventario.modelos import OrigenNecesidad, Stock
from src.persistencia.repositorio_inventario import LecturaMaestros
from src.servicios.observadores_stock import ObservadorStock
from src.servicios.reposicion_service import ReposicionService


class GeneradorNecesidades(ObservadorStock):
    def __init__(self, reposicion: ReposicionService) -> None:
        self._reposicion = reposicion
        self._maestros = LecturaMaestros(reposicion.db)

    def stock_bajo_minimo(self, stock: Stock) -> None:
        ubicacion = self._maestros.ubicacion(stock.ubicacion_id)
        if ubicacion is None or ubicacion["tipo"] != "SUCURSAL":
            return
        if self._reposicion.hay_necesidad_abierta(stock.ubicacion_id, stock.producto_id):
            return
        renglones = self._reposicion.sugerir_necesidad(stock.ubicacion_id, stock.producto_id)
        if renglones:
            self._reposicion.crear_necesidad(stock.ubicacion_id, renglones, origen=OrigenNecesidad.AUTOMATICA)
