"""Tests integrales del módulo de Logística (turco):
Patrón State del Bulto, inmutabilidad del historial (V2), empaquetado y precintado (P4),
despacho desde el CD (P5), recepción y verificación de precintos en sucursal (P6, V1),
integración con StockService, ReposicionService, Observer y ReporteTransito (R4).
"""

from __future__ import annotations

import dataclasses
import sqlite3
from datetime import date, datetime, timedelta
from decimal import Decimal

import pytest

from src.datos_prueba import cargar_datos_de_prueba
from src.datos_prueba_inventario import cargar_stock_de_prueba
from src.datos_prueba_logistica import cargar_logistica_de_prueba
from src.dominio.inventario.modelos import (
    EstadoOrdenReposicion,
    Referencia,
)
from src.dominio.logistica.modelos import (
    Bulto,
    CambioEstadoBulto,
    CodigoEstadoBulto,
    ControlBulto,
    EnTransito,
    EstadoBulto,
    EstadoRemito,
    Precintado,
    Precinto,
    Preparado,
    Recibido,
    Rechazado,
    TransicionInvalidaError,
    Verificado,
    estado_desde_nombre,
)
from src.excepciones import EntidadDuplicadaError, EntidadNoEncontradaError, ValidacionError
from src.persistencia.repositorio_logistica import CambioEstadoBultoRepositorio
from src.reportes.inventario_reporte import ReporteTransito
from src.servicios.logistica_service import EspecificacionBulto, LogisticaService
from src.servicios.observadores_stock import AlertaStockMinimo
from src.servicios.reposicion_service import ReposicionService
from src.servicios.stock_service import StockInsuficienteError, StockService
from tests.utilidades import TestConBaseEnMemoria

REF_COMPRA = Referencia("ORDEN_COMPRA", 1, usuario="test")
FECHA_BASE = datetime(2026, 10, 10, 9, 0, 0)


class Reloj:
    def __init__(self, momento: datetime = FECHA_BASE) -> None:
        self.momento = momento

    def __call__(self) -> datetime:
        return self.momento

    def avanzar(self, **kwargs) -> datetime:
        self.momento = self.momento + timedelta(**kwargs)
        return self.momento


@pytest.fixture
def reloj():
    return Reloj(FECHA_BASE)


@pytest.fixture
def stock(db, reloj):
    return StockService(db, ahora=reloj)


@pytest.fixture
def reposicion(db):
    return ReposicionService(db)


@pytest.fixture
def logistica(db, stock, reposicion, reloj):
    return LogisticaService(db, stock_service=stock, reposicion_service=reposicion, ahora=reloj)


@pytest.fixture
def orden_con_stock(escenario, stock, reposicion):
    """Carga 100 unidades de ambos productos en el CD y crea una OrdenReposicion de 10 y 6 unidades."""
    stock.ingresar_compra(escenario.cd, escenario.producto, 100, REF_COMPRA, costo_unitario=Decimal("100"))
    stock.ingresar_compra(escenario.cd, escenario.otro_producto, 100, REF_COMPRA, costo_unitario=Decimal("50"))
    necesidad = reposicion.crear_necesidad(
        escenario.sucursal,
        [(escenario.producto, 10), (escenario.otro_producto, 6)],
    )
    return reposicion.consolidar([necesidad.id])


# =============================================================================
# 1. PATRÓN STATE DEL BULTO: TRANSICIONES VÁLIDAS E INVÁLIDAS
# =============================================================================


def test_bulto_inicia_con_objeto_estado_preparado():
    bulto = Bulto(codigo="BUL-0001")

    assert isinstance(bulto.estado, EstadoBulto)
    assert isinstance(bulto.estado, Preparado)
    assert bulto.nombre_estado == CodigoEstadoBulto.PREPARADO.value
    assert not bulto.es_estado_final


