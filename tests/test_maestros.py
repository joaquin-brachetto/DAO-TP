"""Pruebas de maestros (brache): P1, P2 y V4."""

from datetime import datetime, timedelta
from decimal import Decimal

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
from tests.utilidades import TestConBaseEnMemoria

CUIT_VALIDO = "20123456786"
OTRO_CUIT_VALIDO = "30712345671"


class RelojDePrueba:
    """Reloj que avanza un minuto en cada consulta, para ordenar el historial de precios."""

    def __init__(self) -> None:
        self.actual = datetime(2026, 10, 1, 9, 0)

    def __call__(self) -> datetime:
        self.actual += timedelta(minutes=1)
        return self.actual


class TestUbicaciones(TestConBaseEnMemoria):
    def setUp(self):
        super().setUp()
        self.servicio = UbicacionService()

    def test_alta_de_sucursal_y_cd(self):
        sucursal = self.servicio.guardar(Sucursal(codigo=" suc01 ", nombre="Centro", punto_venta=1))
        cd = self.servicio.guardar(CentroDistribucion(codigo="CD", nombre="Central", capacidad_m3=500))
        self.assertEqual(sucursal.codigo, "SUC01")
        leidas = {u.id: u for u in self.servicio.listar()}
        self.assertIsInstance(leidas[sucursal.id], Sucursal)
        self.assertIsInstance(leidas[cd.id], CentroDistribucion)
        self.assertTrue(leidas[cd.id].es_centro_distribucion())
        self.assertEqual([s.id for s in self.servicio.listar_sucursales()], [sucursal.id])

    def test_codigo_duplicado(self):
        self.servicio.guardar(Sucursal(codigo="SUC01", nombre="Centro", punto_venta=1))
        with self.assertRaises(EntidadDuplicadaError):
            self.servicio.guardar(Sucursal(codigo="suc01", nombre="Otra", punto_venta=2))

    def test_punto_de_venta_duplicado(self):
        self.servicio.guardar(Sucursal(codigo="SUC01", nombre="Centro", punto_venta=1))
        with self.assertRaises(EntidadDuplicadaError):
            self.servicio.guardar(Sucursal(codigo="SUC02", nombre="Norte", punto_venta=1))

    def test_punto_de_venta_obligatorio_y_positivo(self):
        for invalido in (0, -3, None):
            with self.subTest(punto_venta=invalido), self.assertRaises(ValidacionError):
                self.servicio.guardar(Sucursal(codigo="SUC01", nombre="Centro", punto_venta=invalido))

    def test_un_solo_cd_activo(self):
        cd = self.servicio.guardar(CentroDistribucion(codigo="CD1", nombre="Central"))
        with self.assertRaises(ValidacionError):
            self.servicio.guardar(CentroDistribucion(codigo="CD2", nombre="Otro"))
        self.servicio.dar_de_baja(cd.id)
        nuevo = self.servicio.guardar(CentroDistribucion(codigo="CD2", nombre="Nuevo"))
        with self.assertRaises(ValidacionError):
            self.servicio.reactivar(cd.id)
        self.assertEqual(self.servicio.obtener(nuevo.id).nombre, "Nuevo")

    def test_modificar_un_cd_no_choca_consigo_mismo(self):
        cd = self.servicio.guardar(CentroDistribucion(codigo="CD1", nombre="Central"))
        cd.nombre = "Central Córdoba"
        self.servicio.guardar(cd)
        self.assertEqual(self.servicio.obtener(cd.id).nombre, "Central Córdoba")

    def test_no_se_puede_cambiar_el_tipo(self):
        sucursal = self.servicio.guardar(Sucursal(codigo="SUC01", nombre="Centro", punto_venta=1))
        with self.assertRaises(ValidacionError):
            self.servicio.guardar(CentroDistribucion(codigo="SUC01", nombre="Centro", id=sucursal.id))

    def test_baja_logica_y_reactivacion(self):
        sucursal = self.servicio.guardar(Sucursal(codigo="SUC01", nombre="Centro", punto_venta=1))
        self.servicio.dar_de_baja(sucursal.id)
        self.assertEqual(self.servicio.listar(), [])
        self.assertFalse(self.servicio.obtener(sucursal.id).activa)
        self.servicio.reactivar(sucursal.id)
        self.assertTrue(self.servicio.obtener(sucursal.id).activa)

    def test_campos_obligatorios(self):
        with self.assertRaises(ValidacionError):
            self.servicio.guardar(Sucursal(codigo="  ", nombre="Centro", punto_venta=1))


