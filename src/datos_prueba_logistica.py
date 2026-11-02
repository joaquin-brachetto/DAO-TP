"""Datos de prueba de logística (turco): bultos, precintos, remitos, despachos,
recepciones verificadas, rechazos por precinto roto/adulterado y remitos en tránsito.

Se ejecuta DESPUÉS de cargar los datos de prueba de maestros (`src.datos_prueba`)
y el stock inicial de inventario (`src.datos_prueba_inventario`), pasando al 100%
por `ReposicionService` y `LogisticaService` para respetar todas las reglas P4, P5,
P6, V1, V2 y dejar poblados los reportes R4 y R5:

1. Escenario 1 (Sucursal Centro – 100% Verificado):
   - Orden de reposición consolidada, empaquetada en 2 bultos (`BUL-0001`, `BUL-0002`)
     con precintos `PREC-1001` y `PREC-1002`, despachada en `REM-0001`, recibida y
     100% verificada. Suma stock disponible en el local y cierra como `CERRADA_COMPLETA`.
2. Escenario 2 (Sucursal Nueva Córdoba – Con Rechazos por Precinto Roto y Adulterado):
   - Orden de reposición consolidada, empaquetada en 3 bultos (`BUL-0003`, `BUL-0004`,
     `BUL-0005`) con precintos `PREC-2001`, `PREC-2002` y `PREC-2003`, despachada en
     `REM-0002` y recepcionada en la sucursal:
     * `BUL-0003`: precinto `PREC-2001` íntegro y coincidente -> `VERIFICADO` (a disponible).
     * `BUL-0004`: precinto `PREC-2002` llega roto/violado -> `RECHAZADO` (a merma).
     * `BUL-0005`: precinto leído `PREC-9999` no coincide con `PREC-2003` -> `RECHAZADO` (a merma).
   - El remito queda `VERIFICADO_CON_RECHAZOS` y la orden cierra como `CERRADA_CON_FALTANTES`.
3. Escenario 3 (Sucursal Cerro de las Rosas – En Tránsito + Orden lista para armar):
   - Remito `REM-0003` con 2 bultos (`BUL-0006` con `PREC-3001` y `BUL-0007` con `PREC-3002`)
     actualmente `EN_TRANSITO` (listo para demostrar en vivo la pantalla «Recepción en sucursal»).
   - Una orden de reposición adicional en estado `PENDIENTE` (lista para demostrar en vivo
     «Armado de bultos y remitos» y «Despacho»).

Uso:
    python -m src.datos_prueba_logistica
o desde el menú Logística → «Cargar datos de prueba de logística».
"""

from __future__ import annotations

from datetime import datetime, timedelta

from src.dominio.logistica.modelos import CodigoEstadoBulto
from src.excepciones import ValidacionError
from src.persistencia.conexion import BaseDeDatos
from src.servicios.logistica_service import EspecificacionBulto, LogisticaService
from src.servicios.reposicion_service import ReposicionService
from src.servicios.stock_service import StockService


class _Reloj:
    def __init__(self, momento: datetime) -> None:
        self.momento = momento

    def __call__(self) -> datetime:
        return self.momento

    def ir_a(self, momento: datetime) -> None:
        self.momento = momento


