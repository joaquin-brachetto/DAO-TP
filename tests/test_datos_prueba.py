from src.datos_prueba import CLIENTES, PRODUCTOS, UBICACIONES, cargar_datos_de_prueba
from src.excepciones import ValidacionError
from tests.utilidades import TestConBaseEnMemoria


class TestDatosDePrueba(TestConBaseEnMemoria):
    def _contar(self, tabla: str) -> int:
        return self.db.consultar_uno(f"SELECT COUNT(*) AS n FROM {tabla}")["n"]

    def test_carga_todo_pasando_por_las_validaciones(self):
        cantidades = cargar_datos_de_prueba(self.db)
        self.assertEqual(self._contar("ubicacion"), len(UBICACIONES))
        self.assertEqual(self._contar("producto"), len(PRODUCTOS))
        self.assertEqual(self._contar("cliente"), len(CLIENTES))
        self.assertEqual(self._contar("stock_minimo"), cantidades["stock mínimos"])
        self.assertEqual(self._contar("ubicacion WHERE tipo = 'CD'"), 1)
        # cada producto tiene su precio inicial y los que aumentaron tienen dos registros
        self.assertGreater(self._contar("historial_precio"), len(PRODUCTOS))

    def test_no_se_carga_dos_veces(self):
        cargar_datos_de_prueba(self.db)
        with self.assertRaises(ValidacionError):
            cargar_datos_de_prueba(self.db)
        self.assertEqual(self._contar("producto"), len(PRODUCTOS))

    def test_se_puede_cargar_en_otra_base_en_el_mismo_proceso(self):
        cargar_datos_de_prueba(self.db)
        self.tearDown()
        self.setUp()
        cargar_datos_de_prueba(self.db)
        self.assertEqual(self._contar("producto"), len(PRODUCTOS))