class TestCategorias(TestConBaseEnMemoria):
    def setUp(self):
        super().setUp()
        self.servicio = CategoriaService()

    def test_nombre_unico_sin_importar_mayusculas(self):
        self.servicio.guardar(Categoria("Bebidas"))
        with self.assertRaises(EntidadDuplicadaError):
            self.servicio.guardar(Categoria("BEBIDAS"))

    def test_modificar_conserva_el_nombre(self):
        categoria = self.servicio.guardar(Categoria("Bebidas"))
        categoria.descripcion = "Con y sin alcohol"
        self.servicio.guardar(categoria)
        self.assertEqual(self.servicio.listar()[0].descripcion, "Con y sin alcohol")

    def test_no_se_elimina_si_tiene_productos(self):
        categoria = self.servicio.guardar(Categoria("Bebidas"))
        producto = ProductoService().guardar(Producto("A1", "Agua", categoria.id, Decimal("1"), Decimal("2")))
        ProductoService().dar_de_baja(producto.id)
        with self.assertRaises(EntidadEnUsoError):
            self.servicio.eliminar(categoria.id)

    def test_eliminar_categoria_vacia(self):
        categoria = self.servicio.guardar(Categoria("Bebidas"))
        self.servicio.eliminar(categoria.id)
        self.assertEqual(self.servicio.listar(), [])


