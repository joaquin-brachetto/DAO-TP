"""Servicios que usa la aplicación web.

Se crean una sola vez al arrancar y se comparten entre todas las pantallas, igual que hacía
la ventana principal de escritorio. Todos usan la misma conexión (Singleton `BaseDeDatos`) y el
mismo `StockService`, que tiene suscriptos los observadores de stock mínimo (patrón Observer).
"""

from src.excepciones import ValidacionError
from src.persistencia.conexion import BaseDeDatos
from src.servicios.compras_service import ComprasService
from src.servicios.inventario_app import crear_stock_service
from src.servicios.logistica_service import LogisticaService
from src.servicios.maestros_service import (
    CategoriaService,
    ProductoService,
    ProveedorService,
    StockMinimoService,
    UbicacionService,
)
from src.servicios.reposicion_service import ReposicionService
from src.servicios.tablero_service import TableroService
from src.servicios.ventas_service import VentasService


class Servicios:
    def __init__(self, db: BaseDeDatos) -> None:
        self.db = db
        self.stock, self.alertas = crear_stock_service(db)
        self.ubicaciones = UbicacionService(db)
        self.categorias = CategoriaService(db)
        self.productos = ProductoService(db)
        self.minimos = StockMinimoService(db)
        self.proveedores = ProveedorService(db)
        self.reposicion = ReposicionService(db)
        self.compras = ComprasService(db, self.stock)
        self.logistica = LogisticaService(db, self.stock, self.reposicion)
        self.ventas = VentasService(db, self.stock)
        self.tablero = TableroService(db, self.stock, self.logistica, self.reposicion)

    def centro_distribucion(self):
        """El Centro de Distribución activo (las compras se reciben ahí)."""
        centro = next((u for u in self.ubicaciones.listar() if u.es_centro_distribucion()), None)
        if centro is None:
            raise ValidacionError("No hay un Centro de Distribución activo. Cargalo en Administración.")
        return centro
