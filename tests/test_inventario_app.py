"""Tests de la integración de inventario con la aplicación (pohlsi): Observer conectado y stock de prueba."""

import pytest

from src.datos_prueba import cargar_datos_de_prueba
from src.datos_prueba_inventario import cargar_stock_de_prueba
from src.dominio.inventario.modelos import EstadoOrdenCompra, OrigenNecesidad, Referencia
from src.excepciones import ValidacionError
from src.servicios.compras_service import ComprasService
from src.servicios.inventario_app import crear_stock_service, describir_alerta
from src.servicios.reposicion_service import ReposicionService

REF = Referencia("TEST", 1)


# --- Observer conectado como en la ventana principal ---------------------------------------


def test_el_stock_service_de_la_aplicacion_alerta_y_genera_la_necesidad(db, escenario, definir_minimo):
    avisos = []
    stock, alertas = crear_stock_service(db, avisos.append)
    definir_minimo(escenario.producto, escenario.sucursal, 5)
    stock.ingresar_pendiente(escenario.sucursal, escenario.producto, 8, REF)
    stock.confirmar_disponible(escenario.sucursal, escenario.producto, 8, REF)

    stock.egresar(escenario.sucursal, escenario.producto, 4, REF)  # quedan 4, mínimo 5

    assert len(avisos) == 1 and len(alertas.alertas()) == 1
    (necesidad,) = ReposicionService(db).listar_necesidades()
    assert necesidad.origen == OrigenNecesidad.AUTOMATICA


def test_describir_alerta(db, escenario, definir_minimo):
    avisos = []
    stock, _ = crear_stock_service(db, avisos.append)
    definir_minimo(escenario.producto, escenario.cd, 5)
    stock.ingresar_compra(escenario.cd, escenario.producto, 6, REF)

    stock.egresar(escenario.cd, escenario.producto, 2, REF)

    assert describir_alerta(avisos[0], db) == "⚠ Stock mínimo: Yerba (Centro): quedan 4, mínimo 5"


# --- Stock de prueba ---------------------------------------------------------------------------


@pytest.fixture
def con_maestros(db):
    cargar_datos_de_prueba(db)
    return db


def test_stock_de_prueba_exige_los_maestros_cargados(db):
    with pytest.raises(ValidacionError):
        cargar_stock_de_prueba(db)


def test_stock_de_prueba_carga_compras_y_las_sucursales(con_maestros):
    db = con_maestros
    cantidades = cargar_stock_de_prueba(db)

    assert cantidades["productos en stock"] == 23
    compras = ComprasService(db).listar()
    recibidas = sum(1 for o in compras if o.estado == EstadoOrdenCompra.RECIBIDA)
    assert recibidas == cantidades["órdenes de compra recibidas"]
    assert sum(1 for o in compras if o.estado == EstadoOrdenCompra.PENDIENTE) == 1
    sin_stock = db.consultar(
        "SELECT u.codigo FROM ubicacion u WHERE NOT EXISTS "
        "(SELECT 1 FROM stock s WHERE s.ubicacion_id = u.id AND s.cantidad_disponible > 0)"
    )
    assert sin_stock == []
    assert db.consultar_uno("SELECT SUM(cantidad_pendiente) AS p FROM stock")["p"] == 0  # todo verificado


def test_stock_de_prueba_deja_un_producto_justo_en_su_minimo(con_maestros):
    db = con_maestros
    cargar_stock_de_prueba(db)

    fila = db.consultar_uno(
        "SELECT s.cantidad_disponible, sm.cantidad_minima FROM stock s "
        "JOIN producto p ON p.id = s.producto_id JOIN ubicacion u ON u.id = s.ubicacion_id "
        "JOIN stock_minimo sm ON sm.producto_id = s.producto_id AND sm.ubicacion_id = s.ubicacion_id "
        "WHERE p.sku = 'CAF-250' AND u.codigo = 'SUC01'"
    )
    assert fila["cantidad_disponible"] == fila["cantidad_minima"]


def test_stock_de_prueba_no_se_carga_dos_veces(con_maestros):
    cargar_stock_de_prueba(con_maestros)

    with pytest.raises(ValidacionError):
        cargar_stock_de_prueba(con_maestros)