class TestProductos(TestConBaseEnMemoria):
    def setUp(self):
        super().setUp()
        self.reloj = RelojDePrueba()
        self.servicio = ProductoService(ahora=self.reloj)
        self.bebidas = CategoriaService().guardar(Categoria("Bebidas"))

    def _producto(self, sku="AGU-500", codigo_barras=None, costo="100", precio="150") -> Producto:
        return Producto(sku, "Agua 500 ml", self.bebidas.id, Decimal(costo), Decimal(precio), codigo_barras)

    def test_alta_normaliza_y_registra_precio_inicial(self):
        producto = self.servicio.guardar(self._producto(sku=" agu-500 ", costo="100.555"))
        leido = self.servicio.obtener(producto.id)
        self.assertEqual(leido.sku, "AGU-500")
        self.assertEqual(leido.costo_actual, Decimal("100.56"))
        historial = self.servicio.historial_precios(producto.id)
        self.assertEqual(len(historial), 1)
        self.assertTrue(historial[0].esta_vigente())

    def test_v4_sku_duplicado(self):
        self.servicio.guardar(self._producto())
        with self.assertRaises(EntidadDuplicadaError) as error:
            self.servicio.guardar(self._producto(sku="agu-500"))
        self.assertIn("AGU-500", str(error.exception))

    def test_v4_codigo_de_barras_duplicado(self):
        self.servicio.guardar(self._producto(codigo_barras="7790001"))
        with self.assertRaises(EntidadDuplicadaError):
            self.servicio.guardar(self._producto(sku="OTRO", codigo_barras="7790001"))

    def test_v4_tambien_al_modificar(self):
        self.servicio.guardar(self._producto())
        otro = self.servicio.guardar(self._producto(sku="OTRO"))
        otro.sku = "AGU-500"
        with self.assertRaises(EntidadDuplicadaError):
            self.servicio.guardar(otro)

    def test_v4_un_producto_dado_de_baja_sigue_ocupando_su_sku(self):
        producto = self.servicio.guardar(self._producto())
        self.servicio.dar_de_baja(producto.id)
        with self.assertRaises(EntidadDuplicadaError):
            self.servicio.guardar(self._producto())

    def test_modificar_sin_cambiar_precio_no_agrega_historial(self):
        producto = self.servicio.guardar(self._producto())
        producto.nombre = "Agua mineral 500 ml"
        self.servicio.guardar(producto)
        self.assertEqual(len(self.servicio.historial_precios(producto.id)), 1)

    def test_cambio_de_precio_cierra_el_anterior_y_abre_uno_nuevo(self):
        producto = self.servicio.guardar(self._producto())
        producto.precio_venta_actual = Decimal("180")
        self.servicio.guardar(producto)
        nuevo, anterior = self.servicio.historial_precios(producto.id)
        self.assertEqual(nuevo.precio_venta, Decimal("180.00"))
        self.assertTrue(nuevo.esta_vigente())
        self.assertEqual(anterior.precio_venta, Decimal("150.00"))
        self.assertEqual(anterior.fecha_hasta, nuevo.fecha_desde)
        momento_viejo = anterior.fecha_desde + timedelta(seconds=30)
        self.assertEqual(self.servicio.precio_vigente_en(producto.id, momento_viejo).precio_venta, Decimal("150.00"))

    def test_validaciones_de_datos(self):
        casos = {
            "costo negativo": self._producto(costo="-1"),
            "sku vacío": self._producto(sku=" "),
            "código de barras con letras": self._producto(codigo_barras="77A"),
            "categoría inexistente": Producto("X", "X", 999, Decimal("1"), Decimal("1")),
        }
        for nombre, producto in casos.items():
            with self.subTest(nombre), self.assertRaises(ValidacionError):
                self.servicio.guardar(producto)

    def test_margen(self):
        producto = self._producto(costo="100", precio="150")
        self.assertEqual(producto.margen_unitario(), Decimal("50.00"))
        self.assertEqual(producto.margen_porcentual(), Decimal("50.00"))
        self.assertEqual(self._producto(costo="100", precio="80").margen_unitario(), Decimal("-20.00"))
        self.assertIsNone(self._producto(costo="0").margen_porcentual())

    def test_baja_reactivacion_y_busqueda(self):
        producto = self.servicio.guardar(self._producto(codigo_barras="7790001"))
        self.assertEqual([p.id for p in self.servicio.buscar("agua")], [producto.id])
        self.assertEqual([p.id for p in self.servicio.buscar("7790")], [producto.id])
        self.servicio.dar_de_baja(producto.id)
        self.assertEqual(self.servicio.buscar("agua"), [])
        self.assertEqual(len(self.servicio.buscar("agua", incluir_inactivos=True)), 1)
        self.servicio.reactivar(producto.id)
        self.assertTrue(self.servicio.obtener(producto.id).activo)

    def test_asignar_y_quitar_proveedores(self):
        producto = self.servicio.guardar(self._producto())
        proveedor = ProveedorService().guardar(Proveedor(CUIT_VALIDO, "Aguas SA"))
        self.servicio.asignar_proveedor(ProductoProveedor(producto.id, proveedor.id, "AG1", Decimal("90"), 3))
        self.servicio.asignar_proveedor(ProductoProveedor(producto.id, proveedor.id, "AG1", Decimal("95"), 2))
        [relacion] = self.servicio.proveedores_de(producto.id)
        self.assertEqual((relacion.costo_pactado, relacion.plazo_entrega_dias), (Decimal("95.00"), 2))
        self.assertEqual(len(ProveedorService().productos_de(proveedor.id)), 1)
        self.servicio.quitar_proveedor(producto.id, proveedor.id)
        self.assertEqual(self.servicio.proveedores_de(producto.id), [])
        with self.assertRaises(ValidacionError):
            self.servicio.quitar_proveedor(producto.id, proveedor.id)

    def test_no_se_asigna_un_proveedor_dado_de_baja_o_inexistente(self):
        producto = self.servicio.guardar(self._producto())
        proveedores = ProveedorService()
        proveedor = proveedores.guardar(Proveedor(CUIT_VALIDO, "Aguas SA"))
        proveedores.dar_de_baja(proveedor.id)
        with self.assertRaises(ValidacionError):
            self.servicio.asignar_proveedor(ProductoProveedor(producto.id, proveedor.id))
        with self.assertRaises(EntidadNoEncontradaError):
            self.servicio.asignar_proveedor(ProductoProveedor(producto.id, 999))


