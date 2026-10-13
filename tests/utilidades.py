import unittest

from src.persistencia.conexion import BaseDeDatos


class TestConBaseEnMemoria(unittest.TestCase):
    """Cada test arranca con una base vacía en memoria y el esquema completo creado."""

    def setUp(self) -> None:
        BaseDeDatos.reiniciar()
        self.db = BaseDeDatos(":memory:")
        self.db.inicializar_esquema()

    def tearDown(self) -> None:
        BaseDeDatos.reiniciar()
