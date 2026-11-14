"""Los seis reportes, con sus filtros, y su exportación a PDF o CSV.

Cada reporte se arma una sola vez como `DocumentoReporte` (el mismo objeto que usan los
exportadores). La pantalla lo recibe en JSON y los botones «Exportar» lo pasan al exportador
que corresponda (patrón Strategy: `exportador_para("PDF")` o `exportador_para("CSV")`).
"""

import re
import tempfile
import unicodedata
from collections.abc import Callable
from datetime import date, timedelta
from io import BytesIO
from pathlib import Path

from flask import Blueprint, jsonify, request, send_file

from src.excepciones import ValidacionError
from src.reportes.existencias_reporte import ReporteExistencias
from src.reportes.exportacion import DocumentoReporte, GraficoReporte, SeccionReporte, exportador_para
from src.reportes.inventario_reporte import NOMBRE_TIPO, ReporteMovimientos, ReporteTransito, TipoMovimiento, formato_duracion
from src.reportes.logistica_reporte import NOMBRE_ANOMALIA, ReporteBultosRechazados, TipoAnomaliaPrecinto
from src.reportes.productos_reporte import ReporteProductosVendidos
from src.reportes.ventas_reporte import ReporteVentas
from src.web.utiles import NOMBRES_MEDIO, arg_entero, dinero, fecha, fecha_hora, miles, porcentaje, servicios

bp = Blueprint("reportes", __name__)

DIAS_POR_DEFECTO = 30


class Filtros:
    """Lee los filtros de la URL y arma el texto «Desde: … · Sucursal: …» que va en el PDF."""

    def __init__(self) -> None:
        self.s = servicios()
        self.partes: list[str] = []

    def periodo(self) -> tuple[date, date]:
        hoy = date.today()
        desde = fecha(request.args.get("desde"), "Desde", hoy - timedelta(days=DIAS_POR_DEFECTO))
        hasta = fecha(request.args.get("hasta"), "Hasta", hoy)
        if desde > hasta:
            raise ValidacionError("La fecha «Desde» no puede ser posterior a «Hasta».")
        self.partes += [f"Desde: {desde:%d/%m/%Y}", f"Hasta: {hasta:%d/%m/%Y}"]
        return desde, hasta

    def ubicacion(self, nombre: str = "ubicacion", etiqueta: str = "Ubicación") -> int | None:
        ubicacion_id = arg_entero(nombre, etiqueta)
        texto = self.s.ubicaciones.obtener(ubicacion_id).nombre if ubicacion_id else "Todas"
        self.partes.append(f"{etiqueta}: {texto}")
        return ubicacion_id

    def categoria(self) -> int | None:
        categoria_id = arg_entero("categoria", "Categoría")
        nombres = {c.id: c.nombre for c in self.s.categorias.listar()}
        self.partes.append(f"Categoría: {nombres.get(categoria_id, 'Todas')}")
        return categoria_id

    def opcion(self, nombre: str, etiqueta: str, opciones: dict[str, str]) -> str | None:
        valor = request.args.get(nombre) or None
        if valor is not None and valor not in opciones:
            raise ValidacionError(f"«{etiqueta}» no es válido.")
        self.partes.append(f"{etiqueta}: {opciones[valor] if valor else 'Todos'}")
        return valor

    def texto(self) -> str:
        return " · ".join(self.partes)


def _documento(titulo, filtros, resumen, grafico, secciones) -> DocumentoReporte:
    documento = DocumentoReporte(
        titulo=titulo,
        filtros=filtros.texto(),
        resumen=" · ".join(f"{etiqueta}: {valor}" for etiqueta, valor in resumen),
        secciones=secciones,
        grafico=grafico,
    )
    documento.indicadores = resumen  # para los recuadros de la pantalla
    return documento


# --- R1: existencias y stock mínimo -------------------------------------------------------------------


