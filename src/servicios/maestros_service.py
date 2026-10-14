"""Casos de uso de maestros (P1, P2) y validación de duplicados (V4)."""

from collections.abc import Callable
from datetime import datetime

from src.dominio.maestros.modelos import (
    Categoria,
    HistorialPrecio,
    Producto,
    ProductoProveedor,
    Proveedor,
    StockMinimo,
    Sucursal,
    Ubicacion,
    formatear_cuit,
)
from src.excepciones import EntidadDuplicadaError, EntidadEnUsoError, ValidacionError
from src.persistencia.conexion import BaseDeDatos
from src.persistencia.repositorio_maestros import (
    CategoriaRepositorio,
    HistorialPrecioRepositorio,
    ProductoProveedorRepositorio,
    ProductoRepositorio,
    ProveedorRepositorio,
    StockMinimoRepositorio,
    UbicacionRepositorio,
)

# --- P1: sucursales y Centro de Distribución ---------------------------------------------


class UbicacionService:
    def __init__(self, db: BaseDeDatos | None = None) -> None:
        self.db = db or BaseDeDatos()
        self.repo = UbicacionRepositorio(self.db)

    def listar(self, incluir_inactivas: bool = False) -> list[Ubicacion]:
        return self.repo.listar(incluir_inactivas)

    def listar_sucursales(self, incluir_inactivas: bool = False) -> list[Sucursal]:
        return self.repo.listar_sucursales(incluir_inactivas)

    def obtener(self, ubicacion_id: int) -> Ubicacion:
        return self.repo.obtener(ubicacion_id)

    def guardar(self, ubicacion: Ubicacion) -> Ubicacion:
        """Da de alta (sin id) o modifica (con id) una sucursal o el CD."""
        ubicacion.validar()
        if ubicacion.id is not None and self.repo.obtener(ubicacion.id).tipo != ubicacion.tipo:
            raise ValidacionError("No se puede cambiar una sucursal a Centro de Distribución ni al revés.")
        if self.repo.existe(codigo=ubicacion.codigo, excluir_id=ubicacion.id):
            raise EntidadDuplicadaError(f"Ya existe una ubicación con el código {ubicacion.codigo}.")
        if isinstance(ubicacion, Sucursal) and self.repo.existe(
            punto_venta=ubicacion.punto_venta, excluir_id=ubicacion.id
        ):
            raise EntidadDuplicadaError(f"El punto de venta {ubicacion.punto_venta} ya lo usa otra sucursal.")
        if ubicacion.es_centro_distribucion() and ubicacion.activa:
            self._validar_unico_cd(ubicacion.id)
        return self.repo.guardar(ubicacion)

    def dar_de_baja(self, ubicacion_id: int) -> None:
        self.repo.eliminar(ubicacion_id)

    def reactivar(self, ubicacion_id: int) -> Ubicacion:
        ubicacion = self.repo.obtener(ubicacion_id)
        ubicacion.activa = True
        return self.guardar(ubicacion)

    def _validar_unico_cd(self, excluir_id: int | None) -> None:
        # La consigna describe un único Centro de Distribución central.
        if self.repo.existe(tipo="CD", activa=True, excluir_id=excluir_id):
            raise ValidacionError("Ya hay un Centro de Distribución activo; el sistema trabaja con uno solo.")


# --- P2: categorías --------------------------------------------------------------------------


class CategoriaService:
    def __init__(self, db: BaseDeDatos | None = None) -> None:
        self.db = db or BaseDeDatos()
        self.repo = CategoriaRepositorio(self.db)
        self.productos = ProductoRepositorio(self.db)

    def listar(self) -> list[Categoria]:
        return self.repo.listar()

    def guardar(self, categoria: Categoria) -> Categoria:
        categoria.validar()
        # La columna tiene COLLATE NOCASE: "bebidas" y "Bebidas" se consideran iguales.
        repetida = self.repo.buscar_uno_por(nombre=categoria.nombre)
        if repetida is not None and repetida.id != categoria.id:
            raise EntidadDuplicadaError(f"Ya existe la categoría «{repetida.nombre}».")
        return self.repo.guardar(categoria)

    def eliminar(self, categoria_id: int) -> None:
        cantidad = len(self.productos.buscar_por(categoria_id=categoria_id))
        if cantidad:
            raise EntidadEnUsoError(
                f"No se puede eliminar la categoría: tiene {cantidad} producto(s) asociados "
                "(incluidos los dados de baja)."
            )
        self.repo.eliminar(categoria_id)


