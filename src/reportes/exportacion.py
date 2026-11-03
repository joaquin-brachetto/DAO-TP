"""Exportación de reportes a PDF (ReportLab + Matplotlib) y a CSV (biblioteca csv).

Cualquier reporte se exporta igual: la pantalla arma un `DocumentoReporte` con lo que
está mostrando (título, filtros, resumen, tablas y gráfico) y se lo pasa a un
exportador. Los exportadores aplican el patrón **Strategy**: todos responden a
`exportar(documento, ruta)` y cada uno genera su formato a su manera.

    exportador = exportador_para("PDF")      # o "CSV"
    exportador.exportar(documento, "r3_movimientos.pdf")
"""

import csv
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from io import BytesIO
from pathlib import Path

from src.excepciones import ValidacionError


@dataclass
class SeccionReporte:
    """Una tabla del reporte: sus columnas y sus filas, ya formateadas como texto."""

    titulo: str
    columnas: list[str]
    filas: list[list[str]]


@dataclass
class GraficoReporte:
    """Datos de un gráfico de barras horizontales. Las barras en alerta van en rojo."""

    titulo: str
    etiquetas: list[str]
    valores: list[float]
    alertas: list[bool] = field(default_factory=list)


@dataclass
class DocumentoReporte:
    titulo: str
    secciones: list[SeccionReporte]
    filtros: str = ""
    resumen: str = ""
    grafico: GraficoReporte | None = None
    generado: datetime = field(default_factory=datetime.now)

    def __str__(self) -> str:
        return f"{self.titulo} ({len(self.secciones)} tablas)"


class ExportadorReporte(ABC):
    """Strategy: cada formato de salida implementa `exportar` a su manera."""

    formato: str
    extension: str

    @abstractmethod
    def exportar(self, documento: DocumentoReporte, ruta: str | Path) -> Path:
        """Genera el archivo y devuelve su ruta."""


class ExportadorCSV(ExportadorReporte):
    """CSV con `;` como separador y codificación utf-8-sig, para que Excel en español lo abra bien."""

    formato = "CSV"
    extension = ".csv"

    def exportar(self, documento: DocumentoReporte, ruta: str | Path) -> Path:
        ruta = Path(ruta)
        with open(ruta, "w", newline="", encoding="utf-8-sig") as archivo:
            escritor = csv.writer(archivo, delimiter=";")
            escritor.writerow([documento.titulo])
            escritor.writerow([f"Generado: {documento.generado:%d/%m/%Y %H:%M}"])
            if documento.filtros:
                escritor.writerow([f"Filtros: {documento.filtros}"])
            if documento.resumen:
                escritor.writerow([documento.resumen])
            for seccion in documento.secciones:
                escritor.writerow([])
                escritor.writerow([seccion.titulo])
                escritor.writerow(seccion.columnas)
                escritor.writerows(seccion.filas)
        return ruta


# Helvetica (la letra de ReportLab) no tiene estos símbolos que usan las pantallas.
_REEMPLAZOS_PDF = {"⚠": "(!)", "→": "->", "≤": "<=", "≥": ">="}


def _texto_pdf(texto: object) -> str:
    texto = str(texto)
    for simbolo, reemplazo in _REEMPLAZOS_PDF.items():
        texto = texto.replace(simbolo, reemplazo)
    return texto.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


