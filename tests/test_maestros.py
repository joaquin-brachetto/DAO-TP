"""Tests de maestros (brache): P1, P2 y V4."""

from datetime import datetime, timedelta
from decimal import Decimal

import pytest

from src.dominio.maestros.modelos import (
    Categoria,
    CentroDistribucion,
    Producto,
    ProductoProveedor,
    Proveedor,
    StockMinimo,
    Sucursal,
    cuit_es_valido,
    formatear_cuit,
    normalizar_cuit,
)
from src.excepciones import (
    EntidadDuplicadaError,
    EntidadEnUsoError,
    EntidadNoEncontradaError,
    ValidacionError,
)
from src.servicios.maestros_service import (
    CategoriaService,
    ProductoService,
    ProveedorService,
    StockMinimoService,
    UbicacionService,
)

CUIT_VALIDO = "20123456786"
OTRO_CUIT_VALIDO = "30712345671"


class RelojDePrueba:
    """Reloj que avanza un minuto en cada consulta, para ordenar el historial de precios."""

    def __init__(self) -> None:
        self.actual = datetime(2026, 10, 1, 9, 0)

    def __call__(self) -> datetime:
        self.actual += timedelta(minutes=1)
        return self.actual


# --- Ubicaciones (P1) ------------------------------------------------------------------------


@pytest.fixture
def ubicaciones(db):
    return UbicacionService()


def test_alta_de_sucursal_y_cd(ubicaciones):
    sucursal = ubicaciones.guardar(Sucursal(codigo=" suc01 ", nombre="Centro", punto_venta=1))
    cd = ubicaciones.guardar(CentroDistribucion(codigo="CD", nombre="Central", capacidad_m3=500))

    assert sucursal.codigo == "SUC01"
    leidas = {u.id: u for u in ubicaciones.listar()}
    assert isinstance(leidas[sucursal.id], Sucursal)
    assert isinstance(leidas[cd.id], CentroDistribucion)
    assert leidas[cd.id].es_centro_distribucion()
    assert [s.id for s in ubicaciones.listar_sucursales()] == [sucursal.id]


def test_codigo_duplicado(ubicaciones):
    ubicaciones.guardar(Sucursal(codigo="SUC01", nombre="Centro", punto_venta=1))
    with pytest.raises(EntidadDuplicadaError):
        ubicaciones.guardar(Sucursal(codigo="suc01", nombre="Otra", punto_venta=2))


def test_punto_de_venta_duplicado(ubicaciones):
    ubicaciones.guardar(Sucursal(codigo="SUC01", nombre="Centro", punto_venta=1))
    with pytest.raises(EntidadDuplicadaError):
        ubicaciones.guardar(Sucursal(codigo="SUC02", nombre="Norte", punto_venta=1))


@pytest.mark.parametrize("invalido", [0, -3, None])
def test_punto_de_venta_obligatorio_y_positivo(ubicaciones, invalido):
    with pytest.raises(ValidacionError):
        ubicaciones.guardar(Sucursal(codigo="SUC01", nombre="Centro", punto_venta=invalido))


def test_un_solo_cd_activo(ubicaciones):
    cd = ubicaciones.guardar(CentroDistribucion(codigo="CD1", nombre="Central"))
    with pytest.raises(ValidacionError):
        ubicaciones.guardar(CentroDistribucion(codigo="CD2", nombre="Otro"))

    ubicaciones.dar_de_baja(cd.id)
    nuevo = ubicaciones.guardar(CentroDistribucion(codigo="CD2", nombre="Nuevo"))

    with pytest.raises(ValidacionError):
        ubicaciones.reactivar(cd.id)
    assert ubicaciones.obtener(nuevo.id).nombre == "Nuevo"


def test_modificar_un_cd_no_choca_consigo_mismo(ubicaciones):
    cd = ubicaciones.guardar(CentroDistribucion(codigo="CD1", nombre="Central"))
    cd.nombre = "Central Córdoba"

    ubicaciones.guardar(cd)

    assert ubicaciones.obtener(cd.id).nombre == "Central Córdoba"


def test_no_se_puede_cambiar_el_tipo(ubicaciones):
    sucursal = ubicaciones.guardar(Sucursal(codigo="SUC01", nombre="Centro", punto_venta=1))
    with pytest.raises(ValidacionError):
        ubicaciones.guardar(CentroDistribucion(codigo="SUC01", nombre="Centro", id=sucursal.id))


