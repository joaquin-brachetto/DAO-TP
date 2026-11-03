"""Patrón **Observer** del inventario.

- Subject:   `SujetoStock` mantiene la lista de observadores y los notifica.
             `StockService` hereda de él.
- Observer:  `ObservadorStock` es la interfaz común para ser notificado.
             `AlertaStockMinimo` y `GeneradorNecesidades` la implementan.

El sujeto no sabe qué hace cada observador con el aviso: eso es lo que los
mantiene desacoplados (relación 1 a N sin dependencia rígida). Se suscriben con
`stock_service.suscribir(observador)`.
"""

import logging
from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from src.dominio.inventario.modelos import Stock

registro = logging.getLogger(__name__)


class ObservadorStock(ABC):
    """Observer: interfaz de quien quiere enterarse de que un producto quedó en su stock mínimo."""

    @abstractmethod
    def stock_bajo_minimo(self, stock: Stock) -> None:
        """Se llama después de un egreso, cuando el disponible llegó al mínimo o quedó por debajo."""


class SujetoStock:
    """Subject: mantiene la lista de observadores y les avisa cuando un producto llega a su mínimo."""

    def __init__(self) -> None:
        self._observadores: list[ObservadorStock] = []

    def suscribir(self, observador: ObservadorStock) -> None:
        if observador not in self._observadores:
            self._observadores.append(observador)

    def desuscribir(self, observador: ObservadorStock) -> None:
        if observador in self._observadores:
            self._observadores.remove(observador)

    def notificar(self, stock: Stock) -> None:
        for observador in list(self._observadores):
            try:
                observador.stock_bajo_minimo(stock)
            except Exception:  # un observador con problemas no debe frenar una venta o un despacho
                registro.exception("Falló el observador %r al notificar stock bajo el mínimo", observador)


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