class ExportadorPDF(ExportadorReporte):
    """PDF horizontal armado con ReportLab; el gráfico se dibuja con Matplotlib y se inserta como imagen."""

    formato = "PDF"
    extension = ".pdf"

    def exportar(self, documento: DocumentoReporte, ruta: str | Path) -> Path:
        try:
            from reportlab.lib import colors
            from reportlab.lib.pagesizes import A4, landscape
            from reportlab.lib.styles import getSampleStyleSheet
            from reportlab.lib.units import cm
            from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
        except ImportError as error:
            raise ValidacionError(
                "Para exportar a PDF hay que instalar ReportLab y Matplotlib: "
                "python -m pip install -r requirements.txt"
            ) from error

        ruta = Path(ruta)
        estilos = getSampleStyleSheet()
        celda = estilos["BodyText"].clone("celda", fontSize=7.5, leading=9)
        encabezado = celda.clone("encabezado", fontName="Helvetica-Bold", textColor=colors.white)
        titulo_tabla = estilos["Heading3"].clone("titulo_tabla", keepWithNext=1)  # no queda solo al pie
        doc = SimpleDocTemplate(
            str(ruta), pagesize=landscape(A4), title=documento.titulo,
            leftMargin=1.5 * cm, rightMargin=1.5 * cm, topMargin=1.5 * cm, bottomMargin=1.5 * cm,
        )
        elementos = [
            Paragraph(_texto_pdf(documento.titulo), estilos["Title"]),
            Paragraph(f"Generado: {documento.generado:%d/%m/%Y %H:%M}", estilos["Normal"]),
        ]
        if documento.filtros:
            elementos.append(Paragraph(f"Filtros: {_texto_pdf(documento.filtros)}", estilos["Normal"]))
        if documento.resumen:
            elementos.append(Spacer(1, 6))
            elementos.append(Paragraph(f"<b>{_texto_pdf(documento.resumen)}</b>", estilos["Normal"]))

        if documento.grafico is not None and documento.grafico.valores:
            elementos.append(Spacer(1, 10))
            elementos.append(self._imagen_grafico(documento.grafico, Image, ancho=doc.width))

        for seccion in documento.secciones:
            elementos.append(Spacer(1, 12))
            elementos.append(Paragraph(_texto_pdf(seccion.titulo), titulo_tabla))
            if not seccion.filas:
                elementos.append(Paragraph("Sin datos para los filtros elegidos.", estilos["Normal"]))
                continue
            datos = [[Paragraph(_texto_pdf(c), encabezado) for c in seccion.columnas]]
            datos += [[Paragraph(_texto_pdf(v), celda) for v in fila] for fila in seccion.filas]
            tabla = Table(datos, colWidths=self._anchos(seccion, doc.width), repeatRows=1)
            tabla.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2a5d8f")),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#eef2f6")]),
                ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#b8c2cc")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]))
            elementos.append(tabla)
        doc.build(elementos)
        return ruta

    @staticmethod
    def _anchos(seccion: SeccionReporte, ancho_total: float) -> list[float]:
        """Cada columna recibe al menos el ancho de su palabra más larga (para no cortar códigos);
        el resto del ancho se reparte según el texto más largo de cada columna."""
        puntos_por_letra = 4.4  # aproximado para la letra de 7,5 puntos de las celdas
        minimos, largos = [], []
        for indice, columna in enumerate(seccion.columnas):
            textos = [columna] + [str(fila[indice]) for fila in seccion.filas if indice < len(fila)]
            palabra_mas_larga = max(len(palabra) for texto in textos for palabra in texto.split() or [""])
            minimos.append(min(palabra_mas_larga, 18) * puntos_por_letra + 8)
            largos.append(min(max(len(texto) for texto in textos), 45))
        sobrante = max(ancho_total - sum(minimos), 0)
        total = sum(largos) or 1
        anchos = [minimo + sobrante * largo / total for minimo, largo in zip(minimos, largos)]
        escala = ancho_total / sum(anchos)  # si los mínimos no entran, se achican todos por igual
        return [ancho * escala for ancho in anchos]

    @staticmethod
    def _imagen_grafico(grafico: GraficoReporte, Image, ancho: float):
        """Dibuja el gráfico con Matplotlib en memoria (BytesIO) y lo devuelve como imagen de ReportLab."""
        import matplotlib

        matplotlib.use("Agg")  # sin ventana: solo genera la imagen
        import matplotlib.pyplot as plt

        cantidad = len(grafico.valores)
        alertas = grafico.alertas or [False] * cantidad
        alto = 1.2 + 0.35 * cantidad
        figura, ejes = plt.subplots(figsize=(10, alto))
        posiciones = list(range(cantidad))
        ejes.barh(posiciones, grafico.valores,
                  color=["#d03b3b" if alerta else "#2a78d6" for alerta in alertas])
        ejes.set_yticks(posiciones, [e if len(e) <= 40 else e[:39] + "…" for e in grafico.etiquetas])
        ejes.invert_yaxis()  # el primero arriba, como en la pantalla
        ejes.set_title(grafico.titulo, fontsize=11)
        ejes.spines[["top", "right"]].set_visible(False)
        figura.tight_layout()
        memoria = BytesIO()
        figura.savefig(memoria, format="png", dpi=150)
        plt.close(figura)
        memoria.seek(0)
        return Image(memoria, width=ancho, height=ancho * alto / 10)


EXPORTADORES: dict[str, ExportadorReporte] = {
    exportador.formato: exportador for exportador in (ExportadorPDF(), ExportadorCSV())
}


def exportador_para(formato: str) -> ExportadorReporte:
    try:
        return EXPORTADORES[formato.upper()]
    except KeyError as error:
        raise ValidacionError(f"No se puede exportar a {formato}.") from error