def test_baja_logica_y_reactivacion(ubicaciones):
    sucursal = ubicaciones.guardar(Sucursal(codigo="SUC01", nombre="Centro", punto_venta=1))

    ubicaciones.dar_de_baja(sucursal.id)
    assert ubicaciones.listar() == []
    assert not ubicaciones.obtener(sucursal.id).activa

    ubicaciones.reactivar(sucursal.id)
    assert ubicaciones.obtener(sucursal.id).activa


def test_campos_obligatorios(ubicaciones):
    with pytest.raises(ValidacionError):
        ubicaciones.guardar(Sucursal(codigo="  ", nombre="Centro", punto_venta=1))


# --- Categorías (P2) -------------------------------------------------------------------------


@pytest.fixture
def categorias(db):
    return CategoriaService()


def test_nombre_unico_sin_importar_mayusculas(categorias):
    categorias.guardar(Categoria("Bebidas"))
    with pytest.raises(EntidadDuplicadaError):
        categorias.guardar(Categoria("BEBIDAS"))


def test_modificar_conserva_el_nombre(categorias):
    categoria = categorias.guardar(Categoria("Bebidas"))
    categoria.descripcion = "Con y sin alcohol"

    categorias.guardar(categoria)

    assert categorias.listar()[0].descripcion == "Con y sin alcohol"


def test_no_se_elimina_si_tiene_productos(categorias):
    categoria = categorias.guardar(Categoria("Bebidas"))
    producto = ProductoService().guardar(Producto("A1", "Agua", categoria.id, Decimal("1"), Decimal("2")))
    ProductoService().dar_de_baja(producto.id)

    with pytest.raises(EntidadEnUsoError):
        categorias.eliminar(categoria.id)


def test_eliminar_categoria_vacia(categorias):
    categoria = categorias.guardar(Categoria("Bebidas"))

    categorias.eliminar(categoria.id)

    assert categorias.listar() == []


# --- Productos (P2 y V4) ---------------------------------------------------------------------


@pytest.fixture
def productos(db):
    return ProductoService(ahora=RelojDePrueba())


@pytest.fixture
def nuevo_producto(db):
    """Devuelve una función que arma un producto de la categoría Bebidas (sin guardarlo)."""
    bebidas = CategoriaService().guardar(Categoria("Bebidas"))

    def crear(sku="AGU-500", codigo_barras=None, costo="100", precio="150", categoria_id=None) -> Producto:
        return Producto(
            sku, "Agua 500 ml", categoria_id or bebidas.id, Decimal(costo), Decimal(precio), codigo_barras
        )

    return crear


def test_alta_normaliza_y_registra_precio_inicial(productos, nuevo_producto):
    producto = productos.guardar(nuevo_producto(sku=" agu-500 ", costo="100.555"))

    leido = productos.obtener(producto.id)
    assert leido.sku == "AGU-500"
    assert leido.costo_actual == Decimal("100.56")
    historial = productos.historial_precios(producto.id)
    assert len(historial) == 1
    assert historial[0].esta_vigente()


def test_v4_sku_duplicado(productos, nuevo_producto):
    productos.guardar(nuevo_producto())
    with pytest.raises(EntidadDuplicadaError, match="AGU-500"):
        productos.guardar(nuevo_producto(sku="agu-500"))


def test_v4_codigo_de_barras_duplicado(productos, nuevo_producto):
    productos.guardar(nuevo_producto(codigo_barras="7790001"))
    with pytest.raises(EntidadDuplicadaError):
        productos.guardar(nuevo_producto(sku="OTRO", codigo_barras="7790001"))


def test_v4_tambien_al_modificar(productos, nuevo_producto):
    productos.guardar(nuevo_producto())
    otro = productos.guardar(nuevo_producto(sku="OTRO"))
    otro.sku = "AGU-500"

    with pytest.raises(EntidadDuplicadaError):
        productos.guardar(otro)


def test_v4_un_producto_dado_de_baja_sigue_ocupando_su_sku(productos, nuevo_producto):
    producto = productos.guardar(nuevo_producto())
    productos.dar_de_baja(producto.id)

    with pytest.raises(EntidadDuplicadaError):
        productos.guardar(nuevo_producto())


def test_modificar_sin_cambiar_precio_no_agrega_historial(productos, nuevo_producto):
    producto = productos.guardar(nuevo_producto())
    producto.nombre = "Agua mineral 500 ml"

    productos.guardar(producto)

    assert len(productos.historial_precios(producto.id)) == 1


