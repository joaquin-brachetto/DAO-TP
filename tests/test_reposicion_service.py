"""Tests de ReposicionService y GeneradorNecesidades (pohlsi): P3 y patrón Observer."""

import pytest

from src.dominio.inventario.modelos import EstadoNecesidad, EstadoOrdenReposicion, OrigenNecesidad, Referencia
from src.excepciones import EntidadNoEncontradaError, ValidacionError
from src.servicios.generador_necesidades import GeneradorNecesidades
from src.servicios.reposicion_service import ReposicionService
from src.servicios.stock_service import StockService

REF = Referencia("TEST", 1)


@pytest.fixture
def reposicion(db):
    return ReposicionService(db)


def stock_en_local(stock, ubicacion_id, producto_id, cantidad):
    """Deja `cantidad` unidades verificadas (disponibles) en un local."""
    stock.ingresar_pendiente(ubicacion_id, producto_id, cantidad, REF)
    stock.confirmar_disponible(ubicacion_id, producto_id, cantidad, REF)


# --- Necesidades ---------------------------------------------------------------------------------


def test_crear_necesidad_manual(reposicion, escenario):
    necesidad = reposicion.crear_necesidad(escenario.sucursal, [(escenario.producto, 12)])

    guardada = reposicion.obtener_necesidad(necesidad.id)
    assert (guardada.origen, guardada.estado) == (OrigenNecesidad.MANUAL, EstadoNecesidad.PENDIENTE)
    assert [(d.producto_id, d.cantidad_solicitada) for d in guardada.detalles] == [(escenario.producto, 12)]


def test_la_necesidad_debe_ser_de_una_sucursal(reposicion, escenario):
    with pytest.raises(ValidacionError):
        reposicion.crear_necesidad(escenario.cd, [(escenario.producto, 1)])


def test_ubicacion_inexistente(reposicion, escenario):
    with pytest.raises(EntidadNoEncontradaError):
        reposicion.crear_necesidad(999, [(escenario.producto, 1)])


@pytest.mark.parametrize("renglones", [[], [(1, 0)], [(1, -2)], [(1, 5), (1, 3)], [(999, 1)]])
def test_necesidad_invalida(reposicion, escenario, renglones):
    with pytest.raises((ValidacionError, EntidadNoEncontradaError)):
        reposicion.crear_necesidad(escenario.sucursal, renglones)
    assert reposicion.listar_necesidades() == []


def test_anular_necesidad_pendiente(reposicion, escenario):
    necesidad = reposicion.crear_necesidad(escenario.sucursal, [(escenario.producto, 3)])

    reposicion.anular_necesidad(necesidad.id)

    assert reposicion.obtener_necesidad(necesidad.id).estado == EstadoNecesidad.ANULADA
    with pytest.raises(ValidacionError):
        reposicion.anular_necesidad(necesidad.id)


# --- Sugerencia: stock mínimo - disponible - pendiente -----------------------------------------------


def test_sugiere_lo_que_falta_para_llegar_al_minimo(reposicion, escenario, db, definir_minimo):
    stock = StockService(db)
    definir_minimo(escenario.producto, escenario.sucursal, 10)
    stock_en_local(stock, escenario.sucursal, escenario.producto, 3)
    stock.ingresar_pendiente(escenario.sucursal, escenario.producto, 2, REF)  # ya viene en camino

    assert reposicion.sugerir_necesidad(escenario.sucursal) == [(escenario.producto, 5)]  # 10 - 3 - 2


def test_no_sugiere_lo_que_esta_sobre_el_minimo_ni_sin_minimo(reposicion, escenario, db, definir_minimo):
    stock = StockService(db)
    definir_minimo(escenario.producto, escenario.sucursal, 10)
    stock_en_local(stock, escenario.sucursal, escenario.producto, 11)
    stock_en_local(stock, escenario.sucursal, escenario.otro_producto, 1)  # sin mínimo definido

    assert reposicion.sugerir_necesidad(escenario.sucursal) == []


# --- Consolidación (P3) ---------------------------------------------------------------------------------


def test_consolidar_suma_por_producto_y_fija_origen_y_destino(reposicion, escenario):
    una = reposicion.crear_necesidad(escenario.sucursal, [(escenario.producto, 5), (escenario.otro_producto, 1)])
    otra = reposicion.crear_necesidad(escenario.sucursal, [(escenario.producto, 7)])

    orden = reposicion.consolidar([una.id, otra.id])

    guardada = reposicion.obtener(orden.id)
    assert (guardada.origen_id, guardada.destino_id) == (escenario.cd, escenario.sucursal)
    assert guardada.estado == EstadoOrdenReposicion.PENDIENTE
    pedidos = {d.producto_id: d.cantidad_solicitada for d in guardada.detalles}
    assert pedidos == {escenario.producto: 12, escenario.otro_producto: 1}
    for id_ in (una.id, otra.id):
        consolidada = reposicion.obtener_necesidad(id_)
        assert (consolidada.estado, consolidada.orden_reposicion_id) == (EstadoNecesidad.CONSOLIDADA, orden.id)