# --- P2: productos, precios y proveedores de cada producto ------------------------------------


class ProductoService:
    def __init__(self, db: BaseDeDatos | None = None, ahora: Callable[[], datetime] = datetime.now) -> None:
        self.db = db or BaseDeDatos()
        self.repo = ProductoRepositorio(self.db)
        self.categorias = CategoriaRepositorio(self.db)
        self.historial = HistorialPrecioRepositorio(self.db)
        self.proveedores = ProveedorRepositorio(self.db)
        self.producto_proveedor = ProductoProveedorRepositorio(self.db)
        self._ahora = ahora

    def listar(self, incluir_inactivos: bool = False) -> list[Producto]:
        return self.repo.listar(incluir_inactivos)

    def buscar(self, texto: str, incluir_inactivos: bool = False) -> list[Producto]:
        return self.repo.buscar_texto(texto, incluir_inactivos)

    def obtener(self, producto_id: int) -> Producto:
        return self.repo.obtener(producto_id)

    def guardar(self, producto: Producto) -> Producto:
        """Alta o modificación. Cada cambio de costo o precio queda en el historial."""
        producto.validar()
        if self.categorias.obtener_por_id(producto.categoria_id) is None:
            raise ValidacionError("La categoría elegida no existe.")
        self._validar_duplicados(producto)

        with self.db.transaccion():
            anterior = self.repo.obtener(producto.id) if producto.id is not None else None
            self.repo.guardar(producto)
            if anterior is None or (anterior.costo_actual, anterior.precio_venta_actual) != (
                producto.costo_actual,
                producto.precio_venta_actual,
            ):
                self._registrar_precio(producto)
        return producto

    def dar_de_baja(self, producto_id: int) -> None:
        self.repo.eliminar(producto_id)

    def reactivar(self, producto_id: int) -> Producto:
        producto = self.repo.obtener(producto_id)
        producto.activo = True
        return self.guardar(producto)

    def historial_precios(self, producto_id: int) -> list[HistorialPrecio]:
        return self.historial.de_producto(producto_id)

    def precio_vigente_en(self, producto_id: int, momento: datetime) -> HistorialPrecio | None:
        return self.historial.vigente_en(producto_id, momento)

    # Proveedores de cada producto

    def proveedores_de(self, producto_id: int) -> list[ProductoProveedor]:
        return self.producto_proveedor.de_producto(producto_id)

    def asignar_proveedor(self, relacion: ProductoProveedor) -> ProductoProveedor:
        """Agrega un proveedor al producto, o actualiza sus condiciones si ya estaba."""
        relacion.validar()
        self.repo.obtener(relacion.producto_id)
        proveedor = self.proveedores.obtener(relacion.proveedor_id)
        if not proveedor.activo:
            raise ValidacionError(f"El proveedor {proveedor.razon_social} está dado de baja.")
        return self.producto_proveedor.guardar(relacion)

    def quitar_proveedor(self, producto_id: int, proveedor_id: int) -> None:
        if not self.producto_proveedor.eliminar(producto_id, proveedor_id):
            raise ValidacionError("Ese proveedor no estaba asignado al producto.")

    # Auxiliares

    def _validar_duplicados(self, producto: Producto) -> None:
        # V4: SKU y código de barras identifican al producto (la columna SKU ignora mayúsculas).
        repetido = self.repo.buscar_uno_por(sku=producto.sku)
        if repetido is not None and repetido.id != producto.id:
            raise EntidadDuplicadaError(f"Ya existe un producto con el SKU {producto.sku} ({repetido.nombre}).")
        if producto.codigo_barras is not None:
            repetido = self.repo.buscar_uno_por(codigo_barras=producto.codigo_barras)
            if repetido is not None and repetido.id != producto.id:
                raise EntidadDuplicadaError(
                    f"El código de barras {producto.codigo_barras} ya es del producto {repetido.sku} ({repetido.nombre})."
                )

    def _registrar_precio(self, producto: Producto) -> None:
        momento = self._ahora()
        vigente = self.historial.vigente(producto.id)
        if vigente is not None:
            vigente.fecha_hasta = momento
            self.historial.guardar(vigente)
        self.historial.guardar(
            HistorialPrecio(
                producto_id=producto.id,
                costo=producto.costo_actual,
                precio_venta=producto.precio_venta_actual,
                fecha_desde=momento,
            )
        )