def test_cambio_de_precio_cierra_el_anterior_y_abre_uno_nuevo(productos, nuevo_producto):
    producto = productos.guardar(nuevo_producto())
    producto.precio_venta_actual = Decimal("180")

    productos.guardar(producto)

    nuevo, anterior = productos.historial_precios(producto.id)
    assert nuevo.precio_venta == Decimal("180.00")
    assert nuevo.esta_vigente()
    assert anterior.precio_venta == Decimal("150.00")
    assert anterior.fecha_hasta == nuevo.fecha_desde
    momento_viejo = anterior.fecha_desde + timedelta(seconds=30)
    assert productos.precio_vigente_en(producto.id, momento_viejo).precio_venta == Decimal("150.00")


@pytest.mark.parametrize(
    "datos",
    [
        {"costo": "-1"},
        {"sku": " "},
        {"codigo_barras": "77A"},
        {"categoria_id": 999},
    ],
    ids=["costo negativo", "sku vacío", "código de barras con letras", "categoría inexistente"],
)
def test_validaciones_de_datos_del_producto(productos, nuevo_producto, datos):
    with pytest.raises(ValidacionError):
        productos.guardar(nuevo_producto(**datos))


def test_margen(nuevo_producto):
    producto = nuevo_producto(costo="100", precio="150")

    assert producto.margen_unitario() == Decimal("50.00")
    assert producto.margen_porcentual() == Decimal("50.00")
    assert nuevo_producto(costo="100", precio="80").margen_unitario() == Decimal("-20.00")
    assert nuevo_producto(costo="0").margen_porcentual() is None


def test_baja_reactivacion_y_busqueda(productos, nuevo_producto):
    producto = productos.guardar(nuevo_producto(codigo_barras="7790001"))
    assert [p.id for p in productos.buscar("agua")] == [producto.id]
    assert [p.id for p in productos.buscar("7790")] == [producto.id]

    productos.dar_de_baja(producto.id)
    assert productos.buscar("agua") == []
    assert len(productos.buscar("agua", incluir_inactivos=True)) == 1

    productos.reactivar(producto.id)
    assert productos.obtener(producto.id).activo


def test_asignar_y_quitar_proveedores(productos, nuevo_producto):
    producto = productos.guardar(nuevo_producto())
    proveedor = ProveedorService().guardar(Proveedor(CUIT_VALIDO, "Aguas SA"))

    productos.asignar_proveedor(ProductoProveedor(producto.id, proveedor.id, "AG1", Decimal("90"), 3))
    productos.asignar_proveedor(ProductoProveedor(producto.id, proveedor.id, "AG1", Decimal("95"), 2))

    [relacion] = productos.proveedores_de(producto.id)
    assert (relacion.costo_pactado, relacion.plazo_entrega_dias) == (Decimal("95.00"), 2)
    assert len(ProveedorService().productos_de(proveedor.id)) == 1

    productos.quitar_proveedor(producto.id, proveedor.id)
    assert productos.proveedores_de(producto.id) == []
    with pytest.raises(ValidacionError):
        productos.quitar_proveedor(producto.id, proveedor.id)


def test_no_se_asigna_un_proveedor_dado_de_baja_o_inexistente(productos, nuevo_producto):
    producto = productos.guardar(nuevo_producto())
    proveedores = ProveedorService()
    proveedor = proveedores.guardar(Proveedor(CUIT_VALIDO, "Aguas SA"))
    proveedores.dar_de_baja(proveedor.id)

    with pytest.raises(ValidacionError):
        productos.asignar_proveedor(ProductoProveedor(producto.id, proveedor.id))
    with pytest.raises(EntidadNoEncontradaError):
        productos.asignar_proveedor(ProductoProveedor(producto.id, 999))


# --- Proveedores (P2 y V4) -------------------------------------------------------------------


@pytest.fixture
def proveedores(db):
    return ProveedorService()


def test_cuit():
    assert cuit_es_valido(CUIT_VALIDO)
    assert not cuit_es_valido("20123456789")  # verificador incorrecto
    assert not cuit_es_valido("2012345678")
    assert normalizar_cuit("20-12345678-6") == CUIT_VALIDO
    assert formatear_cuit(CUIT_VALIDO) == "20-12345678-6"


def test_alta_acepta_cuit_con_guiones(proveedores):
    proveedor = proveedores.guardar(Proveedor("20-12345678-6", "Aguas SA", email="ventas@aguas.com"))
    assert proveedores.obtener(proveedor.id).cuit == CUIT_VALIDO


def test_v4_cuit_duplicado(proveedores):
    proveedores.guardar(Proveedor(CUIT_VALIDO, "Aguas SA"))
    with pytest.raises(EntidadDuplicadaError, match="20-12345678-6"):
        proveedores.guardar(Proveedor("20-12345678-6", "Otra SA"))