def test_no_se_consolidan_necesidades_de_distintos_locales(reposicion, escenario):
    una = reposicion.crear_necesidad(escenario.sucursal, [(escenario.producto, 5)])
    otra = reposicion.crear_necesidad(escenario.otra_sucursal, [(escenario.producto, 5)])

    with pytest.raises(ValidacionError):
        reposicion.consolidar([una.id, otra.id])


def test_no_se_consolida_dos_veces_la_misma_necesidad(reposicion, escenario):
    necesidad = reposicion.crear_necesidad(escenario.sucursal, [(escenario.producto, 5)])
    reposicion.consolidar([necesidad.id])

    with pytest.raises(ValidacionError):
        reposicion.consolidar([necesidad.id])


def test_consolidar_sin_necesidades(reposicion):
    with pytest.raises(ValidacionError):
        reposicion.consolidar([])


def test_consolidar_necesidad_inexistente(reposicion):
    with pytest.raises(EntidadNoEncontradaError):
        reposicion.consolidar([999])


def test_sin_centro_de_distribucion_activo_no_se_puede_consolidar(reposicion, escenario, db):
    necesidad = reposicion.crear_necesidad(escenario.sucursal, [(escenario.producto, 5)])
    db.ejecutar("UPDATE ubicacion SET activa = 0 WHERE id = ?", (escenario.cd,))

    with pytest.raises(ValidacionError):
        reposicion.consolidar([necesidad.id])
    assert reposicion.obtener_necesidad(necesidad.id).estado == EstadoNecesidad.PENDIENTE


def test_los_numeros_de_orden_son_correlativos(reposicion, escenario):
    primera = reposicion.consolidar([reposicion.crear_necesidad(escenario.sucursal, [(escenario.producto, 1)]).id])
    segunda = reposicion.consolidar([reposicion.crear_necesidad(escenario.sucursal, [(escenario.producto, 1)]).id])

    assert (primera.numero, segunda.numero) == (1, 2)


# --- Ciclo de vida de la orden -----------------------------------------------------------------------------


@pytest.fixture
def orden(reposicion, escenario):
    necesidad = reposicion.crear_necesidad(escenario.sucursal, [(escenario.producto, 10)])
    return reposicion.consolidar([necesidad.id])


def test_ciclo_completo_cierra_como_completa(reposicion, escenario, orden):
    reposicion.iniciar_preparacion(orden.id)
    reposicion.registrar_preparado(orden.id, escenario.producto, 10)
    reposicion.marcar_despachada(orden.id)
    reposicion.registrar_recibido(orden.id, escenario.producto, 10)

    cerrada = reposicion.cerrar(orden.id)

    assert cerrada.estado == EstadoOrdenReposicion.CERRADA_COMPLETA


def test_si_se_recibe_menos_cierra_con_faltantes(reposicion, escenario, orden):
    reposicion.iniciar_preparacion(orden.id)
    reposicion.registrar_preparado(orden.id, escenario.producto, 10)
    reposicion.marcar_despachada(orden.id)
    reposicion.registrar_recibido(orden.id, escenario.producto, 7)  # 3 se rechazaron

    cerrada = reposicion.cerrar(orden.id)

    assert cerrada.estado == EstadoOrdenReposicion.CERRADA_CON_FALTANTES
    assert cerrada.detalles[0].faltante() == 3


def test_no_se_puede_saltear_estados(reposicion, orden):
    with pytest.raises(ValidacionError):
        reposicion.marcar_despachada(orden.id)  # PENDIENTE -> DESPACHADA no es válido
    with pytest.raises(ValidacionError):
        reposicion.cerrar(orden.id)
    assert reposicion.obtener(orden.id).estado == EstadoOrdenReposicion.PENDIENTE


def test_una_orden_cerrada_no_cambia_mas(reposicion, escenario, orden):
    reposicion.iniciar_preparacion(orden.id)
    reposicion.registrar_preparado(orden.id, escenario.producto, 10)
    reposicion.marcar_despachada(orden.id)
    reposicion.registrar_recibido(orden.id, escenario.producto, 10)
    reposicion.cerrar(orden.id)

    with pytest.raises(ValidacionError):
        reposicion.iniciar_preparacion(orden.id)
    with pytest.raises(ValidacionError):
        reposicion.cerrar(orden.id)


