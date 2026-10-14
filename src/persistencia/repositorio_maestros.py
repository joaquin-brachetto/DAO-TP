"""Repositorios de maestros (brache)."""

from datetime import datetime
from typing import Any

from src.dominio.maestros.modelos import (
    Categoria,
    CentroDistribucion,
    HistorialPrecio,
    Producto,
    ProductoProveedor,
    Proveedor,
    StockMinimo,
    Sucursal,
    TipoUbicacion,
    Ubicacion,
)
from src.persistencia.conexion import BaseDeDatos
from src.persistencia.repositorio_base import RepositorioBase


class UbicacionRepositorio(RepositorioBase[Ubicacion]):
    """Sucursales y Centro de Distribución comparten la tabla `ubicacion` (columna `tipo`)."""

    tabla = "ubicacion"
    entidad = Ubicacion
    campo_activo = "activa"
    orden = "tipo, nombre"

    def _a_entidad(self, fila) -> Ubicacion:
        comunes = dict(
            id=fila["id"],
            codigo=fila["codigo"],
            nombre=fila["nombre"],
            direccion=fila["direccion"],
            telefono=fila["telefono"],
            activa=bool(fila["activa"]),
        )
        if fila["tipo"] == TipoUbicacion.CD:
            return CentroDistribucion(capacidad_m3=fila["capacidad_m3"], **comunes)
        return Sucursal(punto_venta=fila["punto_venta"], **comunes)

    def _a_fila(self, ubicacion: Ubicacion) -> dict[str, Any]:
        return {
            "tipo": str(ubicacion.tipo),
            "codigo": ubicacion.codigo,
            "nombre": ubicacion.nombre,
            "direccion": ubicacion.direccion,
            "telefono": ubicacion.telefono,
            "punto_venta": getattr(ubicacion, "punto_venta", None),
            "capacidad_m3": getattr(ubicacion, "capacidad_m3", None),
            "activa": ubicacion.activa,
        }

    def listar_sucursales(self, incluir_inactivas: bool = False) -> list[Sucursal]:
        return [u for u in self.listar(incluir_inactivas) if u.tipo == TipoUbicacion.SUCURSAL]

    def listar_centros(self, incluir_inactivos: bool = False) -> list[CentroDistribucion]:
        return [u for u in self.listar(incluir_inactivos) if u.tipo == TipoUbicacion.CD]


class CategoriaRepositorio(RepositorioBase[Categoria]):
    tabla = "categoria"
    entidad = Categoria
    orden = "nombre"


class ProductoRepositorio(RepositorioBase[Producto]):
    tabla = "producto"
    entidad = Producto
    campo_activo = "activo"
    orden = "nombre"

    def buscar_texto(self, texto: str, incluir_inactivos: bool = False) -> list[Producto]:
        """Productos cuyo SKU, nombre o código de barras contiene el texto."""
        patron = f"%{texto.strip()}%"
        sql = "SELECT * FROM producto WHERE (sku LIKE ? OR nombre LIKE ? OR codigo_barras LIKE ?)"
        if not incluir_inactivos:
            sql += " AND activo = 1"
        filas = self.db.consultar(sql + " ORDER BY nombre", (patron, patron, patron))
        return [self._a_entidad(fila) for fila in filas]


class HistorialPrecioRepositorio(RepositorioBase[HistorialPrecio]):
    tabla = "historial_precio"
    entidad = HistorialPrecio
    orden = "fecha_desde DESC, id DESC"

    def vigente(self, producto_id: int) -> HistorialPrecio | None:
        return self.buscar_uno_por(producto_id=producto_id, fecha_hasta=None)

    def de_producto(self, producto_id: int) -> list[HistorialPrecio]:
        """Historial completo, del más reciente al más antiguo."""
        return self.buscar_por(producto_id=producto_id)

    def vigente_en(self, producto_id: int, momento: datetime) -> HistorialPrecio | None:
        """Costo y precio que tenía el producto en un momento dado."""
        fila = self.db.consultar_uno(
            "SELECT * FROM historial_precio WHERE producto_id = ? AND fecha_desde <= ? "
            "AND (fecha_hasta IS NULL OR fecha_hasta > ?) ORDER BY fecha_desde DESC LIMIT 1",
            (producto_id, momento, momento),
        )
        return self._a_entidad(fila) if fila else None


class ProveedorRepositorio(RepositorioBase[Proveedor]):
    tabla = "proveedor"
    entidad = Proveedor
    campo_activo = "activo"
    orden = "razon_social"