def test_patron_state_camino_feliz_completo():
    bulto = Bulto(codigo="BUL-0001")
    bulto.agregar_producto(producto_id=1, cantidad=4)
    bulto.agregar_producto(producto_id=1, cantidad=2)  # acumula en el mismo producto
    assert bulto.total_unidades() == 6

    precinto = Precinto(numero="PREC-001", fecha_colocacion=FECHA_BASE)
    bulto.precintar(precinto, usuario="turco", fecha_hora=FECHA_BASE)
    assert isinstance(bulto.estado, Precintado)
    assert not bulto.es_estado_final

    bulto.despachar(usuario="turco", fecha_hora=FECHA_BASE + timedelta(hours=1))
    assert isinstance(bulto.estado, EnTransito)

    bulto.recibir(usuario="local1", fecha_hora=FECHA_BASE + timedelta(hours=5))
    assert isinstance(bulto.estado, Recibido)

    bulto.verificar(usuario="local1", observacion="Control OK", fecha_hora=FECHA_BASE + timedelta(hours=6))
    assert isinstance(bulto.estado, Verificado)
    assert bulto.es_estado_final

    historial = bulto.historial()
    assert isinstance(historial, tuple)
    assert [(c.estado_anterior, c.estado_nuevo) for c in historial] == [
        ("PREPARADO", "PRECINTADO"),
        ("PRECINTADO", "EN_TRANSITO"),
        ("EN_TRANSITO", "RECIBIDO"),
        ("RECIBIDO", "VERIFICADO"),
    ]


def test_patron_state_camino_de_rechazo():
    bulto = Bulto(codigo="BUL-0002")
    bulto.agregar_producto(producto_id=2, cantidad=5)
    bulto.precintar(Precinto(numero="PREC-002"), usuario="turco")
    bulto.despachar(usuario="turco")
    bulto.recibir(usuario="local1")

    bulto.rechazar(motivo="Precinto violado en transporte", usuario="local1")

    assert isinstance(bulto.estado, Rechazado)
    assert bulto.es_estado_final
    assert bulto.motivo_rechazo == "Precinto violado en transporte"
    assert bulto.historial()[-1].estado_nuevo == "RECHAZADO"


def test_no_se_puede_precintar_un_bulto_vacio():
    bulto = Bulto(codigo="BUL-VACIO")
    with pytest.raises(TransicionInvalidaError):
        bulto.precintar(Precinto(numero="PREC-999"))


@pytest.mark.parametrize(
    "accion",
    [
        lambda b: b.despachar(),
        lambda b: b.recibir(),
        lambda b: b.verificar(),
        lambda b: b.rechazar("Motivo"),
    ],
)
def test_transiciones_invalidas_desde_preparado(accion):
    bulto = Bulto(codigo="BUL-001")
    bulto.agregar_producto(1, 3)

    with pytest.raises(TransicionInvalidaError):
        accion(bulto)
    assert isinstance(bulto.estado, Preparado)


@pytest.mark.parametrize(
    "accion",
    [
        lambda b: b.agregar_producto(1, 2),
        lambda b: b.precintar(Precinto("PREC-OTRO")),
        lambda b: b.recibir(),
        lambda b: b.verificar(),
        lambda b: b.rechazar("Motivo"),
    ],
)
def test_transiciones_invalidas_desde_precintado(accion):
    bulto = Bulto(codigo="BUL-001")
    bulto.agregar_producto(1, 3)
    bulto.precintar(Precinto("PREC-001"))

    with pytest.raises(TransicionInvalidaError):
        accion(bulto)
    assert isinstance(bulto.estado, Precintado)


@pytest.mark.parametrize(
    "accion",
    [
        lambda b: b.agregar_producto(1, 2),
        lambda b: b.precintar(Precinto("PREC-OTRO")),
        lambda b: b.despachar(),
        lambda b: b.verificar(),
        lambda b: b.rechazar("Motivo"),
    ],
)
def test_transiciones_invalidas_desde_en_transito(accion):
    bulto = Bulto(codigo="BUL-001")
    bulto.agregar_producto(1, 3)
    bulto.precintar(Precinto("PREC-001"))
    bulto.despachar()

    with pytest.raises(TransicionInvalidaError):
        accion(bulto)
    assert isinstance(bulto.estado, EnTransito)


