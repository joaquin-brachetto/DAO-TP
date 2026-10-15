"""Armado del inventario para la aplicación (pohlsi).

La ventana principal crea UN `StockService` y lo comparte con todas las pantallas
(ventas, reportes, inventario) como `ventana.stock_service`. Acá se le suscriben
los dos observadores del patrón **Observer**:

- `AlertaStockMinimo`: guarda la alerta y avisa a la interfaz (barra de estado).
- `GeneradorNecesidades`: crea la necesidad de reposición automática del local.
"""

from collections.abc import Callable

from src.persistencia.conexion import BaseDeDatos
from src.servicios.generador_necesidades import GeneradorNecesidades
from src.servicios.observadores_stock import AlertaStock, AlertaStockMinimo
from src.servicios.reposicion_service import ReposicionService
from src.servicios.stock_service import StockService


def crear_stock_service(
    db: BaseDeDatos | None = None, al_alertar: Callable[[AlertaStock], None] | None = None
) -> tuple[StockService, AlertaStockMinimo]:
    """Devuelve el StockService con sus observadores suscriptos, y el observador de alertas."""
    db = db or BaseDeDatos()
    stock_service = StockService(db)
    alertas = AlertaStockMinimo(stock_service.minimos, al_alertar)
    stock_service.suscribir(alertas)
    stock_service.suscribir(GeneradorNecesidades(ReposicionService(db)))
    return stock_service, alertas


def describir_alerta(alerta: AlertaStock, db: BaseDeDatos | None = None) -> str:
    """Texto para mostrar al usuario: «⚠ Stock mínimo: Café (Sucursal Centro): quedan 4, mínimo 5»."""
    db = db or BaseDeDatos()
    producto = db.consultar_uno("SELECT nombre FROM producto WHERE id = ?", (alerta.producto_id,))
    ubicacion = db.consultar_uno("SELECT nombre FROM ubicacion WHERE id = ?", (alerta.ubicacion_id,))
    return (
        f"⚠ Stock mínimo: {producto['nombre'] if producto else alerta.producto_id} "
        f"({ubicacion['nombre'] if ubicacion else alerta.ubicacion_id}): "
        f"quedan {alerta.disponible}, mínimo {alerta.minimo}"
    )