# --- P2: niveles mínimos de existencia ----------------------------------------------------------


class StockMinimoService:
    """Administra el stock mínimo de cada producto por ubicación.

    Inventario (pohlsi) lo consulta desde su Observer con `minimo()` o
    `esta_en_minimo()` cada vez que cambia el stock disponible.
    """

    def __init__(self, db: BaseDeDatos | None = None) -> None:
        self.db = db or BaseDeDatos()
        self.repo = StockMinimoRepositorio(self.db)
        self.productos = ProductoRepositorio(self.db)
        self.ubicaciones = UbicacionRepositorio(self.db)

    def definir(self, minimo: StockMinimo) -> StockMinimo:
        minimo.validar()
        producto = self.productos.obtener(minimo.producto_id)
        if not producto.activo:
            raise ValidacionError(f"El producto {producto.sku} está dado de baja.")
        ubicacion = self.ubicaciones.obtener(minimo.ubicacion_id)
        if not ubicacion.activa:
            raise ValidacionError(f"La ubicación {ubicacion.nombre} está dada de baja.")
        return self.repo.guardar(minimo)

    def quitar(self, producto_id: int, ubicacion_id: int) -> None:
        if not self.repo.eliminar(producto_id, ubicacion_id):
            raise ValidacionError("Ese producto no tenía un stock mínimo definido en esa ubicación.")

    def de_producto(self, producto_id: int) -> list[StockMinimo]:
        return self.repo.de_producto(producto_id)

    def de_ubicacion(self, ubicacion_id: int) -> dict[int, int]:
        """{producto_id: cantidad_minima} de una ubicación."""
        return {m.producto_id: m.cantidad_minima for m in self.repo.de_ubicacion(ubicacion_id)}

    def minimo(self, producto_id: int, ubicacion_id: int) -> int:
        """Cantidad mínima definida; 0 si no hay ninguna."""
        minimo = self.repo.obtener(producto_id, ubicacion_id)
        return minimo.cantidad_minima if minimo else 0

    def esta_en_minimo(self, producto_id: int, ubicacion_id: int, disponible: int) -> bool:
        """¿El disponible llegó al mínimo o está por debajo? (False si no hay mínimo definido)."""
        minimo = self.repo.obtener(producto_id, ubicacion_id)
        return minimo is not None and minimo.esta_en_minimo(disponible)


# --- P2: proveedores ----------------------------------------------------------------------------


class ProveedorService:
    def __init__(self, db: BaseDeDatos | None = None) -> None:
        self.db = db or BaseDeDatos()
        self.repo = ProveedorRepositorio(self.db)
        self.producto_proveedor = ProductoProveedorRepositorio(self.db)

    def listar(self, incluir_inactivos: bool = False) -> list[Proveedor]:
        return self.repo.listar(incluir_inactivos)

    def obtener(self, proveedor_id: int) -> Proveedor:
        return self.repo.obtener(proveedor_id)

    def guardar(self, proveedor: Proveedor) -> Proveedor:
        proveedor.validar()
        # V4: el CUIT identifica al proveedor.
        repetido = self.repo.buscar_uno_por(cuit=proveedor.cuit)
        if repetido is not None and repetido.id != proveedor.id:
            raise EntidadDuplicadaError(
                f"Ya existe un proveedor con el CUIT {formatear_cuit(proveedor.cuit)} ({repetido.razon_social})."
            )
        return self.repo.guardar(proveedor)

    def dar_de_baja(self, proveedor_id: int) -> None:
        self.repo.eliminar(proveedor_id)

    def reactivar(self, proveedor_id: int) -> Proveedor:
        proveedor = self.repo.obtener(proveedor_id)
        proveedor.activo = True
        return self.guardar(proveedor)

    def productos_de(self, proveedor_id: int) -> list[ProductoProveedor]:
        return self.producto_proveedor.de_proveedor(proveedor_id)