@pytest.mark.parametrize(
    "accion",
    [
        lambda b: b.agregar_producto(1, 2),
        lambda b: b.precintar(Precinto("PREC-OTRO")),
        lambda b: b.despachar(),
        lambda b: b.recibir(),
        lambda b: b.rechazar("   "),  # motivo vacío no permitido
    ],
)
def test_transiciones_invalidas_desde_recibido(accion):
    bulto = Bulto(codigo="BUL-001")
    bulto.agregar_producto(1, 3)
    bulto.precintar(Precinto("PREC-001"))
    bulto.despachar()
    bulto.recibir()

    with pytest.raises(TransicionInvalidaError):
        accion(bulto)
    assert isinstance(bulto.estado, Recibido)


@pytest.mark.parametrize("estado_final", ["VERIFICADO", "RECHAZADO"])
@pytest.mark.parametrize(
    "accion",
    [
        lambda b: b.agregar_producto(1, 1),
        lambda b: b.precintar(Precinto("PREC-X")),
        lambda b: b.despachar(),
        lambda b: b.recibir(),
        lambda b: b.verificar(),
        lambda b: b.rechazar("Motivo"),
    ],
)
def test_estados_finales_no_admiten_ninguna_transicion(estado_final, accion):
    bulto = Bulto(codigo="BUL-FIN", estado=estado_desde_nombre(estado_final))

    with pytest.raises(TransicionInvalidaError):
        accion(bulto)
    assert bulto.nombre_estado == estado_final


# =============================================================================
# 2. INMUTABILIDAD DEL HISTORIAL DE ESTADOS (V2)
# =============================================================================