def test_no_se_prepara_mas_de_lo_solicitado(reposicion, escenario, orden):
    reposicion.iniciar_preparacion(orden.id)
    reposicion.registrar_preparado(orden.id, escenario.producto, 6)

    with pytest.raises(ValidacionError):
        reposicion.registrar_preparado(orden.id, escenario.producto, 5)
    assert reposicion.obtener(orden.id).detalles[0].cantidad_preparada == 6


def test_no_se_recibe_mas_de_lo_preparado(reposicion, escenario, orden):
    reposicion.iniciar_preparacion(orden.id)
    reposicion.registrar_preparado(orden.id, escenario.producto, 4)
    reposicion.marcar_despachada(orden.id)

    with pytest.raises(ValidacionError):
        reposicion.registrar_recibido(orden.id, escenario.producto, 5)


def test_lo_preparado_solo_se_registra_en_preparacion(reposicion, escenario, orden):
    with pytest.raises(ValidacionError):
        reposicion.registrar_preparado(orden.id, escenario.producto, 1)  # todavía PENDIENTE


def test_producto_que_no_esta_en_la_orden(reposicion, escenario, orden):
    reposicion.iniciar_preparacion(orden.id)

    with pytest.raises(EntidadNoEncontradaError):
        reposicion.registrar_preparado(orden.id, escenario.otro_producto, 1)


def test_listar_ordenes_por_estado(reposicion, escenario, orden):
    otra = reposicion.consolidar([reposicion.crear_necesidad(escenario.sucursal, [(escenario.producto, 1)]).id])
    reposicion.iniciar_preparacion(otra.id)

    assert [o.id for o in reposicion.listar(EstadoOrdenReposicion.EN_PREPARACION)] == [otra.id]
    assert len(reposicion.listar()) == 2


# --- Observer: GeneradorNecesidades ----------------------------------------------------------------------------


@pytest.fixture
def conectado(db, reposicion):
    """StockService con el GeneradorNecesidades suscripto."""
    stock = StockService(db)
    stock.suscribir(GeneradorNecesidades(reposicion))
    return stock


def test_una_venta_que_deja_el_local_bajo_el_minimo_genera_una_necesidad(conectado, reposicion, escenario, db, definir_minimo):
    definir_minimo(escenario.producto, escenario.sucursal, 5)
    stock_en_local(conectado, escenario.sucursal, escenario.producto, 10)

    conectado.egresar(escenario.sucursal, escenario.producto, 6, REF)  # quedan 4, bajo el mínimo de 5

    (necesidad,) = reposicion.listar_necesidades()
    assert necesidad.origen == OrigenNecesidad.AUTOMATICA
    assert necesidad.ubicacion_id == escenario.sucursal
    assert [(d.producto_id, d.cantidad_solicitada) for d in necesidad.detalles] == [(escenario.producto, 1)]


def test_no_genera_necesidad_mientras_hay_stock_suficiente(conectado, reposicion, escenario, db, definir_minimo):
    definir_minimo(escenario.producto, escenario.sucursal, 5)
    stock_en_local(conectado, escenario.sucursal, escenario.producto, 10)

    conectado.egresar(escenario.sucursal, escenario.producto, 2, REF)

    assert reposicion.listar_necesidades() == []


def test_no_duplica_la_necesidad_si_ya_hay_una_abierta(conectado, reposicion, escenario, db, definir_minimo):
    definir_minimo(escenario.producto, escenario.sucursal, 5)
    stock_en_local(conectado, escenario.sucursal, escenario.producto, 10)

    conectado.egresar(escenario.sucursal, escenario.producto, 6, REF)
    conectado.egresar(escenario.sucursal, escenario.producto, 1, REF)

    assert len(reposicion.listar_necesidades()) == 1


def test_una_vez_consolidada_puede_generar_otra(conectado, reposicion, escenario, db, definir_minimo):
    definir_minimo(escenario.producto, escenario.sucursal, 5)
    stock_en_local(conectado, escenario.sucursal, escenario.producto, 10)
    conectado.egresar(escenario.sucursal, escenario.producto, 6, REF)
    reposicion.consolidar([reposicion.listar_necesidades()[0].id])

    conectado.egresar(escenario.sucursal, escenario.producto, 1, REF)

    assert len(reposicion.listar_necesidades(EstadoNecesidad.PENDIENTE)) == 1


def test_si_el_cd_baja_del_minimo_no_se_genera_reposicion(conectado, reposicion, escenario, db, definir_minimo):
    definir_minimo(escenario.producto, escenario.cd, 5)
    conectado.ingresar_compra(escenario.cd, escenario.producto, 10, REF)

    conectado.egresar(escenario.cd, escenario.producto, 8, REF)

    assert reposicion.listar_necesidades() == []
