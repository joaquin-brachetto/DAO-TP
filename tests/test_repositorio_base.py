"""Tests de RepositorioBase (brache): patrón Repository genérico."""

from dataclasses import dataclass

import pytest

from src.excepciones import EntidadDuplicadaError, EntidadEnUsoError, EntidadNoEncontradaError
from src.persistencia.repositorio_base import RepositorioBase


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


@pytest.fixture
def categorias(db):
    return CategoriaRepositorio()


@pytest.fixture
def proveedores(db):
    return ProveedorRepositorio()


def test_guardar_inserta_y_completa_el_id(categorias):
    bebidas = categorias.guardar(Categoria("Bebidas"))

    assert bebidas.id is not None
    assert categorias.obtener(bebidas.id) == bebidas


def test_guardar_con_id_actualiza(categorias):
    bebidas = categorias.guardar(Categoria("Bebidas"))
    bebidas.descripcion = "Con y sin alcohol"

    categorias.guardar(bebidas)

    assert categorias.obtener(bebidas.id).descripcion == "Con y sin alcohol"
    assert len(categorias.listar()) == 1


def test_actualizar_algo_que_no_existe_falla(categorias):
    with pytest.raises(EntidadNoEncontradaError):
        categorias.guardar(Categoria("Fantasma", id=999))


def test_obtener_inexistente(categorias):
    assert categorias.obtener_por_id(999) is None
    with pytest.raises(EntidadNoEncontradaError):
        categorias.obtener(999)


def test_listar_respeta_el_orden(categorias):
    for nombre in ("Limpieza", "Almacén", "Bebidas"):
        categorias.guardar(Categoria(nombre))

    assert [c.nombre for c in categorias.listar()] == ["Almacén", "Bebidas", "Limpieza"]


def test_duplicado_se_traduce_a_error_de_negocio(proveedores):
    proveedores.guardar(Proveedor("20123456789", "Uno SA"))

    with pytest.raises(EntidadDuplicadaError, match="cuit"):
        proveedores.guardar(Proveedor("20123456789", "Dos SA"))


def test_existe_permite_excluir_el_propio_registro(proveedores):
    proveedor = proveedores.guardar(Proveedor("20123456789", "Uno SA"))

    assert proveedores.existe(cuit="20123456789")
    assert not proveedores.existe(cuit="20123456789", excluir_id=proveedor.id)
    assert not proveedores.existe(cuit="27999999990")


def test_buscar_por(proveedores):
    proveedores.guardar(Proveedor("20123456789", "Uno SA"))
    proveedores.guardar(Proveedor("27999999990", "Dos SA"))

    encontrados = proveedores.buscar_por(razon_social="Dos SA")

    assert [p.cuit for p in encontrados] == ["27999999990"]
    assert proveedores.buscar_uno_por(razon_social="Tres SA") is None


def test_buscar_por_columna_inexistente_falla(proveedores):
    with pytest.raises(ValueError):
        proveedores.buscar_por(nombre_que_no_existe="x")


def test_eliminar_con_campo_activo_es_baja_logica(proveedores):
    proveedor = proveedores.guardar(Proveedor("20123456789", "Uno SA"))

    proveedores.eliminar(proveedor.id)

    assert proveedores.listar() == []
    assert len(proveedores.listar(incluir_inactivos=True)) == 1
    assert proveedores.obtener(proveedor.id).activo is False


def test_eliminar_sin_campo_activo_borra(categorias):
    bebidas = categorias.guardar(Categoria("Bebidas"))

    categorias.eliminar(bebidas.id)

    assert categorias.obtener_por_id(bebidas.id) is None


def test_no_se_puede_borrar_algo_en_uso(db, categorias):
    bebidas = categorias.guardar(Categoria("Bebidas"))
    db.ejecutar(
        "INSERT INTO producto (sku, nombre, categoria_id, costo_actual, precio_venta_actual) "
        "VALUES ('A', 'Agua', ?, 1, 2)",
        (bebidas.id,),
    )

    with pytest.raises(EntidadEnUsoError):
        categorias.eliminar(bebidas.id)


def test_eliminar_inexistente(categorias):
    with pytest.raises(EntidadNoEncontradaError):
        categorias.eliminar(999)
