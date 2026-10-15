"""Patrón **Observer** del inventario (pohlsi).

- Subject:   `StockService` (mantiene la lista de observadores y los notifica).
- Observer:  `ObservadorStock` (interfaz común para ser notificado).

El servicio no sabe qué hace cada observador con el aviso: eso es lo que los
mantiene desacoplados. Se suscriben con `stock_service.suscribir(observador)`.
"""

from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from src.dominio.inventario.modelos import Stock


class ObservadorStock(ABC):
    """Interfaz de quien quiere enterarse de que un producto quedó en su stock mínimo."""

    @abstractmethod
    def stock_bajo_minimo(self, stock: Stock) -> None:
        """Se llama después de un egreso, cuando el disponible llegó al mínimo o quedó por debajo."""


@dataclass(frozen=True)
class AlertaStock:
    producto_id: int
    ubicacion_id: int
    disponible: int
    minimo: int
    faltante: int
    fecha_hora: datetime


class AlertaStockMinimo(ObservadorStock):
    """Guarda una alerta por producto y ubicación para mostrarla en pantalla.

    Si se la crea con `al_alertar`, además llama a esa función en cada aviso
    (la interfaz puede usarla para refrescar un panel o mostrar un mensaje).
    Si un producto vuelve a quedar bajo el mínimo, reemplaza su alerta anterior
    en lugar de acumular avisos repetidos.
    """

    def __init__(self, minimos, al_alertar: Callable[[AlertaStock], None] | None = None) -> None:
        self._minimos = minimos  # StockMinimoService de maestros
        self._al_alertar = al_alertar
        self._alertas: dict[tuple[int, int], AlertaStock] = {}

    def stock_bajo_minimo(self, stock: Stock) -> None:
        minimo = self._minimos.minimo(stock.producto_id, stock.ubicacion_id)
        alerta = AlertaStock(
            producto_id=stock.producto_id,
            ubicacion_id=stock.ubicacion_id,
            disponible=stock.cantidad_disponible,
            minimo=minimo,
            faltante=max(minimo - stock.cantidad_disponible, 0),
            fecha_hora=datetime.now(),
        )
        self._alertas[(stock.producto_id, stock.ubicacion_id)] = alerta
        if self._al_alertar is not None:
            self._al_alertar(alerta)

    def alertas(self) -> list[AlertaStock]:
        """Alertas vigentes, las de mayor faltante primero."""
        return sorted(self._alertas.values(), key=lambda alerta: alerta.faltante, reverse=True)

    def descartar(self, producto_id: int, ubicacion_id: int) -> None:
        self._alertas.pop((producto_id, ubicacion_id), None)

    def limpiar(self) -> None:
        self._alertas.clear()
