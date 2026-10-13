from dataclasses import dataclass

from src.excepciones import EntidadDuplicadaError, EntidadEnUsoError, EntidadNoEncontradaError
from src.persistencia.repositorio_base import RepositorioBase
from tests.utilidades import TestConBaseEnMemoria


# Entidades y repositorios mínimos, solo para probar la clase base.
@dataclass
class Categoria:
    nombre: str
    descripcion: str | None = None
    id: int | None = None


class CategoriaRepositorio(RepositorioBase[Categoria]):
    tabla = "categoria"
    entidad = Categoria
    orden = "nombre"


@dataclass
class Proveedor:
    cuit: str
    razon_social: str
    activo: bool = True
    id: int | None = None


class ProveedorRepositorio(RepositorioBase[Proveedor]):
    tabla = "proveedor"
    entidad = Proveedor
    campo_activo = "activo"


class TestRepositorioBase(TestConBaseEnMemoria):
    def setUp(self):
        super().setUp()
        self.categorias = CategoriaRepositorio()
        self.proveedores = ProveedorRepositorio()

    def test_guardar_inserta_y_completa_el_id(self):
        bebidas = self.categorias.guardar(Categoria("Bebidas"))
        self.assertIsNotNone(bebidas.id)
        self.assertEqual(self.categorias.obtener(bebidas.id), bebidas)

    def test_guardar_con_id_actualiza(self):
        bebidas = self.categorias.guardar(Categoria("Bebidas"))
        bebidas.descripcion = "Con y sin alcohol"
        self.categorias.guardar(bebidas)
        self.assertEqual(self.categorias.obtener(bebidas.id).descripcion, "Con y sin alcohol")
        self.assertEqual(len(self.categorias.listar()), 1)

    def test_actualizar_algo_que_no_existe_falla(self):
        with self.assertRaises(EntidadNoEncontradaError):
            self.categorias.guardar(Categoria("Fantasma", id=999))

    def test_obtener_inexistente(self):
        self.assertIsNone(self.categorias.obtener_por_id(999))
        with self.assertRaises(EntidadNoEncontradaError):
            self.categorias.obtener(999)

    def test_listar_respeta_el_orden(self):
        for nombre in ("Limpieza", "Almacén", "Bebidas"):
            self.categorias.guardar(Categoria(nombre))
        self.assertEqual([c.nombre for c in self.categorias.listar()], ["Almacén", "Bebidas", "Limpieza"])

    def test_duplicado_se_traduce_a_error_de_negocio(self):
        self.proveedores.guardar(Proveedor("20123456789", "Uno SA"))
        with self.assertRaises(EntidadDuplicadaError) as contexto:
            self.proveedores.guardar(Proveedor("20123456789", "Dos SA"))
        self.assertIn("cuit", str(contexto.exception))

    def test_existe_permite_excluir_el_propio_registro(self):
        proveedor = self.proveedores.guardar(Proveedor("20123456789", "Uno SA"))
        self.assertTrue(self.proveedores.existe(cuit="20123456789"))
        self.assertFalse(self.proveedores.existe(cuit="20123456789", excluir_id=proveedor.id))
        self.assertFalse(self.proveedores.existe(cuit="27999999990"))

    def test_buscar_por(self):
        self.proveedores.guardar(Proveedor("20123456789", "Uno SA"))
        self.proveedores.guardar(Proveedor("27999999990", "Dos SA"))
        encontrados = self.proveedores.buscar_por(razon_social="Dos SA")
        self.assertEqual([p.cuit for p in encontrados], ["27999999990"])
        self.assertIsNone(self.proveedores.buscar_uno_por(razon_social="Tres SA"))

    def test_buscar_por_columna_inexistente_falla(self):
        with self.assertRaises(ValueError):
            self.proveedores.buscar_por(nombre_que_no_existe="x")

    def test_eliminar_con_campo_activo_es_baja_logica(self):
        proveedor = self.proveedores.guardar(Proveedor("20123456789", "Uno SA"))
        self.proveedores.eliminar(proveedor.id)
        self.assertEqual(self.proveedores.listar(), [])
        self.assertEqual(len(self.proveedores.listar(incluir_inactivos=True)), 1)
        self.assertIs(self.proveedores.obtener(proveedor.id).activo, False)

    def test_eliminar_sin_campo_activo_borra(self):
        bebidas = self.categorias.guardar(Categoria("Bebidas"))
        self.categorias.eliminar(bebidas.id)
        self.assertIsNone(self.categorias.obtener_por_id(bebidas.id))

    def test_no_se_puede_borrar_algo_en_uso(self):
        bebidas = self.categorias.guardar(Categoria("Bebidas"))
        self.db.ejecutar(
            "INSERT INTO producto (sku, nombre, categoria_id, costo_actual, precio_venta_actual) "
            "VALUES ('A', 'Agua', ?, 1, 2)",
            (bebidas.id,),
        )
        with self.assertRaises(EntidadEnUsoError):
            self.categorias.eliminar(bebidas.id)

    def test_eliminar_inexistente(self):
        with self.assertRaises(EntidadNoEncontradaError):
            self.categorias.eliminar(999)