class TestProveedores(TestConBaseEnMemoria):
    def setUp(self):
        super().setUp()
        self.servicio = ProveedorService()

    def test_cuit(self):
        self.assertTrue(cuit_es_valido(CUIT_VALIDO))
        self.assertFalse(cuit_es_valido("20123456789"))  # verificador incorrecto
        self.assertFalse(cuit_es_valido("2012345678"))
        self.assertEqual(normalizar_cuit("20-12345678-6"), CUIT_VALIDO)
        self.assertEqual(formatear_cuit(CUIT_VALIDO), "20-12345678-6")

    def test_alta_acepta_cuit_con_guiones(self):
        proveedor = self.servicio.guardar(Proveedor("20-12345678-6", "Aguas SA", email="ventas@aguas.com"))
        self.assertEqual(self.servicio.obtener(proveedor.id).cuit, CUIT_VALIDO)

    def test_v4_cuit_duplicado(self):
        self.servicio.guardar(Proveedor(CUIT_VALIDO, "Aguas SA"))
        with self.assertRaises(EntidadDuplicadaError) as error:
            self.servicio.guardar(Proveedor("20-12345678-6", "Otra SA"))
        self.assertIn("20-12345678-6", str(error.exception))

    def test_modificar_no_choca_consigo_mismo(self):
        proveedor = self.servicio.guardar(Proveedor(CUIT_VALIDO, "Aguas SA"))
        proveedor.razon_social = "Aguas del Sur SA"
        self.servicio.guardar(proveedor)
        self.assertEqual(self.servicio.obtener(proveedor.id).razon_social, "Aguas del Sur SA")

    def test_validaciones_de_datos(self):
        for proveedor in (
            Proveedor("20123456789", "CUIT inválido"),
            Proveedor(OTRO_CUIT_VALIDO, "  "),
            Proveedor(OTRO_CUIT_VALIDO, "Mail malo", email="sin-arroba"),
        ):
            with self.subTest(proveedor=proveedor), self.assertRaises(ValidacionError):
                self.servicio.guardar(proveedor)

    def test_baja_y_reactivacion(self):
        proveedor = self.servicio.guardar(Proveedor(CUIT_VALIDO, "Aguas SA"))
        self.servicio.dar_de_baja(proveedor.id)
        self.assertEqual(self.servicio.listar(), [])
        self.servicio.reactivar(proveedor.id)
        self.assertEqual(len(self.servicio.listar()), 1)


class TestStockMinimo(TestConBaseEnMemoria):
    def setUp(self):
        super().setUp()
        self.servicio = StockMinimoService()
        ubicaciones = UbicacionService()
        self.sucursal = ubicaciones.guardar(Sucursal(codigo="SUC01", nombre="Centro", punto_venta=1))
        self.cd = ubicaciones.guardar(CentroDistribucion(codigo="CD", nombre="Central"))
        categoria = CategoriaService().guardar(Categoria("Bebidas"))
        self.productos = ProductoService()
        self.agua = self.productos.guardar(Producto("AGU", "Agua", categoria.id, Decimal("1"), Decimal("2")))

    def test_definir_reemplazar_y_quitar(self):
        self.servicio.definir(StockMinimo(self.agua.id, self.sucursal.id, 10))
        self.servicio.definir(StockMinimo(self.agua.id, self.cd.id, 60))
        self.servicio.definir(StockMinimo(self.agua.id, self.sucursal.id, 12))
        self.assertEqual(self.servicio.minimo(self.agua.id, self.sucursal.id), 12)
        self.assertEqual(len(self.servicio.de_producto(self.agua.id)), 2)
        self.assertEqual(self.servicio.de_ubicacion(self.cd.id), {self.agua.id: 60})
        self.servicio.quitar(self.agua.id, self.sucursal.id)
        self.assertEqual(self.servicio.minimo(self.agua.id, self.sucursal.id), 0)
        with self.assertRaises(ValidacionError):
            self.servicio.quitar(self.agua.id, self.sucursal.id)

    def test_en_minimo_incluye_llegar_justo_al_minimo(self):
        self.servicio.definir(StockMinimo(self.agua.id, self.sucursal.id, 10))
        self.assertTrue(self.servicio.esta_en_minimo(self.agua.id, self.sucursal.id, 10))
        self.assertTrue(self.servicio.esta_en_minimo(self.agua.id, self.sucursal.id, 3))
        self.assertFalse(self.servicio.esta_en_minimo(self.agua.id, self.sucursal.id, 11))
        self.assertFalse(self.servicio.esta_en_minimo(self.agua.id, self.cd.id, 0))  # sin mínimo definido

    def test_faltante(self):
        minimo = StockMinimo(self.agua.id, self.sucursal.id, 10)
        self.assertEqual(minimo.faltante(4), 6)
        self.assertEqual(minimo.faltante(15), 0)
        self.assertFalse(StockMinimo(self.agua.id, self.sucursal.id, 0).esta_en_minimo(0))

    def test_validaciones(self):
        with self.assertRaises(ValidacionError):
            self.servicio.definir(StockMinimo(self.agua.id, self.sucursal.id, -1))
        with self.assertRaises(EntidadNoEncontradaError):
            self.servicio.definir(StockMinimo(999, self.sucursal.id, 5))
        UbicacionService().dar_de_baja(self.sucursal.id)
        with self.assertRaises(ValidacionError):
            self.servicio.definir(StockMinimo(self.agua.id, self.sucursal.id, 5))
        self.productos.dar_de_baja(self.agua.id)
        with self.assertRaises(ValidacionError):
            self.servicio.definir(StockMinimo(self.agua.id, self.cd.id, 5))
