"""Tests de la exportación de reportes a PDF y CSV (patrón Strategy con ReportLab, Matplotlib y csv)."""

import csv
from datetime import datetime

import pytest

from src.excepciones import ValidacionError
from src.reportes.exportacion import (
    DocumentoReporte,
    ExportadorCSV,
    ExportadorPDF,
    ExportadorReporte,
    GraficoReporte,
    SeccionReporte,
    exportador_para,
)


@pytest.fixture
def documento():
    return DocumentoReporte(
        titulo="R4 – Tiempo de tránsito CD → locales",
        filtros="Desde: 2026-11-01 · Hasta: 2026-11-30",
        resumen="2 remitos verificados",
        secciones=[
            SeccionReporte("Por sucursal", ["Sucursal", "Promedio"], [["Centro", "10 h"], ["Norte", "1 d 2 h"]]),
            SeccionReporte("Sin datos", ["Columna"], []),
        ],
        grafico=GraficoReporte("Horas", ["Centro", "Norte"], [10.0, 26.0], [False, True]),
        generado=datetime(2026, 11, 2, 20, 0),
    )


@pytest.mark.parametrize("formato, clase", [("PDF", ExportadorPDF), ("csv", ExportadorCSV)])
def test_se_elige_el_exportador_por_formato(formato, clase):
    exportador = exportador_para(formato)

    assert isinstance(exportador, clase)
    assert isinstance(exportador, ExportadorReporte)


def test_formato_desconocido():
    with pytest.raises(ValidacionError):
        exportador_para("XLS")


def test_csv_con_titulo_filtros_y_cada_tabla(documento, tmp_path):
    ruta = exportador_para("CSV").exportar(documento, tmp_path / "r4.csv")

    with open(ruta, encoding="utf-8-sig", newline="") as archivo:
        filas = list(csv.reader(archivo, delimiter=";"))
    assert filas[0] == ["R4 – Tiempo de tránsito CD → locales"]
    assert ["Filtros: Desde: 2026-11-01 · Hasta: 2026-11-30"] in filas
    inicio = filas.index(["Por sucursal"])
    assert filas[inicio + 1:inicio + 4] == [["Sucursal", "Promedio"], ["Centro", "10 h"], ["Norte", "1 d 2 h"]]
    assert ["Sin datos"] in filas


def test_pdf_con_tablas_y_grafico(documento, tmp_path):
    pytest.importorskip("reportlab")
    pytest.importorskip("matplotlib")

    ruta = exportador_para("PDF").exportar(documento, tmp_path / "r4.pdf")

    contenido = ruta.read_bytes()
    assert contenido.startswith(b"%PDF")
    assert b"/Image" in contenido or b"/XObject" in contenido  # el gráfico va como imagen


def test_pdf_sin_grafico(documento, tmp_path):
    pytest.importorskip("reportlab")
    documento.grafico = None

    ruta = exportador_para("PDF").exportar(documento, tmp_path / "sin_grafico.pdf")

    assert ruta.stat().st_size > 0