def r1_existencias() -> DocumentoReporte:
    f = Filtros()
    ubicacion_id, categoria_id = f.ubicacion(), f.categoria()
    solo_minimo = request.args.get("solo_minimo") == "1"
    if solo_minimo:
        f.partes.append("Solo en stock mínimo")
    r = ReporteExistencias(f.s.stock, f.s.db).consultar(ubicacion_id, categoria_id, solo_minimo)
    criticos = r.menor_cobertura(10)
    return _documento(
        "R1 – Existencias y stock mínimo", f,
        [("Renglones", miles(len(r.filas))), ("En o bajo el mínimo", miles(r.cantidad_en_minimo)),
         ("Unidades disponibles", miles(r.total_unidades)), ("Valorizado al costo", dinero(r.total_valorizado))],
        GraficoReporte("Productos más cerca de su mínimo (unidades disponibles)",
                       [f"{x.producto} – {x.codigo_ubicacion}" for x in criticos],
                       [float(x.disponible) for x in criticos], [x.en_minimo for x in criticos]),
        [SeccionReporte("Existencias", ["Ubicación", "SKU", "Producto", "Categoría", "Disponible", "Mínimo", "Faltante", "Valorizado", "Estado"], [
            [x.ubicacion, x.sku, x.producto, x.categoria, miles(x.disponible), miles(x.minimo), miles(x.faltante),
             dinero(x.valorizado), "En mínimo" if x.en_minimo else "Normal"]
            for x in r.filas
        ])],
    )


# --- R2: productos más vendidos y margen -------------------------------------------------------------


def r2_productos() -> DocumentoReporte:
    f = Filtros()
    desde, hasta = f.periodo()
    ubicacion_id, categoria_id = f.ubicacion("sucursal", "Sucursal"), f.categoria()
    r = ReporteProductosVendidos(f.s.db).consultar(desde, hasta, ubicacion_id, categoria_id)
    top = r.top(10)
    return _documento(
        "R2 – Productos más vendidos y margen", f,
        [("Unidades vendidas", miles(r.total_unidades)), ("Ingresos", dinero(r.total_ingresos)),
         ("Margen", dinero(r.total_margen)), ("Margen sobre ventas", porcentaje(r.margen_porcentual))],
        GraficoReporte("Los diez productos más vendidos (unidades)", [x.producto for x in top],
                       [float(x.unidades) for x in top], [x.es_perdida for x in top]),
        [SeccionReporte("Productos vendidos", ["SKU", "Producto", "Categoría", "Unidades", "Ingresos", "Costo", "Margen", "Margen %"], [
            [x.sku, x.producto, x.categoria, miles(x.unidades), dinero(x.ingresos), dinero(x.costo), dinero(x.margen), porcentaje(x.margen_porcentual)]
            for x in r.filas
        ])],
    )


# --- R3: movimientos y valorización del inventario --------------------------------------------------


def r3_movimientos() -> DocumentoReporte:
    f = Filtros()
    desde, hasta = f.periodo()
    ubicacion_id, categoria_id = f.ubicacion(), f.categoria()
    tipo = f.opcion("tipo", "Tipo", {t.value: NOMBRE_TIPO[t] for t in TipoMovimiento})
    r = ReporteMovimientos(f.s.db).consultar(desde, hasta, ubicacion_id, categoria_id, TipoMovimiento(tipo) if tipo else None)
    (u_ent, v_ent), (u_sal, v_sal) = r.entradas, r.salidas
    return _documento(
        "R3 – Movimientos y valorización del inventario", f,
        [("Movimientos", miles(len(r.movimientos))), ("Entradas", f"{miles(u_ent)} u. · {dinero(v_ent)}"),
         ("Salidas", f"{miles(u_sal)} u. · {dinero(v_sal)}"), ("Stock valorizado", dinero(r.total_valorizado))],
        GraficoReporte("Stock valorizado al costo actual, por ubicación", [x.ubicacion for x in r.valorizacion],
                       [float(x.valor_total) for x in r.valorizacion]),
        [
            SeccionReporte("Entradas y salidas por tipo", ["Tipo", "Sentido", "Movimientos", "Unidades", "Valor"], [
                [t.nombre, str(t.sentido), miles(t.movimientos), miles(t.unidades), dinero(t.valor)] for t in r.por_tipo()
            ]),
            SeccionReporte("Stock valorizado por ubicación", ["Ubicación", "Disponible", "Pendiente", "Merma", "Valor (disp. + pend.)", "Valor merma"], [
                [x.ubicacion, miles(x.disponible), miles(x.pendiente), miles(x.merma), dinero(x.valor_total), dinero(x.valor_merma)]
                for x in r.valorizacion
            ]),
            SeccionReporte("Detalle de movimientos", ["Fecha", "Ubicación", "Producto", "Tipo", "Cantidad", "Valor", "Documento"], [
                [fecha_hora(m.fecha_hora), m.ubicacion, m.producto, NOMBRE_TIPO[m.tipo], miles(m.cantidad), dinero(m.valor), m.documento]
                for m in sorted(r.movimientos, key=lambda m: m.fecha_hora, reverse=True)
            ]),
        ],
    )