class ProductoProveedorRepositorio:
    """Relación muchos a muchos producto–proveedor. La clave es el par (producto, proveedor)."""

    def __init__(self, db: BaseDeDatos | None = None) -> None:
        self.db = db or BaseDeDatos()

    def _a_entidad(self, fila) -> ProductoProveedor:
        return ProductoProveedor(
            producto_id=fila["producto_id"],
            proveedor_id=fila["proveedor_id"],
            codigo_en_proveedor=fila["codigo_en_proveedor"],
            costo_pactado=fila["costo_pactado"],
            plazo_entrega_dias=fila["plazo_entrega_dias"],
        )

    def guardar(self, relacion: ProductoProveedor) -> ProductoProveedor:
        """Asigna el proveedor al producto, o actualiza las condiciones si ya estaba asignado."""
        self.db.ejecutar(
            "INSERT INTO producto_proveedor "
            "(producto_id, proveedor_id, codigo_en_proveedor, costo_pactado, plazo_entrega_dias) "
            "VALUES (?, ?, ?, ?, ?) "
            "ON CONFLICT (producto_id, proveedor_id) DO UPDATE SET "
            "codigo_en_proveedor = excluded.codigo_en_proveedor, "
            "costo_pactado = excluded.costo_pactado, "
            "plazo_entrega_dias = excluded.plazo_entrega_dias",
            (
                relacion.producto_id,
                relacion.proveedor_id,
                relacion.codigo_en_proveedor,
                relacion.costo_pactado,
                relacion.plazo_entrega_dias,
            ),
        )
        return relacion

    def eliminar(self, producto_id: int, proveedor_id: int) -> bool:
        cursor = self.db.ejecutar(
            "DELETE FROM producto_proveedor WHERE producto_id = ? AND proveedor_id = ?",
            (producto_id, proveedor_id),
        )
        return cursor.rowcount > 0

    def de_producto(self, producto_id: int) -> list[ProductoProveedor]:
        filas = self.db.consultar(
            "SELECT pp.* FROM producto_proveedor pp JOIN proveedor p ON p.id = pp.proveedor_id "
            "WHERE pp.producto_id = ? ORDER BY p.razon_social",
            (producto_id,),
        )
        return [self._a_entidad(fila) for fila in filas]

    def de_proveedor(self, proveedor_id: int) -> list[ProductoProveedor]:
        filas = self.db.consultar(
            "SELECT pp.* FROM producto_proveedor pp JOIN producto p ON p.id = pp.producto_id "
            "WHERE pp.proveedor_id = ? ORDER BY p.nombre",
            (proveedor_id,),
        )
        return [self._a_entidad(fila) for fila in filas]


class StockMinimoRepositorio:
    """Mínimo de cada producto en cada ubicación. La clave es el par (producto, ubicación)."""

    def __init__(self, db: BaseDeDatos | None = None) -> None:
        self.db = db or BaseDeDatos()

    def _a_entidad(self, fila) -> StockMinimo:
        return StockMinimo(fila["producto_id"], fila["ubicacion_id"], fila["cantidad_minima"])

    def guardar(self, minimo: StockMinimo) -> StockMinimo:
        """Define el mínimo, o lo reemplaza si ya había uno para ese producto y ubicación."""
        self.db.ejecutar(
            "INSERT INTO stock_minimo (producto_id, ubicacion_id, cantidad_minima) VALUES (?, ?, ?) "
            "ON CONFLICT (producto_id, ubicacion_id) DO UPDATE SET cantidad_minima = excluded.cantidad_minima",
            (minimo.producto_id, minimo.ubicacion_id, minimo.cantidad_minima),
        )
        return minimo

    def eliminar(self, producto_id: int, ubicacion_id: int) -> bool:
        cursor = self.db.ejecutar(
            "DELETE FROM stock_minimo WHERE producto_id = ? AND ubicacion_id = ?", (producto_id, ubicacion_id)
        )
        return cursor.rowcount > 0

    def obtener(self, producto_id: int, ubicacion_id: int) -> StockMinimo | None:
        fila = self.db.consultar_uno(
            "SELECT * FROM stock_minimo WHERE producto_id = ? AND ubicacion_id = ?", (producto_id, ubicacion_id)
        )
        return self._a_entidad(fila) if fila else None

    def de_producto(self, producto_id: int) -> list[StockMinimo]:
        filas = self.db.consultar(
            "SELECT sm.* FROM stock_minimo sm JOIN ubicacion u ON u.id = sm.ubicacion_id "
            "WHERE sm.producto_id = ? ORDER BY u.tipo, u.nombre",
            (producto_id,),
        )
        return [self._a_entidad(fila) for fila in filas]

    def de_ubicacion(self, ubicacion_id: int) -> list[StockMinimo]:
        filas = self.db.consultar("SELECT * FROM stock_minimo WHERE ubicacion_id = ?", (ubicacion_id,))
        return [self._a_entidad(fila) for fila in filas]