def test_modificar_proveedor_no_choca_consigo_mismo(proveedores):
    proveedor = proveedores.guardar(Proveedor(CUIT_VALIDO, "Aguas SA"))
    proveedor.razon_social = "Aguas del Sur SA"

    proveedores.guardar(proveedor)

    assert proveedores.obtener(proveedor.id).razon_social == "Aguas del Sur SA"


@pytest.mark.parametrize(
    "proveedor",
    [
        Proveedor("20123456789", "CUIT inválido"),
        Proveedor(OTRO_CUIT_VALIDO, "  "),
        Proveedor(OTRO_CUIT_VALIDO, "Mail malo", email="sin-arroba"),
    ],
    ids=["cuit inválido", "razón social vacía", "email inválido"],
)
def test_validaciones_de_datos_del_proveedor(proveedores, proveedor):
    with pytest.raises(ValidacionError):
        proveedores.guardar(proveedor)


def test_baja_y_reactivacion_de_proveedor(proveedores):
    proveedor = proveedores.guardar(Proveedor(CUIT_VALIDO, "Aguas SA"))

    proveedores.dar_de_baja(proveedor.id)
    assert proveedores.listar() == []

    proveedores.reactivar(proveedor.id)
    assert len(proveedores.listar()) == 1


# --- Stock mínimo (P2) -----------------------------------------------------------------------


@pytest.fixture
def con_minimos(db):
    """Una sucursal, el CD y un producto, listos para definirles stock mínimo."""
    ubicaciones = UbicacionService()
    sucursal = ubicaciones.guardar(Sucursal(codigo="SUC01", nombre="Centro", punto_venta=1))
    cd = ubicaciones.guardar(CentroDistribucion(codigo="CD", nombre="Central"))
    categoria = CategoriaService().guardar(Categoria("Bebidas"))
    agua = ProductoService().guardar(Producto("AGU", "Agua", categoria.id, Decimal("1"), Decimal("2")))
    return StockMinimoService(), sucursal, cd, agua


def test_definir_reemplazar_y_quitar(con_minimos):
    servicio, sucursal, cd, agua = con_minimos
    servicio.definir(StockMinimo(agua.id, sucursal.id, 10))
    servicio.definir(StockMinimo(agua.id, cd.id, 60))
    servicio.definir(StockMinimo(agua.id, sucursal.id, 12))

    assert servicio.minimo(agua.id, sucursal.id) == 12
    assert len(servicio.de_producto(agua.id)) == 2
    assert servicio.de_ubicacion(cd.id) == {agua.id: 60}

    servicio.quitar(agua.id, sucursal.id)
    assert servicio.minimo(agua.id, sucursal.id) == 0
    with pytest.raises(ValidacionError):
        servicio.quitar(agua.id, sucursal.id)


def test_en_minimo_incluye_llegar_justo_al_minimo(con_minimos):
    servicio, sucursal, cd, agua = con_minimos
    servicio.definir(StockMinimo(agua.id, sucursal.id, 10))

    assert servicio.esta_en_minimo(agua.id, sucursal.id, 10)
    assert servicio.esta_en_minimo(agua.id, sucursal.id, 3)
    assert not servicio.esta_en_minimo(agua.id, sucursal.id, 11)
    assert not servicio.esta_en_minimo(agua.id, cd.id, 0)  # sin mínimo definido


def test_faltante(con_minimos):
    _, sucursal, _, agua = con_minimos
    minimo = StockMinimo(agua.id, sucursal.id, 10)

    assert minimo.faltante(4) == 6
    assert minimo.faltante(15) == 0
    assert not StockMinimo(agua.id, sucursal.id, 0).esta_en_minimo(0)


def test_validaciones_de_stock_minimo(con_minimos):
    servicio, sucursal, cd, agua = con_minimos
    with pytest.raises(ValidacionError):
        servicio.definir(StockMinimo(agua.id, sucursal.id, -1))
    with pytest.raises(EntidadNoEncontradaError):
        servicio.definir(StockMinimo(999, sucursal.id, 5))

    UbicacionService().dar_de_baja(sucursal.id)
    with pytest.raises(ValidacionError):
        servicio.definir(StockMinimo(agua.id, sucursal.id, 5))

    ProductoService().dar_de_baja(agua.id)
    with pytest.raises(ValidacionError):
        servicio.definir(StockMinimo(agua.id, cd.id, 5))