# --- R4: tiempo de tránsito CD → locales ------------------------------------------------------------


def r4_transito() -> DocumentoReporte:
    f = Filtros()
    desde, hasta = f.periodo()
    sucursal_id = f.ubicacion("sucursal", "Sucursal")
    r = ReporteTransito(f.s.db).consultar(desde, hasta, sucursal_id)
    por_sucursal = r.por_sucursal()
    return _documento(
        "R4 – Tiempo promedio de tránsito CD → locales", f,
        [("Remitos verificados", miles(len(r.recibidos))), ("En tránsito", miles(r.cantidad_en_transito)),
         ("Promedio general", formato_duracion(r.promedio_horas) if r.promedio_horas is not None else "—")],
        GraficoReporte("Tiempo promedio de tránsito por sucursal (horas)", [x.destino for x in por_sucursal],
                       [round(x.promedio_horas, 1) for x in por_sucursal]),
        [
            SeccionReporte("Promedio por sucursal", ["Sucursal", "Remitos", "Promedio", "Mínimo", "Máximo"], [
                [x.destino, miles(x.remitos), formato_duracion(x.promedio_horas), formato_duracion(x.minimo_horas), formato_duracion(x.maximo_horas)]
                for x in por_sucursal
            ]),
            SeccionReporte("Remitos del período", ["Origen", "Destino", "Despacho", "Recepción", "Tránsito", "Unidades", "Con rechazos"], [
                [x.origen, x.destino, fecha_hora(x.despacho), fecha_hora(x.recepcion), formato_duracion(x.horas),
                 miles(x.unidades), "Sí" if x.con_rechazos else "No"]
                for x in r.filas
            ]),
        ],
    )


# --- R5: bultos rechazados y mermas -------------------------------------------------------------------


def r5_rechazos() -> DocumentoReporte:
    f = Filtros()
    desde, hasta = f.periodo()
    sucursal_id, categoria_id = f.ubicacion("sucursal", "Sucursal"), f.categoria()
    anomalias = {t.value: NOMBRE_ANOMALIA[t.value] for t in TipoAnomaliaPrecinto if t != TipoAnomaliaPrecinto.TODOS}
    anomalia = f.opcion("anomalia", "Anomalía", anomalias)
    r = ReporteBultosRechazados(f.s.db).consultar(desde, hasta, sucursal_id, categoria_id, anomalia)
    return _documento(
        "R5 – Bultos rechazados y mermas", f,
        [("Bultos rechazados", miles(r.total_bultos_rechazados)), ("Unidades a merma", miles(r.total_unidades_merma)),
         ("Costo de la merma", dinero(r.total_valor_merma)), ("Tasa de rechazo", porcentaje(r.tasa_rechazo_global))],
        GraficoReporte("Costo de la merma por sucursal", [x.sucursal for x in r.por_sucursal],
                       [float(x.valor_merma) for x in r.por_sucursal], [x.bultos_rechazados > 0 for x in r.por_sucursal]),
        [
            SeccionReporte("Resumen por sucursal", ["Sucursal", "Bultos recibidos", "Verificados", "Rechazados", "% rechazo", "Unidades merma", "Costo merma"], [
                [x.sucursal, miles(x.total_bultos_recibidos), miles(x.bultos_verificados), miles(x.bultos_rechazados),
                 porcentaje(x.porcentaje_rechazo), miles(x.unidades_merma), dinero(x.valor_merma)]
                for x in r.por_sucursal
            ]),
            SeccionReporte("Bultos rechazados", ["Fecha", "Bulto", "Remito", "Sucursal", "Precinto colocado", "Precinto leído", "Anomalía", "Unidades", "Costo"], [
                [fecha_hora(x.fecha_rechazo), x.codigo_bulto, x.numero_remito, x.sucursal, x.precinto_colocado,
                 x.precinto_leido, x.tipo_anomalia, miles(x.unidades_totales), dinero(x.valor_merma)]
                for x in r.bultos_rechazados
            ]),
            SeccionReporte("Merma por producto", ["SKU", "Producto", "Categoría", "Sucursal", "Bultos", "Unidades", "Costo"], [
                [x.sku, x.producto, x.categoria, x.sucursal, miles(x.bultos_afectados), miles(x.unidades_merma), dinero(x.valor_merma)]
                for x in r.mermas_por_producto
            ]),
        ],
    )


