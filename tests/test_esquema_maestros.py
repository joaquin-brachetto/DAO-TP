import sqlite3

from tests.utilidades import TestConBaseEnMemoria


class TestEsquemaMaestros(TestConBaseEnMemoria):
    def setUp(self):
        super().setUp()
        self.db.ejecutar("INSERT INTO categoria (id, nombre) VALUES (1, 'Bebidas')")

    def _insertar_producto(self, sku: str, codigo_barras: str | None = None, costo: str = "10") -> None:
        self.db.ejecutar(
            "INSERT INTO producto (sku, codigo_barras, nombre, categoria_id, costo_actual, precio_venta_actual) "
            "VALUES (?, ?, 'Producto', 1, ?, 20)",
            (sku, codigo_barras, costo),
        )

    def _insertar_proveedor(self, cuit: str) -> None:
        self.db.ejecutar("INSERT INTO proveedor (cuit, razon_social) VALUES (?, 'Proveedor SA')", (cuit,))

    def test_se_crean_todas_las_tablas_de_maestros(self):
        tablas = {fila["name"] for fila in self.db.consultar("SELECT name FROM sqlite_master WHERE type = 'table'")}
        self.assertLessEqual(
            {"ubicacion", "categoria", "producto", "historial_precio", "proveedor", "producto_proveedor"}, tablas
        )

    def test_inicializar_dos_veces_no_falla(self):
        self.db.inicializar_esquema()

    # V4 - productos
    def test_no_permite_sku_duplicado_aunque_cambien_mayusculas(self):
        self._insertar_producto("ABC-1")
        with self.assertRaises(sqlite3.IntegrityError):
            self._insertar_producto("abc-1")

    def test_no_permite_codigo_de_barras_duplicado(self):
        self._insertar_producto("A", "7790001")
        with self.assertRaises(sqlite3.IntegrityError):
            self._insertar_producto("B", "7790001")

    def test_varios_productos_pueden_no_tener_codigo_de_barras(self):
        self._insertar_producto("A")
        self._insertar_producto("B")

    def test_no_permite_costo_negativo(self):
        with self.assertRaises(sqlite3.IntegrityError):
            self._insertar_producto("A", costo="-1")

    def test_producto_exige_categoria_existente(self):
        with self.assertRaises(sqlite3.IntegrityError):
            self.db.ejecutar(
                "INSERT INTO producto (sku, nombre, categoria_id, costo_actual, precio_venta_actual) "
                "VALUES ('X', 'X', 99, 1, 1)"
            )

    # V4 - proveedores
    def test_no_permite_cuit_duplicado(self):
        self._insertar_proveedor("20123456789")
        with self.assertRaises(sqlite3.IntegrityError):
            self._insertar_proveedor("20123456789")

    def test_cuit_debe_tener_11_digitos(self):
        for cuit_invalido in ("2012345678", "20-12345678-9", "2012345678A"):
            with self.subTest(cuit=cuit_invalido), self.assertRaises(sqlite3.IntegrityError):
                self._insertar_proveedor(cuit_invalido)

    # Ubicaciones
    def test_tipo_de_ubicacion_valido(self):
        with self.assertRaises(sqlite3.IntegrityError):
            self.db.ejecutar("INSERT INTO ubicacion (tipo, codigo, nombre) VALUES ('DEPOSITO', 'X', 'X')")

    def test_el_cd_no_tiene_punto_de_venta(self):
        with self.assertRaises(sqlite3.IntegrityError):
            self.db.ejecutar(
                "INSERT INTO ubicacion (tipo, codigo, nombre, punto_venta) VALUES ('CD', 'CD1', 'Central', 1)"
            )
