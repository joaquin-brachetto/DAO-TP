"""Resumen de la pantalla de Inicio: junta lo que ya calculan los otros módulos."""

from datetime import date, datetime, time, timedelta

from src.dominio.inventario.modelos import EstadoNecesidad, EstadoOrdenReposicion
from src.dominio.logistica.modelos import CodigoEstadoBulto, EstadoRemito
from src.persistencia.conexion import BaseDeDatos
from src.persistencia.repositorio_tablero import TableroRepositorio
from src.reportes.existencias_reporte import ReporteExistencias
from src.reportes.inventario_reporte import ReporteMovimientos
from src.servicios.logistica_service import LogisticaService
from src.servicios.reposicion_service import ReposicionService
from src.servicios.stock_service import StockService

DIAS_GRAFICO = 7


class TableroService:
    def __init__(
        self,
        db: BaseDeDatos,
        stock: StockService,
        logistica: LogisticaService,
        reposicion: ReposicionService,
    ) -> None:
        self.db = db
        self.repo = TableroRepositorio(db)
        self.stock = stock
        self.logistica = logistica
        self.reposicion = reposicion

    def datos_cargados(self) -> dict[str, bool]:
        return self.repo.datos_cargados()

    def resumen(self, hoy: date | None = None) -> dict:
        hoy = hoy or date.today()
        inicio_hoy = datetime.combine(hoy, time.min)
        manana = inicio_hoy + timedelta(days=1)
        primer_dia = hoy - timedelta(days=DIAS_GRAFICO - 1)

        por_dia = {fila["dia"]: fila["total"] for fila in self.repo.cobrado_por_dia(
            datetime.combine(primer_dia, time.min), manana)}
        ventas_semana = [
            {"dia": dia, "total": por_dia.get(dia.isoformat(), 0)}
            for dia in (primer_dia + timedelta(days=n) for n in range(DIAS_GRAFICO))
        ]
        cobros_hoy = {fila["medio_pago"]: fila["total"] for fila in self.repo.cobrado_por_medio(inicio_hoy, manana)}

        en_minimo = ReporteExistencias(self.stock, self.db).consultar(solo_en_minimo=True).filas
        valorizado = ReporteMovimientos(self.db).consultar(hoy, hoy).total_valorizado
        remitos_en_transito = self.logistica.listar_remitos(estado=EstadoRemito.EN_TRANSITO)

        return {
            "ventas_hoy": self.repo.cantidad_de_ventas(inicio_hoy, manana),
            "cobrado_hoy": sum(cobros_hoy.values()),
            "cobros_hoy": cobros_hoy,
            "ventas_semana": ventas_semana,
            "stock_valorizado": valorizado,
            "remitos_en_transito": [r.destino_id for r in remitos_en_transito],
            "en_minimo": [
                {"producto_id": f.producto_id, "ubicacion_id": f.ubicacion_id,
                 "disponible": f.disponible, "minimo": f.minimo}
                for f in en_minimo
            ],
            "necesidades_pendientes": len(self.reposicion.listar_necesidades(EstadoNecesidad.PENDIENTE)),
            "ordenes_por_preparar": len(self.reposicion.listar(EstadoOrdenReposicion.PENDIENTE))
            + len(self.reposicion.listar(EstadoOrdenReposicion.EN_PREPARACION)),
            "bultos_en_transito": len(self.logistica.listar_bultos(estado=CodigoEstadoBulto.EN_TRANSITO)),
            "ultimas_ventas": self.repo.ultimas_ventas(6),
        }