def test_cambio_estado_bulto_es_inmutable_en_python():
    cambio = CambioEstadoBulto(
        fecha_hora=FECHA_BASE,
        estado_anterior="PREPARADO",
        estado_nuevo="PRECINTADO",
        usuario="turco",
        observacion="Cerrado",
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        cambio.estado_nuevo = "VERIFICADO"  # type: ignore[misc]


def test_v2_historial_inmutable_en_sqlite_bloquea_update_y_delete(logistica, orden_con_stock, escenario, db, reloj):
    remito = logistica.armar_remito(
        orden_con_stock.id,
        [EspecificacionBulto([(escenario.producto, 5)], numero_precinto="PREC-V2")],
        usuario="turco",
    )
    bulto_id = remito.bultos[0].id
    reloj.avanzar(hours=1)
    logistica.registrar_despacho([remito.id], "Transp SA", "AA 111 BB", usuario="turco")
    reloj.avanzar(hours=3)
    logistica.procesar_recepcion_completa(
        remito.id,
        recibido_por="receptor",
        controles_por_bulto=[(bulto_id, "PREC-V2", True, "OK")],
    )

    historial = logistica.historial_bulto(bulto_id)
    assert len(historial) == 5
    assert [c.estado_nuevo for c in historial] == [
        "PREPARADO",
        "PRECINTADO",
        "EN_TRANSITO",
        "RECIBIDO",
        "VERIFICADO",
    ]
    assert [c.estado_anterior for c in historial] == [
        None,
        "PREPARADO",
        "PRECINTADO",
        "EN_TRANSITO",
        "RECIBIDO",
    ]

    # Intento directo de UPDATE o DELETE sobre cambio_estado_bulto debe fallar por trigger V2
    with pytest.raises(sqlite3.IntegrityError):
        db.ejecutar("UPDATE cambio_estado_bulto SET estado_nuevo = 'RECHAZADO' WHERE id = ?", (historial[0].id,))
    with pytest.raises(sqlite3.IntegrityError):
        db.ejecutar("DELETE FROM cambio_estado_bulto WHERE id = ?", (historial[0].id,))

    # También vía repositorio se traduce a ValidacionError
    repo_hist = CambioEstadoBultoRepositorio(db)
    with pytest.raises(ValidacionError):
        repo_hist.eliminar(historial[0].id)


# =============================================================================
# 3. VALIDACIÓN V1 E INTEGRACIÓN CON STOCKSERVICE Y REPOSICIONSERVICE (P4, P5, P6)
# =============================================================================


def test_p4_armar_y_precintar_actualiza_orden_y_mantiene_stock_en_cd(
    logistica, stock, reposicion, orden_con_stock, escenario
):
    remito = logistica.armar_remito(
        orden_con_stock.id,
        [
            EspecificacionBulto([(escenario.producto, 6)], numero_precinto="PREC-101", peso_kg=6.0),
            EspecificacionBulto([(escenario.producto, 4), (escenario.otro_producto, 6)], numero_precinto="PREC-102"),
        ],
        usuario="turco",
    )

    assert remito.estado == EstadoRemito.EMITIDO
    assert len(remito.bultos) == 2
    assert all(isinstance(b.estado, Precintado) for b in remito.bultos)

    orden = reposicion.obtener(orden_con_stock.id)
    assert orden.estado == EstadoOrdenReposicion.EN_PREPARACION
    preparadas = {d.producto_id: d.cantidad_preparada for d in orden.detalles}
    assert preparadas == {escenario.producto: 10, escenario.otro_producto: 6}

    # Antes de despachar, el stock sigue en el CD y en la sucursal es 0
    assert stock.stock_disponible(escenario.cd, escenario.producto) == 100
    assert stock.stock_disponible(escenario.sucursal, escenario.producto) == 0


def test_p5_y_v1_despacho_descuenta_cd_e_ingresa_pendiente_en_sucursal_sin_habilitar_venta(
    logistica, stock, reposicion, orden_con_stock, escenario
):
    remito = logistica.armar_remito(
        orden_con_stock.id,
        [EspecificacionBulto([(escenario.producto, 10), (escenario.otro_producto, 6)], numero_precinto="PREC-201")],
    )

    despacho = logistica.registrar_despacho([remito.id], "Expreso Sur", "AB 999 CD", usuario="turco")

    assert despacho.remito_ids == [remito.id]
    remito_act = logistica.obtener_remito(remito.id)
    assert remito_act.estado == EstadoRemito.EN_TRANSITO
    assert isinstance(remito_act.bultos[0].estado, EnTransito)
    assert reposicion.obtener(orden_con_stock.id).estado == EstadoOrdenReposicion.DESPACHADA

    # CD descontó 10 y 6 unidades
    assert stock.stock_disponible(escenario.cd, escenario.producto) == 90
    assert stock.stock_disponible(escenario.cd, escenario.otro_producto) == 94

    # Sucursal tiene las unidades en PENDIENTE, pero 0 en DISPONIBLE (V1)
    stock_suc = stock.stock_de(escenario.sucursal, escenario.producto)
    assert (stock_suc.cantidad_pendiente, stock_suc.cantidad_disponible, stock_suc.cantidad_merma) == (10, 0, 0)
    with pytest.raises(StockInsuficienteError):
        stock.egresar(escenario.sucursal, escenario.producto, 1, Referencia("VENTA", 1))


def test_p6_y_v1_recibir_sin_verificar_mantiene_pendiente_y_verificar_habilita_venta(
    logistica, stock, reposicion, orden_con_stock, escenario, reloj
):
    remito = logistica.armar_remito(
        orden_con_stock.id,
        [EspecificacionBulto([(escenario.producto, 10), (escenario.otro_producto, 6)], numero_precinto="PREC-301")],
    )
    reloj.avanzar(hours=1)
    logistica.registrar_despacho([remito.id], "Expreso Sur", "AB 999 CD")

    # Paso A: Llegada del remito a la sucursal
    reloj.avanzar(hours=4)
    recepcion = logistica.recibir_remito(remito.id, recibido_por="encargado")
    bulto_rec = logistica.obtener_bulto(remito.bultos[0].id)
    assert isinstance(bulto_rec.estado, Recibido)
    assert logistica.obtener_remito(remito.id).estado == EstadoRemito.RECIBIDO
    # V1: Aunque el bulto llegó (Recibido), todavía NO está verificado -> stock_disponible sigue en 0
    assert stock.stock_disponible(escenario.sucursal, escenario.producto) == 0
    assert stock.stock_de(escenario.sucursal, escenario.producto).cantidad_pendiente == 10

    # Paso B: Controlar precinto íntegro y coincidente (incluso con minúsculas/espacios) y cerrar
    reloj.avanzar(minutes=30)
    control = logistica.registrar_control_bulto(
        recepcion.id, bulto_rec.id, numero_precinto_leido="  prec-301 ", precinto_integro=True
    )
    assert control.es_valido("PREC-301")
    assert control.resultado == "VERIFICADO"
    # Antes de cerrar la recepción del remito, el stock todavía no impactó
    assert stock.stock_disponible(escenario.sucursal, escenario.producto) == 0

    logistica.cerrar_recepcion(recepcion.id)

    # Recién con remito y bulto VERIFICADO pasa de pendiente a disponible (V1)
    stock_suc = stock.stock_de(escenario.sucursal, escenario.producto)
    assert (stock_suc.cantidad_pendiente, stock_suc.cantidad_disponible, stock_suc.cantidad_merma) == (0, 10, 0)
    assert logistica.obtener_remito(remito.id).estado == EstadoRemito.VERIFICADO
    assert reposicion.obtener(orden_con_stock.id).estado == EstadoOrdenReposicion.CERRADA_COMPLETA

    # Ahora sí se puede vender en la sucursal
    stock.egresar(escenario.sucursal, escenario.producto, 4, Referencia("VENTA", 10))
    assert stock.stock_disponible(escenario.sucursal, escenario.producto) == 6


def test_v1_precinto_roto_o_adulterado_rechaza_bulto_registra_merma_y_no_habilita_venta(
    logistica, stock, reposicion, orden_con_stock, escenario, reloj
):
    remito = logistica.armar_remito(
        orden_con_stock.id,
        [
            EspecificacionBulto([(escenario.producto, 10)], numero_precinto="PREC-ROTO"),
            EspecificacionBulto([(escenario.otro_producto, 6)], numero_precinto="PREC-ORIG"),
        ],
    )
    reloj.avanzar(hours=1)
    logistica.registrar_despacho([remito.id], "Flete Norte", "AC 111 ZZ")
    b_roto, b_adulterado = remito.bultos

    reloj.avanzar(hours=5)
    logistica.procesar_recepcion_completa(
        remito.id,
        recibido_por="encargado",
        controles_por_bulto=[
            (b_roto.id, "PREC-ROTO", False, "Llegó cortado"),
            (b_adulterado.id, "PREC-FALSO", True, "No coincide el número"),
        ],
    )

    assert isinstance(logistica.obtener_bulto(b_roto.id).estado, Rechazado)
    assert isinstance(logistica.obtener_bulto(b_adulterado.id).estado, Rechazado)
    assert logistica.obtener_remito(remito.id).estado == EstadoRemito.VERIFICADO_CON_RECHAZOS
    assert reposicion.obtener(orden_con_stock.id).estado == EstadoOrdenReposicion.CERRADA_CON_FALTANTES

    # Todo fue a merma, disponible = 0, pendiente = 0 -> no habilita venta (V1)
    s_prod1 = stock.stock_de(escenario.sucursal, escenario.producto)
    s_prod2 = stock.stock_de(escenario.sucursal, escenario.otro_producto)
    assert (s_prod1.cantidad_pendiente, s_prod1.cantidad_disponible, s_prod1.cantidad_merma) == (0, 0, 10)
    assert (s_prod2.cantidad_pendiente, s_prod2.cantidad_disponible, s_prod2.cantidad_merma) == (0, 0, 6)

    with pytest.raises(StockInsuficienteError):
        stock.egresar(escenario.sucursal, escenario.producto, 1, Referencia("VENTA", 1))


def test_recepcion_mixta_verifica_un_bulto_y_rechaza_otro(
    logistica, stock, reposicion, orden_con_stock, escenario, reloj
):
    remito = logistica.armar_remito(
        orden_con_stock.id,
        [
            EspecificacionBulto([(escenario.producto, 6)], numero_precinto="PREC-OK"),
            EspecificacionBulto([(escenario.producto, 4), (escenario.otro_producto, 6)], numero_precinto="PREC-MAL"),
        ],
    )
    logistica.registrar_despacho([remito.id], "Flete Mix", "AD 222 BB")
    b_ok, b_mal = remito.bultos

    logistica.procesar_recepcion_completa(
        remito.id,
        recibido_por="encargado",
        controles_por_bulto=[
            (b_ok.id, "PREC-OK", True, "Intacto"),
            (b_mal.id, "PREC-MAL", False, "Roto"),
        ],
    )

    s_prod1 = stock.stock_de(escenario.sucursal, escenario.producto)
    assert (s_prod1.cantidad_disponible, s_prod1.cantidad_merma, s_prod1.cantidad_pendiente) == (6, 4, 0)
    assert logistica.obtener_remito(remito.id).estado == EstadoRemito.VERIFICADO_CON_RECHAZOS
    orden_final = reposicion.obtener(orden_con_stock.id)
    assert orden_final.estado == EstadoOrdenReposicion.CERRADA_CON_FALTANTES


def test_integracion_con_observer_y_reporte_r4_transito(
    logistica, stock, reposicion, orden_con_stock, escenario, definir_minimo, reloj, db
):
    definir_minimo(escenario.producto, escenario.cd, 95)
    alerta = AlertaStockMinimo(stock.minimos)
    stock.suscribir(alerta)

    remito = logistica.armar_remito(
        orden_con_stock.id,
        [EspecificacionBulto([(escenario.producto, 10), (escenario.otro_producto, 6)], numero_precinto="PREC-R4")],
    )
    t_salida = reloj.avanzar(hours=1)
    logistica.registrar_despacho([remito.id], "Expreso R4", "AE 555 FF")

    # El CD quedó en 90 (<= mínimo 95), por lo que el Observer disparó alerta
    assert len(alerta.alertas()) == 1
    assert alerta.alertas()[0].ubicacion_id == escenario.cd

    # 8 horas después se recepciona y verifica en la sucursal
    reloj.avanzar(hours=8)
    logistica.procesar_recepcion_completa(
        remito.id,
        recibido_por="local1",
        controles_por_bulto=[(remito.bultos[0].id, "PREC-R4", True, "OK")],
    )

    resumen_r4 = ReporteTransito(db).consultar(t_salida.date(), t_salida.date())
    assert len(resumen_r4.filas) == 1
    assert resumen_r4.filas[0].remito_id == remito.id
    assert resumen_r4.filas[0].horas == pytest.approx(8.0)
    assert resumen_r4.filas[0].unidades == 16


# =============================================================================
# 4. UNICIDAD Y VALIDACIONES DE NEGOCIO
# =============================================================================


def test_unicidad_de_codigo_bulto_precinto_y_remito(logistica, orden_con_stock, escenario):
    remito = logistica.crear_remito(orden_con_stock.id, numero_remito="REM-UNICO")
    with pytest.raises(EntidadDuplicadaError):
        logistica.crear_remito(orden_con_stock.id, numero_remito="rem-unico")

    logistica.armar_bulto(
        remito.id, [(escenario.producto, 3)], codigo="BUL-UNICO", numero_precinto="PREC-UNICO"
    )
    with pytest.raises(EntidadDuplicadaError):
        logistica.armar_bulto(remito.id, [(escenario.producto, 2)], codigo="bul-unico")
    with pytest.raises(EntidadDuplicadaError):
        logistica.armar_bulto(remito.id, [(escenario.producto, 2)], numero_precinto="prec-unico")


def test_no_permite_preparar_mas_de_lo_solicitado_ni_sin_stock_cd(
    logistica, stock, reposicion, orden_con_stock, escenario
):
    remito = logistica.crear_remito(orden_con_stock.id)
    with pytest.raises(ValidacionError):
        logistica.armar_bulto(remito.id, [(escenario.producto, 11)])  # solicitó 10

    # Si el CD no tiene stock suficiente, no permite empaquetar
    nec_grande = reposicion.crear_necesidad(escenario.sucursal, [(escenario.producto, 500)])
    orden_grande = reposicion.consolidar([nec_grande.id])
    rem_grande = logistica.crear_remito(orden_grande.id)
    with pytest.raises(StockInsuficienteError):
        logistica.armar_bulto(rem_grande.id, [(escenario.producto, 200)])


def test_no_permite_despachar_bulto_sin_precintar_ni_cerrar_recepcion_incompleta(
    logistica, orden_con_stock, escenario
):
    remito = logistica.crear_remito(orden_con_stock.id)
    bulto = logistica.armar_bulto(remito.id, [(escenario.producto, 5)])  # sin precinto -> queda Preparado

    with pytest.raises(TransicionInvalidaError):
        logistica.registrar_despacho([remito.id], "Camión", "AA 123 BB")

    logistica.precintar_bulto(bulto.id, "PREC-LISTO")
    logistica.registrar_despacho([remito.id], "Camión", "AA 123 BB")
    recepcion = logistica.recibir_remito(remito.id, recibido_por="encargado")

    # No se puede cerrar la recepción si el bulto todavía está en Recibido (sin controlar)
    with pytest.raises(TransicionInvalidaError):
        logistica.cerrar_recepcion(recepcion.id)


def test_datos_prueba_logistica_carga_escenario_completo(db):
    cargar_datos_de_prueba(db)
    cargar_stock_de_prueba(db)
    resumen = cargar_logistica_de_prueba(db)

    assert resumen["remitos emitidos y despachados"] == 3
    assert resumen["bultos rechazados (en merma para R5)"] == 2
    assert resumen["bultos en tránsito (listos para recibir)"] == 2
    with pytest.raises(ValidacionError):
        cargar_logistica_de_prueba(db)


# =============================================================================
# 5. SUITE COMPATIBLE CON PYTHON -M UNITTEST
# =============================================================================


class TestLogisticaUnittest(TestConBaseEnMemoria):
    """Garantiza cobertura completa también cuando se ejecuta `python -m unittest`."""

    def setUp(self) -> None:
        super().setUp()
        self.cd = self.db.ejecutar(
            "INSERT INTO ubicacion (tipo, codigo, nombre) VALUES ('CD', 'CD1', 'Centro')"
        ).lastrowid
        self.sucursal = self.db.ejecutar(
            "INSERT INTO ubicacion (tipo, codigo, nombre, punto_venta) VALUES ('SUCURSAL', 'S1', 'Local 1', 1)"
        ).lastrowid
        cat = self.db.ejecutar("INSERT INTO categoria (nombre) VALUES ('General')").lastrowid
        self.producto = self.db.ejecutar(
            "INSERT INTO producto (sku, nombre, categoria_id, costo_actual, precio_venta_actual) "
            "VALUES ('SKU-1', 'Producto 1', ?, 100, 150)",
            (cat,),
        ).lastrowid
        self.stock = StockService(self.db)
        self.reposicion = ReposicionService(self.db)
        self.logistica = LogisticaService(self.db, self.stock, self.reposicion)
        self.stock.ingresar_compra(self.cd, self.producto, 50, REF_COMPRA, Decimal("100"))

    def test_flujo_completo_verificado_y_rechazado_e_inmutabilidad(self) -> None:
        nec = self.reposicion.crear_necesidad(self.sucursal, [(self.producto, 10)])
        orden = self.reposicion.consolidar([nec.id])
        remito = self.logistica.armar_remito(
            orden.id,
            [
                EspecificacionBulto([(self.producto, 6)], numero_precinto="PREC-U1"),
                EspecificacionBulto([(self.producto, 4)], numero_precinto="PREC-U2"),
            ],
        )
        self.logistica.registrar_despacho([remito.id], "Transporte UTN", "AF 000 AA")
        self.assertEqual(self.stock.stock_disponible(self.sucursal, self.producto), 0)

        b1, b2 = remito.bultos
        self.logistica.procesar_recepcion_completa(
            remito.id,
            recibido_por="receptor",
            controles_por_bulto=[
                (b1.id, "PREC-U1", True, "OK"),
                (b2.id, "PREC-U2", False, "Precinto cortado"),
            ],
        )
        st = self.stock.stock_de(self.sucursal, self.producto)
        self.assertEqual((st.cantidad_disponible, st.cantidad_merma, st.cantidad_pendiente), (6, 4, 0))
        self.assertEqual(len(self.logistica.historial_bulto(b1.id)), 5)
        with self.assertRaises(sqlite3.IntegrityError):
            self.db.ejecutar("DELETE FROM cambio_estado_bulto")