# --- R6: ventas por período, local y medio de pago ------------------------------------------------------


def r6_ventas() -> DocumentoReporte:
    f = Filtros()
    desde, hasta = f.periodo()
    sucursal_id = f.ubicacion("sucursal", "Sucursal")
    medio = f.opcion("medio", "Medio de pago", NOMBRES_MEDIO)
    filas = [x for x in ReporteVentas(f.s.db).consultar(desde, hasta, sucursal_id) if not medio or x.medio_pago == medio]
    por_sucursal: dict[str, float] = {}
    for x in filas:
        por_sucursal[x.sucursal] = por_sucursal.get(x.sucursal, 0) + float(x.total_cobrado)
    total = sum((x.total_cobrado for x in filas), start=0)
    return _documento(
        "R6 – Ventas por período, local y medio de pago", f,
        [("Total cobrado", dinero(total)), ("Cobros", miles(sum(x.cantidad_ventas for x in filas))),
         ("Sucursales con ventas", miles(len(por_sucursal)))],
        GraficoReporte("Total cobrado por sucursal", list(por_sucursal), list(por_sucursal.values())),
        [SeccionReporte("Ventas por sucursal y medio de pago", ["Sucursal", "Medio de pago", "Ventas", "Cobrado"], [
            [x.sucursal, NOMBRES_MEDIO.get(x.medio_pago, x.medio_pago), miles(x.cantidad_ventas), dinero(x.total_cobrado)]
            for x in filas
        ])],
    )


REPORTES: dict[str, Callable[[], DocumentoReporte]] = {
    "r1": r1_existencias, "r2": r2_productos, "r3": r3_movimientos,
    "r4": r4_transito, "r5": r5_rechazos, "r6": r6_ventas,
}


def _armar(clave: str) -> DocumentoReporte:
    armar = REPORTES.get(clave)
    if armar is None:
        raise ValidacionError(f"No existe el reporte {clave}.")
    return armar()


@bp.get("/reportes/<clave>")
def ver_reporte(clave: str):
    d = _armar(clave)
    return jsonify(
        titulo=d.titulo, filtros=d.filtros, resumen=d.indicadores,
        grafico=None if d.grafico is None else {
            "titulo": d.grafico.titulo, "etiquetas": d.grafico.etiquetas,
            "valores": d.grafico.valores, "alertas": d.grafico.alertas,
        },
        secciones=[{"titulo": s.titulo, "columnas": s.columnas, "filas": s.filas} for s in d.secciones],
    )


@bp.get("/reportes/<clave>/exportar")
def exportar_reporte(clave: str):
    exportador = exportador_para(request.args.get("formato", "PDF"))
    documento = _armar(clave)
    sin_acentos = unicodedata.normalize("NFKD", documento.titulo.split("–")[-1]).encode("ascii", "ignore").decode()
    nombre = re.sub(r"[^A-Za-z0-9]+", "_", sin_acentos).strip("_").lower()
    with tempfile.TemporaryDirectory() as carpeta:
        ruta = exportador.exportar(documento, Path(carpeta) / f"reporte{exportador.extension}")
        contenido = ruta.read_bytes()
    return send_file(
        BytesIO(contenido),
        as_attachment=True,
        download_name=f"{clave}_{nombre}_{date.today():%Y%m%d}{exportador.extension}",
        mimetype="application/pdf" if exportador.extension == ".pdf" else "text/csv",
    )