def cargar_logistica_de_prueba(
    db: BaseDeDatos | None = None,
    stock_service: StockService | None = None,
) -> dict[str, int]:
    """Carga un escenario completo de logística y devuelve el resumen de registros creados."""
    db = db or BaseDeDatos()
    if db.consultar_uno("SELECT 1 FROM producto LIMIT 1") is None:
        raise ValidacionError(
            "Primero cargá los datos de prueba de maestros (Archivo → Cargar datos de prueba)."
        )
    if db.consultar_uno("SELECT 1 FROM stock LIMIT 1") is None:
        raise ValidacionError(
            "Primero cargá el stock inicial de prueba (Inventario → Cargar stock de prueba)."
        )
    if db.consultar_uno("SELECT 1 FROM remito LIMIT 1") is not None:
        raise ValidacionError(
            "Ya hay datos de logística cargados. Para recargarlos, borrá datos/ventas.db y empezá de nuevo."
        )

    sucursales = {
        f["codigo"]: f["id"]
        for f in db.consultar(
            "SELECT id, codigo FROM ubicacion WHERE tipo = 'SUCURSAL' AND activa = 1 ORDER BY codigo"
        )
    }
    if len(sucursales) < 2:
        raise ValidacionError("Se necesitan al menos dos sucursales activas para los datos de logística.")

    codigos_suc = list(sucursales.keys())
    suc_centro = sucursales.get("SUC01", sucursales[codigos_suc[0]])
    suc_nueva_cba = sucursales.get("SUC02", sucursales[codigos_suc[min(1, len(codigos_suc) - 1)]])
    suc_cerro = sucursales.get("SUC03", sucursales[codigos_suc[-1]])

    productos = {
        f["sku"]: f["id"]
        for f in db.consultar("SELECT id, sku FROM producto WHERE activo = 1 ORDER BY id")
    }

    def prod(sku: str, indice_fallback: int = 0) -> int:
        if sku in productos:
            return productos[sku]
        ids = list(productos.values())
        return ids[indice_fallback % len(ids)]

    ahora = datetime.now().replace(microsecond=0)
    reloj = _Reloj(ahora - timedelta(days=3))
    stock = stock_service or StockService(db, ahora=reloj)
    reposicion = ReposicionService(db)
    logistica = LogisticaService(db, stock_service=stock, reposicion_service=reposicion, ahora=reloj)

    with db.transaccion():
        # ---------------------------------------------------------------------
        # 1. Sucursal Centro: Remito REM-0001 despachado, recibido y 100% VERIFICADO
        # ---------------------------------------------------------------------
        t_emision_1 = ahora - timedelta(days=3, hours=6)
        t_despacho_1 = ahora - timedelta(days=3, hours=4)
        t_recepcion_1 = ahora - timedelta(days=2, hours=18)

        nec_1 = reposicion.crear_necesidad(
            suc_centro,
            [(prod("YER-1K", 0), 6), (prod("ARR-1K", 1), 8), (prod("AGU-1500", 2), 10)],
            fecha=t_emision_1.date(),
        )
        orden_1 = reposicion.consolidar([nec_1.id], fecha=t_emision_1)
        remito_1 = logistica.armar_remito(
            orden_1.id,
            [
                EspecificacionBulto(
                    renglones=[(prod("YER-1K", 0), 6), (prod("ARR-1K", 1), 8)],
                    numero_precinto="PREC-1001",
                    peso_kg=14.5,
                ),
                EspecificacionBulto(
                    renglones=[(prod("AGU-1500", 2), 10)],
                    numero_precinto="PREC-1002",
                    peso_kg=15.2,
                ),
            ],
            usuario="turco",
            fecha_hora=t_emision_1,
        )
        logistica.registrar_despacho(
            [remito_1.id],
            transportista="Expreso Córdoba Sur",
            patente="AF 123 CD",
            usuario="turco",
            observaciones="Salida normal matutina hacia Sucursal Centro",
            fecha_hora=t_despacho_1,
        )
        b1_1, b1_2 = remito_1.bultos
        logistica.procesar_recepcion_completa(
            remito_id=remito_1.id,
            recibido_por="encargado_centro",
            controles_por_bulto=[
                (b1_1.id, "PREC-1001", True, "Precinto intacto y mercadería completa"),
                (b1_2.id, "PREC-1002", True, "Precinto intacto"),
            ],
            observaciones="Recepción conforme al 100%",
            fecha_hora=t_recepcion_1,
        )

        # ---------------------------------------------------------------------
        # 2. Sucursal Nueva Córdoba: Remito REM-0002 con bultos VERIFICADO y RECHAZADOs
        # ---------------------------------------------------------------------
        t_emision_2 = ahora - timedelta(days=2, hours=8)
        t_despacho_2 = ahora - timedelta(days=2, hours=6)
        t_recepcion_2 = ahora - timedelta(days=1, hours=20)

        nec_2 = reposicion.crear_necesidad(
            suc_nueva_cba,
            [
                (prod("GAS-2250", 3), 12),
                (prod("VIN-750", 4), 6),
                (prod("QUE-CRE", 5), 4),
                (prod("JAB-3K", 6), 5),
            ],
            fecha=t_emision_2.date(),
        )
        orden_2 = reposicion.consolidar([nec_2.id], fecha=t_emision_2)
        remito_2 = logistica.armar_remito(
            orden_2.id,
            [
                EspecificacionBulto(
                    renglones=[(prod("GAS-2250", 3), 12)],
                    numero_precinto="PREC-2001",
                    peso_kg=27.5,
                ),
                EspecificacionBulto(
                    renglones=[(prod("VIN-750", 4), 6), (prod("QUE-CRE", 5), 4)],
                    numero_precinto="PREC-2002",
                    peso_kg=12.8,
                ),
                EspecificacionBulto(
                    renglones=[(prod("JAB-3K", 6), 5)],
                    numero_precinto="PREC-2003",
                    peso_kg=15.0,
                ),
            ],
            usuario="turco",
            fecha_hora=t_emision_2,
        )
        logistica.registrar_despacho(
            [remito_2.id],
            transportista="Logística Sierras SRL",
            patente="AD 890 XY",
            usuario="turco",
            observaciones="Envío refrigerado y seco a Nueva Córdoba",
            fecha_hora=t_despacho_2,
        )
        b2_1, b2_2, b2_3 = remito_2.bultos
        logistica.procesar_recepcion_completa(
            remito_id=remito_2.id,
            recibido_por="encargado_nva_cba",
            controles_por_bulto=[
                (b2_1.id, "PREC-2001", True, "Precinto verificado sin anomalías"),
                (b2_2.id, "PREC-2002", False, "Precinto plástico cortado al bajar del camión"),
                (b2_3.id, "PREC-9999", True, "Precinto sustituido en tránsito, numeración adulterada"),
            ],
            observaciones="Se rechazan 2 bultos por anomalías de seguridad en precintos (V1)",
            fecha_hora=t_recepcion_2,
        )

        # ---------------------------------------------------------------------
        # 3. Sucursal Cerro de las Rosas: Remito REM-0003 actualmente EN_TRANSITO
        #    y Orden #4 PENDIENTE para probar Armado y Despacho en vivo
        # ---------------------------------------------------------------------
        t_emision_3 = ahora - timedelta(hours=5)
        t_despacho_3 = ahora - timedelta(hours=3)

        nec_3 = reposicion.crear_necesidad(
            suc_cerro,
            [(prod("ACE-900", 7), 8), (prod("LEC-1L", 8), 10)],
            fecha=t_emision_3.date(),
        )
        orden_3 = reposicion.consolidar([nec_3.id], fecha=t_emision_3)
        remito_3 = logistica.armar_remito(
            orden_3.id,
            [
                EspecificacionBulto(
                    renglones=[(prod("ACE-900", 7), 8)],
                    numero_precinto="PREC-3001",
                    peso_kg=8.0,
                ),
                EspecificacionBulto(
                    renglones=[(prod("LEC-1L", 8), 10)],
                    numero_precinto="PREC-3002",
                    peso_kg=10.5,
                ),
            ],
            usuario="turco",
            fecha_hora=t_emision_3,
        )
        logistica.registrar_despacho(
            [remito_3.id],
            transportista="Transporte del Norte SA",
            patente="AG 456 ZZ",
            usuario="turco",
            observaciones="En tránsito hacia Cerro de las Rosas (listo para recepcionar)",
            fecha_hora=t_despacho_3,
        )

        nec_4 = reposicion.crear_necesidad(
            suc_centro,
            [(prod("FID-500", 9), 10), (prod("HAR-1K", 10), 8)],
            fecha=ahora.date(),
        )
        reposicion.consolidar([nec_4.id], fecha=ahora)

    todos_bultos = logistica.listar_bultos()
    rechazados = [b for b in todos_bultos if b.nombre_estado == CodigoEstadoBulto.RECHAZADO.value]
    verificados = [b for b in todos_bultos if b.nombre_estado == CodigoEstadoBulto.VERIFICADO.value]
    en_transito = [b for b in todos_bultos if b.nombre_estado == CodigoEstadoBulto.EN_TRANSITO.value]

    return {
        "remitos emitidos y despachados": 3,
        "bultos totales con trazabilidad": len(todos_bultos),
        "bultos verificados (en stock disponible)": len(verificados),
        "bultos rechazados (en merma para R5)": len(rechazados),
        "bultos en tránsito (listos para recibir)": len(en_transito),
        "órdenes pendientes de empaquetar": 1,
    }


def main() -> None:
    db = BaseDeDatos()
    db.inicializar_esquema()
    try:
        cantidades = cargar_logistica_de_prueba(db)
    except ValidacionError as error:
        print(error)
        return
    print(f"Datos de prueba de logística cargados en {db.ruta}:")
    for tipo, cantidad in cantidades.items():
        print(f"  {cantidad:>4} {tipo}")


if __name__ == "__main__":
    main()
