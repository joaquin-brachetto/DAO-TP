"""Pantallas de logística (turco).

Menú Logística:
    - Armado de bultos y remitos (P4)
    - Despacho desde el CD (P5)
    - Recepción en sucursal y control de precintos (P6, V1)
    - Trazabilidad inmutable de bultos (V2)
    - Cargar datos de prueba de logística
Menú Reportes:
    - R5 – Bultos rechazados y mermas por rotura de precinto logístico

Reutilizan los componentes de `src/ui/componentes.py` (`Grilla`, `Formulario`,
`ejecutar_con_manejo_de_errores`), `src/ui/graficos.py` (`GraficoBarras`, `Barra`)
y obtienen el `StockService` de la ventana principal (`padre.stock_service`) para
que todo movimiento de stock notifique a los observadores activos.
"""

from __future__ import annotations

import tkinter as tk
from datetime import date
from tkinter import ttk
from typing import Any

from src.datos_prueba_logistica import cargar_logistica_de_prueba
from src.dominio.inventario.modelos import (
    EstadoOrdenReposicion,
    OrdenReposicion,
    nombre_estado,
)
from src.dominio.logistica.modelos import (
    Bulto,
    CodigoEstadoBulto,
    EstadoRemito,
    Remito,
    nombre_estado_logistica,
)
from src.excepciones import ValidacionError
from src.reportes.logistica_reporte import (
    NOMBRE_ANOMALIA,
    ReporteBultosRechazados,
    ResumenReporteRechazos,
    TipoAnomaliaPrecinto,
)
from src.servicios.logistica_service import LogisticaService
from src.servicios.maestros_service import CategoriaService
from src.servicios.reposicion_service import ReposicionService
from src.servicios.stock_service import StockService
from src.ui.abm import a_entero, a_real, formato_dinero, formato_porcentaje
from src.ui.componentes import (
    Formulario,
    Grilla,
    confirmar,
    ejecutar_con_manejo_de_errores,
    mostrar_error,
    mostrar_info,
)
from src.ui.graficos import Barra, GraficoBarras
from src.ui.pantallas.inventario import TODAS, TODOS, _a_fecha, _Catalogo, _combo, _stock_service

NUEVO_REMITO = "— Crear nuevo remito automático —"
OPCION_INTEGRO_SI = "Sí (Precinto íntegro)"
OPCION_INTEGRO_NO = "No (Precinto roto / violado)"


def _logistica_service(padre: tk.Misc) -> LogisticaService:
    stock = _stock_service(padre)
    return LogisticaService(db=stock.db, stock_service=stock)


# === P4: Armado de bultos y remitos ============================================================


class PantallaArmadoBultos(tk.Toplevel):
    """P4: Empaquetar mercadería en bultos a partir de una OrdenReposicion, asignar remito y precinto."""

    def __init__(self, padre: tk.Misc) -> None:
        super().__init__(padre)
        self.title("Logística – Armado de bultos y remitos (P4)")
        self.geometry("1280x740")
        self.catalogo = _Catalogo()
        self.stock = _stock_service(padre)
        self.reposicion = ReposicionService(self.stock.db)
        self.servicio = _logistica_service(padre)
        self._ordenes: dict[str, OrdenReposicion] = {}
        self._remitos_orden: dict[str, Remito] = {}
        self._bultos_orden: dict[str, Bulto] = {}
        self._renglones_nuevo_bulto: dict[int, int] = {}
        self._opciones_productos_orden: dict[str, int] = {}

        izquierda = ttk.Frame(self, padding=(12, 12, 6, 12))
        izquierda.pack(side="left", fill="both", expand=True)
        derecha = ttk.LabelFrame(self, text="Armar nuevo bulto (P4)", padding=12)
        derecha.pack(side="right", fill="y", padx=(6, 12), pady=12)

        # --- Panel izquierdo: Órdenes, su detalle pendiente y bultos ya armados ---
        barra = ttk.Frame(izquierda)
        barra.pack(fill="x")
        self.filtro_estado_orden = tk.StringVar(value="Pendientes y en preparación")
        opciones_filtro = [
            "Pendientes y en preparación",
            nombre_estado(EstadoOrdenReposicion.PENDIENTE),
            nombre_estado(EstadoOrdenReposicion.EN_PREPARACION),
            TODOS,
        ]
        combo_est = _combo(barra, "Órdenes:", self.filtro_estado_orden, opciones_filtro, ancho=26)
        combo_est.bind("<<ComboboxSelected>>", lambda _e: self.refrescar())
        ttk.Button(barra, text="Actualizar", command=self.refrescar).pack(side="left")

        self.grilla_ordenes = Grilla(
            izquierda,
            [
                ("numero", "Orden N°", 65),
                ("fecha", "Emitida", 115),
                ("origen", "Origen (CD)", 180),
                ("destino", "Sucursal destino", 190),
                ("estado", "Estado", 125),
                ("avance", "Solicitado / Prep.", 120),
            ],
            alto=6,
        )
        self.grilla_ordenes.pack(fill="x", pady=(6, 0))
        self.grilla_ordenes.al_seleccionar(self._al_seleccionar_orden)

        ttk.Label(
            izquierda,
            text="Productos de la orden seleccionada (pendiente de empaquetar vs. stock disponible en CD):",
        ).pack(anchor="w", pady=(8, 2))
        self.grilla_detalle_orden = Grilla(
            izquierda,
            [
                ("producto", "Producto", 260),
                ("solicitada", "Solicitada", 80),
                ("preparada", "Ya empaquetada", 105),
                ("pendiente", "Falta armar", 90),
                ("stock_cd", "Disp. en CD", 90),
            ],
            alto=5,
        )
        self.grilla_detalle_orden.pack(fill="x")

        ttk.Label(
            izquierda,
            text="Bultos y remitos ya armados para esta orden:",
        ).pack(anchor="w", pady=(8, 2))
        self.grilla_bultos = Grilla(
            izquierda,
            [
                ("codigo", "Bulto", 90),
                ("remito", "Remito", 95),
                ("estado", "Estado bulto", 110),
                ("precinto", "Precinto N°", 120),
                ("peso", "Peso (kg)", 75),
                ("unidades", "Unidades", 70),
                ("contenido", "Contenido", 220),
            ],
            alto=6,
        )
        self.grilla_bultos.pack(fill="both", expand=True)

        marco_precintar = ttk.LabelFrame(
            izquierda, text="Precintar bulto en estado «Preparado» (Patrón State)", padding=8
        )
        marco_precintar.pack(fill="x", pady=(8, 0))
        self.precinto_diferido = tk.StringVar()
        ttk.Label(marco_precintar, text="N° de precinto único:").pack(side="left")
        ttk.Entry(marco_precintar, textvariable=self.precinto_diferido, width=18).pack(
            side="left", padx=(6, 10)
        )
        ttk.Button(
            marco_precintar,
            text="Colocar precinto al bulto elegido",
            command=self._precintar_existente,
        ).pack(side="left")
        ttk.Label(
            marco_precintar,
            text="Transiciona Preparado → Precintado y deja registro en el historial inmutable (V2).",
            foreground="gray30",
        ).pack(side="left", padx=10)

        # --- Panel derecho: Formulario de armado de bulto y asignación de remito/precinto ---
        self.lbl_orden_activa = ttk.Label(
            derecha, text="Elegí una orden a la izquierda", font=("TkDefaultFont", 10, "bold")
        )
        self.lbl_orden_activa.pack(anchor="w", pady=(0, 6))

        marco_rem = ttk.Frame(derecha)
        marco_rem.pack(fill="x", pady=(0, 6))
        ttk.Label(marco_rem, text="Remito:").pack(side="left")
        self.remito_destino = tk.StringVar(value=NUEVO_REMITO)
        self.combo_remito = ttk.Combobox(
            marco_rem,
            textvariable=self.remito_destino,
            values=[NUEVO_REMITO],
            state="readonly",
            width=32,
        )
        self.combo_remito.pack(side="left", padx=(6, 0), fill="x", expand=True)

        self.form_item = Formulario(
            derecha,
            [
                ("producto", "Producto de la orden", []),
                ("cantidad", "Cantidad a empaquetar"),
            ],
            ancho=32,
        )
        self.form_item.pack(fill="x")

        botones_item = ttk.Frame(derecha)
        botones_item.pack(fill="x", pady=(6, 4))
        ttk.Button(botones_item, text="Agregar al bulto", command=self._agregar_item).pack(side="left")
        ttk.Button(botones_item, text="Quitar ítem", command=self._quitar_item).pack(
            side="left", padx=4
        )
        ttk.Button(
            botones_item,
            text="Cargar todo lo pendiente",
            command=self._cargar_todo_pendiente,
        ).pack(side="left")

        self.grilla_items_bulto = Grilla(
            derecha,
            [("producto", "Producto en el bulto", 240), ("cantidad", "Cant.", 65)],
            alto=5,
        )
        self.grilla_items_bulto.pack(fill="both", expand=True, pady=(2, 6))

        self.form_bulto = Formulario(
            derecha,
            [
                ("codigo", "Código bulto (opc.)"),
                ("peso_kg", "Peso en kg (opc.)"),
                ("precinto", "N° Precinto (opc.)"),
                ("usuario", "Operador CD"),
            ],
            ancho=28,
        )
        self.form_bulto.cargar({"usuario": "turco"})
        self.form_bulto.pack(fill="x", pady=(4, 6))
        ttk.Label(
            derecha,
            text="Si informás el N° de precinto ahora, el bulto queda directamente «Precintado».\n"
            "Si lo dejás vacío, se crea en «Preparado» para cerrarlo y precintarlo después.",
            foreground="gray30",
            wraplength=340,
        ).pack(anchor="w", pady=(0, 6))
        ttk.Button(
            derecha,
            text="Confirmar armado de bulto (P4)",
            command=self._confirmar_armado_bulto,
        ).pack(fill="x")

        self.refrescar()

    def _orden_elegida(self) -> OrdenReposicion | None:
        clave = self.grilla_ordenes.seleccionado()
        return self._ordenes.get(clave or "")

    def refrescar(self, seleccionar_orden: int | None = None) -> None:
        todas = self.reposicion.listar()
        filtro = self.filtro_estado_orden.get()
        if filtro == "Pendientes y en preparación":
            ordenes = [
                o
                for o in todas
                if o.estado in (EstadoOrdenReposicion.PENDIENTE, EstadoOrdenReposicion.EN_PREPARACION)
            ]
        elif filtro == TODOS:
            ordenes = todas
        else:
            ordenes = [o for o in todas if nombre_estado(o.estado) == filtro]

        self._ordenes = {str(o.id): o for o in ordenes}
        self.grilla_ordenes.cargar(
            ordenes,
            lambda o: (
                o.numero,
                o.fecha_emision.strftime("%Y-%m-%d %H:%M"),
                self.catalogo.ubicacion(o.origen_id),
                self.catalogo.ubicacion(o.destino_id),
                nombre_estado(o.estado),
                f"{sum(d.cantidad_solicitada for d in o.detalles)} / "
                f"{sum(d.cantidad_preparada for d in o.detalles)} u.",
            ),
            clave=lambda o: o.id,
        )
        self.grilla_detalle_orden.cargar([], lambda _: ())
        self.grilla_bultos.cargar([], lambda _: ())
        if seleccionar_orden is not None and str(seleccionar_orden) in self._ordenes:
            self.grilla_ordenes.seleccionar(seleccionar_orden)
            self._al_seleccionar_orden(str(seleccionar_orden))
        elif ordenes:
            primera = ordenes[0].id
            self.grilla_ordenes.seleccionar(primera)
            self._al_seleccionar_orden(str(primera))
        else:
            self.lbl_orden_activa.configure(text="Sin órdenes para el filtro seleccionado")

    def _al_seleccionar_orden(self, clave: str) -> None:
        orden = self._ordenes.get(clave)
        if orden is None:
            return
        orden = self.reposicion.obtener(orden.id)
        self._ordenes[clave] = orden
        self.lbl_orden_activa.configure(
            text=f"Orden N° {orden.numero} → {self.catalogo.ubicacion(orden.destino_id)}"
        )

        filas_det = []
        opciones_prod: dict[str, int] = {}
        for d in orden.detalles:
            pendiente = max(d.cantidad_solicitada - d.cantidad_preparada, 0)
            disp_cd = self.stock.stock_disponible(orden.origen_id, d.producto_id)
            nombre_p = self.catalogo.producto(d.producto_id)
            filas_det.append((d.producto_id, nombre_p, d.cantidad_solicitada, d.cantidad_preparada, pendiente, disp_cd))
            if pendiente > 0:
                opciones_prod[f"{nombre_p} (falta: {pendiente})"] = d.producto_id

        self.grilla_detalle_orden.cargar(
            filas_det,
            lambda f: (f[1], f[2], f[3], f[4], f[5]),
            clave=lambda f: f[0],
        )
        self._opciones_productos_orden = opciones_prod
        self.form_item.actualizar_opciones("producto", list(opciones_prod))
        self.form_item.cargar({"producto": next(iter(opciones_prod), ""), "cantidad": ""})

        remitos = self.servicio.listar_remitos(orden_reposicion_id=orden.id)
        emitidos = [r for r in remitos if r.estado == EstadoRemito.EMITIDO]
        self._remitos_orden = {f"{r.numero} (Emitido)": r for r in emitidos}
        opciones_rem = [NUEVO_REMITO] + list(self._remitos_orden.keys())
        self.combo_remito.configure(values=opciones_rem)
        self.remito_destino.set(opciones_rem[-1] if emitidos else NUEVO_REMITO)

        bultos_vista: list[tuple[Bulto, str]] = []
        self._bultos_orden.clear()
        for r in remitos:
            for b in r.bultos:
                self._bultos_orden[str(b.id)] = b
                bultos_vista.append((b, r.numero))

        self.grilla_bultos.cargar(
            bultos_vista,
            lambda par: (
                par[0].codigo,
                par[1],
                nombre_estado_logistica(par[0].estado),
                par[0].precinto.numero if par[0].precinto else "— sin precintar —",
                f"{par[0].peso_kg:.1f}" if par[0].peso_kg else "—",
                par[0].total_unidades(),
                ", ".join(
                    f"{self.catalogo.producto(d.producto_id)} x{d.cantidad}"
                    for d in par[0].detalles
                ),
            ),
            clave=lambda par: par[0].id,
        )

    def _refrescar_items_nuevo_bulto(self) -> None:
        self.grilla_items_bulto.cargar(
            self._renglones_nuevo_bulto.items(),
            lambda par: (self.catalogo.producto(par[0]), par[1]),
            clave=lambda par: par[0],
        )

    def _agregar_item(self) -> None:
        def agregar() -> bool:
            v = self.form_item.valores()
            if v["producto"] not in self._opciones_productos_orden:
                raise ValidacionError("Elegí un producto pendiente de la orden.")
            cantidad = a_entero(v["cantidad"], "Cantidad")
            if cantidad <= 0:
                raise ValidacionError("La cantidad debe ser mayor a cero.")
            prod_id = self._opciones_productos_orden[v["producto"]]
            self._renglones_nuevo_bulto[prod_id] = self._renglones_nuevo_bulto.get(prod_id, 0) + cantidad
            return True

        if ejecutar_con_manejo_de_errores(agregar, self):
            self.form_item.cargar({"cantidad": ""})
            self._refrescar_items_nuevo_bulto()

    def _quitar_item(self) -> None:
        clave = self.grilla_items_bulto.seleccionado()
        if clave is None:
            mostrar_error("Elegí un producto de la lista del bulto.", padre=self)
            return
        self._renglones_nuevo_bulto.pop(int(clave), None)
        self._refrescar_items_nuevo_bulto()

    def _cargar_todo_pendiente(self) -> None:
        orden = self._orden_elegida()
        if orden is None:
            mostrar_error("Primero seleccioná una orden de reposición.", padre=self)
            return
        orden = self.reposicion.obtener(orden.id)
        pendientes = {
            d.producto_id: d.cantidad_solicitada - d.cantidad_preparada
            for d in orden.detalles
            if d.cantidad_solicitada - d.cantidad_preparada > 0
        }
        if not pendientes:
            mostrar_info("Esta orden ya tiene todas sus unidades empaquetadas en bultos.", padre=self)
            return
        self._renglones_nuevo_bulto = pendientes
        self._refrescar_items_nuevo_bulto()

    def _confirmar_armado_bulto(self) -> None:
        orden = self._orden_elegida()
        if orden is None:
            mostrar_error("Elegí una orden de reposición a la izquierda.", padre=self)
            return

        def armar() -> Bulto:
            if not self._renglones_nuevo_bulto:
                raise ValidacionError("Agregá al menos un producto al bulto antes de confirmar.")
            datos = self.form_bulto.valores()
            peso = a_real(datos["peso_kg"], "Peso en kg", opcional=True)
            usuario = datos["usuario"] or "turco"
            codigo = datos["codigo"] or None
            precinto = datos["precinto"] or None

            remito_elegido = self._remitos_orden.get(self.remito_destino.get())
            with self.stock.db.transaccion():
                if remito_elegido is None:
                    remito_elegido = self.servicio.crear_remito(orden.id)
                return self.servicio.armar_bulto(
                    remito_id=remito_elegido.id,
                    renglones=list(self._renglones_nuevo_bulto.items()),
                    codigo=codigo,
                    peso_kg=peso,
                    numero_precinto=precinto,
                    usuario=usuario,
                )

        bulto = ejecutar_con_manejo_de_errores(armar, self)
        if bulto is not None:
            self._renglones_nuevo_bulto.clear()
            self._refrescar_items_nuevo_bulto()
            self.form_bulto.cargar({"codigo": "", "peso_kg": "", "precinto": ""})
            self.refrescar(seleccionar_orden=orden.id)
            mostrar_info(
                f"Se armó el bulto «{bulto.codigo}» en estado «{nombre_estado_logistica(bulto.estado)}».",
                "Bulto armado (P4)",
                self,
            )

    def _precintar_existente(self) -> None:
        clave = self.grilla_bultos.seleccionado()
        bulto = self._bultos_orden.get(clave or "")
        if bulto is None:
            mostrar_error("Seleccioná un bulto de la tabla de bultos armados.", padre=self)
            return
        orden = self._orden_elegida()
        usuario = self.form_bulto.valores().get("usuario") or "turco"
        actualizado = ejecutar_con_manejo_de_errores(
            lambda: self.servicio.precintar_bulto(
                bulto.id, self.precinto_diferido.get(), usuario=usuario
            ),
            self,
        )
        if actualizado is not None:
            self.precinto_diferido.set("")
            if orden is not None:
                self.refrescar(seleccionar_orden=orden.id)
            mostrar_info(
                f"El bulto «{actualizado.codigo}» pasó a «{nombre_estado_logistica(actualizado.estado)}» "
                f"con precinto N° {actualizado.precinto.numero}.",
                "Precinto colocado",
                self,
            )


# === P5: Despacho desde el CD ==================================================================


class PantallaDespacho(tk.Toplevel):
    """P5: Registrar la salida de remitos con bultos precintados desde el CD hacia los locales."""

    def __init__(self, padre: tk.Misc) -> None:
        super().__init__(padre)
        self.title("Logística – Despacho desde Centro de Distribución (P5)")
        self.geometry("1220x700")
        self.catalogo = _Catalogo()
        self.servicio = _logistica_service(padre)
        self._remitos_emitidos: dict[str, Remito] = {}
        self._seleccionados_despacho: dict[int, Remito] = {}

        izquierda = ttk.Frame(self, padding=(12, 12, 6, 12))
        izquierda.pack(side="left", fill="both", expand=True)
        derecha = ttk.LabelFrame(self, text="Registrar nuevo despacho (P5)", padding=12)
        derecha.pack(side="right", fill="y", padx=(6, 12), pady=12)

        barra = ttk.Frame(izquierda)
        barra.pack(fill="x")
        ttk.Label(
            barra,
            text="Remitos en estado EMITIDO en el Centro de Distribución:",
            font=("TkDefaultFont", 10, "bold"),
        ).pack(side="left")
        ttk.Button(barra, text="Actualizar", command=self.refrescar).pack(side="right")

        self.grilla_remitos = Grilla(
            izquierda,
            [
                ("numero", "Remito", 95),
                ("orden", "Orden N°", 70),
                ("destino", "Sucursal destino", 210),
                ("bultos", "Bultos", 65),
                ("unidades", "Unidades", 75),
                ("listo", "Estado de bultos", 200),
            ],
            alto=7,
        )
        self.grilla_remitos.pack(fill="x", pady=(6, 0))
        self.grilla_remitos.al_seleccionar(self._mostrar_bultos_remito)

        botones_sel = ttk.Frame(izquierda)
        botones_sel.pack(fill="x", pady=(6, 6))
        ttk.Button(
            botones_sel,
            text="Agregar remito elegido al despacho →",
            command=self._agregar_remito_despacho,
        ).pack(side="left")
        ttk.Button(
            botones_sel,
            text="Agregar todos los remitos listos",
            command=self._agregar_todos_listos,
        ).pack(side="left", padx=6)

        ttk.Label(izquierda, text="Bultos contenidos en el remito seleccionado:").pack(
            anchor="w", pady=(4, 2)
        )
        self.grilla_bultos = Grilla(
            izquierda,
            [
                ("codigo", "Bulto", 95),
                ("estado", "Estado", 110),
                ("precinto", "Precinto N°", 125),
                ("peso", "Peso (kg)", 80),
                ("unidades", "Unidades", 75),
                ("productos", "Productos", 250),
            ],
            alto=5,
        )
        self.grilla_bultos.pack(fill="x")

        ttk.Label(izquierda, text="Últimos despachos registrados desde el CD:").pack(
            anchor="w", pady=(10, 2)
        )
        self.grilla_despachos = Grilla(
            izquierda,
            [
                ("id", "N°", 50),
                ("fecha", "Fecha y hora salida", 135),
                ("transportista", "Transportista", 190),
                ("patente", "Patente", 95),
                ("remitos", "Remitos despachados", 160),
                ("usuario", "Operador", 95),
            ],
            alto=5,
        )
        self.grilla_despachos.pack(fill="both", expand=True)

        # --- Panel derecho ---
        ttk.Label(derecha, text="Remitos incluidos en este viaje:").pack(anchor="w")
        self.grilla_a_despachar = Grilla(
            derecha,
            [("numero", "Remito", 95), ("destino", "Destino", 180), ("bultos", "Bultos", 55)],
            alto=5,
        )
        self.grilla_a_despachar.pack(fill="x", pady=(4, 4))
        ttk.Button(
            derecha,
            text="Quitar remito de la lista",
            command=self._quitar_remito_despacho,
        ).pack(anchor="w", pady=(0, 8))

        self.formulario = Formulario(
            derecha,
            [
                ("transportista", "Transportista"),
                ("patente", "Patente"),
                ("usuario", "Usuario CD"),
                ("observaciones", "Observaciones"),
            ],
            ancho=30,
        )
        self.formulario.cargar({"usuario": "turco"})
        self.formulario.pack(fill="x", pady=(4, 8))

        ttk.Label(
            derecha,
            text="Al confirmar el despacho:\n"
            "• Todos los bultos pasan de Precintado a En tránsito.\n"
            "• Se descuenta stock disponible del CD (EGRESO_DESPACHO).\n"
            "• Ingresa stock PENDIENTE en la sucursal (no vendible aún – V1).",
            foreground="gray30",
            wraplength=330,
        ).pack(anchor="w", pady=(0, 8))

        ttk.Button(
            derecha,
            text="Confirmar despacho desde CD (P5)",
            command=self._confirmar_despacho,
        ).pack(fill="x")

        self.refrescar()

    def refrescar(self) -> None:
        emitidos = self.servicio.listar_remitos(estado=EstadoRemito.EMITIDO)
        self._remitos_emitidos = {str(r.id): r for r in emitidos}
        ordenes = {o.id: o.numero for o in ReposicionService(self.servicio.db).listar()}

        def estado_bultos(r: Remito) -> str:
            if not r.bultos:
                return "⚠ Sin bultos"
            sin_precinto = sum(
                1 for b in r.bultos if b.nombre_estado != CodigoEstadoBulto.PRECINTADO.value
            )
            return "Listo (todos precintados)" if sin_precinto == 0 else f"⚠ {sin_precinto} sin precintar"

        self.grilla_remitos.cargar(
            emitidos,
            lambda r: (
                r.numero,
                ordenes.get(r.orden_reposicion_id, r.orden_reposicion_id),
                self.catalogo.ubicacion(r.destino_id),
                len(r.bultos),
                sum(b.total_unidades() for b in r.bultos),
                estado_bultos(r),
            ),
            clave=lambda r: r.id,
        )
        self.grilla_bultos.cargar([], lambda _: ())

        self._seleccionados_despacho = {
            rid: self._remitos_emitidos[str(rid)]
            for rid in self._seleccionados_despacho
            if str(rid) in self._remitos_emitidos
        }
        self._refrescar_seleccion_despacho()

        todos_remitos = {r.id: r.numero for r in self.servicio.listar_remitos()}
        despachos = self.servicio.listar_despachos()
        self.grilla_despachos.cargar(
            despachos,
            lambda d: (
                d.id,
                d.fecha_hora_salida.strftime("%Y-%m-%d %H:%M"),
                d.transportista,
                d.patente,
                ", ".join(todos_remitos.get(rid, str(rid)) for rid in d.remito_ids),
                d.usuario,
            ),
            clave=lambda d: d.id,
        )

    def _mostrar_bultos_remito(self, clave: str) -> None:
        remito = self._remitos_emitidos.get(clave)
        if remito is None:
            return
        self.grilla_bultos.cargar(
            remito.bultos,
            lambda b: (
                b.codigo,
                nombre_estado_logistica(b.estado),
                b.precinto.numero if b.precinto else "— SIN PRECINTO —",
                f"{b.peso_kg:.1f}" if b.peso_kg else "—",
                b.total_unidades(),
                ", ".join(
                    f"{self.catalogo.producto(d.producto_id)} x{d.cantidad}" for d in b.detalles
                ),
            ),
            clave=lambda b: b.id,
        )

    def _refrescar_seleccion_despacho(self) -> None:
        self.grilla_a_despachar.cargar(
            self._seleccionados_despacho.values(),
            lambda r: (r.numero, self.catalogo.ubicacion(r.destino_id), len(r.bultos)),
            clave=lambda r: r.id,
        )

    def _agregar_remito_despacho(self) -> None:
        clave = self.grilla_remitos.seleccionado()
        remito = self._remitos_emitidos.get(clave or "")
        if remito is None:
            mostrar_error("Seleccioná un remito emitido de la grilla superior.", padre=self)
            return
        self._seleccionados_despacho[remito.id] = remito
        self._refrescar_seleccion_despacho()

    def _agregar_todos_listos(self) -> None:
        agregados = 0
        for r in self._remitos_emitidos.values():
            if r.bultos and all(
                b.nombre_estado == CodigoEstadoBulto.PRECINTADO.value for b in r.bultos
            ):
                self._seleccionados_despacho[r.id] = r
                agregados += 1
        if agregados == 0:
            mostrar_info("No hay remitos con todos sus bultos precintados.", padre=self)
        self._refrescar_seleccion_despacho()

    def _quitar_remito_despacho(self) -> None:
        clave = self.grilla_a_despachar.seleccionado()
        if clave is None:
            mostrar_error("Elegí un remito de la lista a despachar.", padre=self)
            return
        self._seleccionados_despacho.pop(int(clave), None)
        self._refrescar_seleccion_despacho()

    def _confirmar_despacho(self) -> None:
        def despachar():
            datos = self.formulario.valores()
            return self.servicio.registrar_despacho(
                remito_ids=list(self._seleccionados_despacho.keys()),
                transportista=datos["transportista"],
                patente=datos["patente"],
                usuario=datos["usuario"] or "turco",
                observaciones=datos["observaciones"],
            )

        despacho = ejecutar_con_manejo_de_errores(despachar, self)
        if despacho is not None:
            self._seleccionados_despacho.clear()
            self.formulario.cargar({"transportista": "", "patente": "", "observaciones": ""})
            self.refrescar()
            mostrar_info(
                f"Despacho N° {despacho.id} registrado ({despacho.transportista} – {despacho.patente}).\n"
                "Los bultos pasaron a «En tránsito» y el stock ingresó como pendiente en destino.",
                "Despacho registrado (P5)",
                self,
            )


# === P6 y V1: Recepción en sucursal y verificación de precintos ================================


class PantallaRecepcion(tk.Toplevel):
    """P6 y V1: Recepción de remitos en sucursal, control de precinto por bulto e impacto en stock."""

    def __init__(self, padre: tk.Misc) -> None:
        super().__init__(padre)
        self.title("Logística – Recepción en sucursal y verificación de precintos (P6 · V1)")
        self.geometry("1260x740")
        self.catalogo = _Catalogo()
        self.servicio = _logistica_service(padre)
        self._remitos: dict[str, Remito] = {}
        self._bultos_remito: dict[str, Bulto] = {}

        marco = ttk.Frame(self, padding=12)
        marco.pack(fill="both", expand=True)

        barra = ttk.Frame(marco)
        barra.pack(fill="x")
        self._sucursales = {TODAS: None} | self.catalogo.opciones_ubicaciones(solo_sucursales=True)
        self.filtro_sucursal = tk.StringVar(value=TODAS)
        self.filtro_estado = tk.StringVar(value="En tránsito y recibidos")
        combo_suc = _combo(barra, "Sucursal destino:", self.filtro_sucursal, self._sucursales, ancho=28)
        combo_est = _combo(
            barra,
            "Estado remito:",
            self.filtro_estado,
            [
                "En tránsito y recibidos",
                nombre_estado_logistica(EstadoRemito.EN_TRANSITO),
                nombre_estado_logistica(EstadoRemito.RECIBIDO),
                TODOS,
            ],
            ancho=24,
        )
        combo_suc.bind("<<ComboboxSelected>>", lambda _e: self.refrescar())
        combo_est.bind("<<ComboboxSelected>>", lambda _e: self.refrescar())
        ttk.Button(barra, text="Actualizar", command=self.refrescar).pack(side="left")

        self.grilla_remitos = Grilla(
            marco,
            [
                ("numero", "Remito", 95),
                ("orden", "Orden N°", 75),
                ("destino", "Sucursal destino", 220),
                ("fecha", "Fecha emisión", 130),
                ("bultos", "Bultos", 65),
                ("unidades", "Unidades", 75),
                ("estado", "Estado del remito", 180),
            ],
            alto=6,
        )
        self.grilla_remitos.pack(fill="x", pady=(8, 6))
        self.grilla_remitos.al_seleccionar(self._al_seleccionar_remito)

        # --- Paso A: Registrar llegada del remito ---
        marco_llegada = ttk.LabelFrame(
            marco,
            text="Paso 1 – Llegada del remito al local (En tránsito → Recibido; el stock sigue pendiente)",
            padding=8,
        )
        marco_llegada.pack(fill="x", pady=(0, 8))
        self.recibido_por = tk.StringVar(value="encargado_local")
        self.obs_recepcion = tk.StringVar()
        ttk.Label(marco_llegada, text="Recibido por:").pack(side="left")
        ttk.Entry(marco_llegada, textvariable=self.recibido_por, width=20).pack(
            side="left", padx=(4, 12)
        )
        ttk.Label(marco_llegada, text="Observaciones:").pack(side="left")
        ttk.Entry(marco_llegada, textvariable=self.obs_recepcion, width=36).pack(
            side="left", padx=(4, 12)
        )
        ttk.Button(
            marco_llegada,
            text="1. Registrar llegada del remito",
            command=self._registrar_llegada,
        ).pack(side="left")
        self.lbl_estado_recepcion = ttk.Label(
            marco_llegada, text="", font=("TkDefaultFont", 9, "bold")
        )
        self.lbl_estado_recepcion.pack(side="right")

        # --- Paso B: Control individual de cada bulto y cierre ---
        cuerpo = ttk.Frame(marco)
        cuerpo.pack(fill="both", expand=True)

        izq = ttk.LabelFrame(
            cuerpo,
            text="Paso 2 – Bultos del remito y estado de verificación de sus precintos",
            padding=8,
        )
        izq.pack(side="left", fill="both", expand=True, padx=(0, 6))

        der = ttk.LabelFrame(
            cuerpo,
            text="Inspección del bulto seleccionado (P6 · V1)",
            padding=10,
        )
        der.pack(side="right", fill="y", padx=(6, 0))

        self.grilla_bultos = Grilla(
            izq,
            [
                ("codigo", "Bulto", 90),
                ("estado", "Estado actual", 110),
                ("esperado", "Precinto CD", 115),
                ("leido", "Precinto leído", 115),
                ("integro", "¿Íntegro?", 80),
                ("resultado", "Resultado", 110),
                ("motivo", "Observación / Motivo de rechazo", 260),
            ],
            alto=8,
        )
        self.grilla_bultos.pack(fill="both", expand=True)
        self.grilla_bultos.al_seleccionar(self._al_seleccionar_bulto)

        barra_cierre = ttk.Frame(izq)
        barra_cierre.pack(fill="x", pady=(8, 0))
        ttk.Button(
            barra_cierre,
            text="3. Cerrar recepción e impactar stock en sucursal (V1)",
            command=self._cerrar_recepcion,
        ).pack(side="left")
        ttk.Button(
            barra_cierre,
            text="Verificar todos como íntegros y cerrar recepción",
            command=self._verificar_todos_y_cerrar,
        ).pack(side="left", padx=8)

        self.lbl_bulto_elegido = ttk.Label(
            der, text="Elegí un bulto de la lista", font=("TkDefaultFont", 10, "bold")
        )
        self.lbl_bulto_elegido.pack(anchor="w", pady=(0, 6))
        self.lbl_precinto_cd = ttk.Label(der, text="Precinto colocado en CD: —", foreground="gray30")
        self.lbl_precinto_cd.pack(anchor="w", pady=(0, 6))

        self.form_control = Formulario(
            der,
            [
                ("precinto_leido", "N° precinto leído"),
                ("integro", "Estado físico", [OPCION_INTEGRO_SI, OPCION_INTEGRO_NO]),
                ("observacion", "Observación"),
            ],
            ancho=28,
        )
        self.form_control.cargar({"integro": OPCION_INTEGRO_SI})
        self.form_control.pack(fill="x")

        ttk.Button(
            der,
            text="Copiar N° de precinto esperado del CD",
            command=self._copiar_precinto_esperado,
        ).pack(fill="x", pady=(6, 4))

        ttk.Button(
            der,
            text="2. Registrar control de este bulto",
            command=self._registrar_control_bulto,
        ).pack(fill="x", pady=(4, 8))

        ttk.Label(
            der,
            text="Regla V1:\n"
            "• Precinto íntegro y número coincidente → VERIFICADO (pasa a Disponible al cerrar).\n"
            "• Precinto roto/violado o número distinto → RECHAZADO (pasa a Merma y NO habilita venta).",
            foreground="gray30",
            wraplength=310,
        ).pack(anchor="w")

        self.refrescar()

    def _remito_elegido(self) -> Remito | None:
        return self._remitos.get(self.grilla_remitos.seleccionado() or "")

    def _bulto_elegido(self) -> Bulto | None:
        return self._bultos_remito.get(self.grilla_bultos.seleccionado() or "")

    def refrescar(self, seleccionar_remito: int | None = None) -> None:
        suc_id = self._sucursales.get(self.filtro_sucursal.get())
        todos = self.servicio.listar_remitos(destino_id=suc_id)
        filtro = self.filtro_estado.get()
        if filtro == "En tránsito y recibidos":
            remitos = [
                r for r in todos if r.estado in (EstadoRemito.EN_TRANSITO, EstadoRemito.RECIBIDO)
            ]
        elif filtro == TODOS:
            remitos = todos
        else:
            remitos = [r for r in todos if nombre_estado_logistica(r.estado) == filtro]

        ordenes = {o.id: o.numero for o in ReposicionService(self.servicio.db).listar()}
        self._remitos = {str(r.id): r for r in remitos}
        self.grilla_remitos.cargar(
            remitos,
            lambda r: (
                r.numero,
                ordenes.get(r.orden_reposicion_id, r.orden_reposicion_id),
                self.catalogo.ubicacion(r.destino_id),
                r.fecha_emision.strftime("%Y-%m-%d %H:%M"),
                len(r.bultos),
                sum(b.total_unidades() for b in r.bultos),
                nombre_estado_logistica(r.estado),
            ),
            clave=lambda r: r.id,
        )
        self.grilla_bultos.cargar([], lambda _: ())
        if seleccionar_remito is not None and str(seleccionar_remito) in self._remitos:
            self.grilla_remitos.seleccionar(seleccionar_remito)
            self._al_seleccionar_remito(str(seleccionar_remito))
        elif remitos:
            primero = remitos[0].id
            self.grilla_remitos.seleccionar(primero)
            self._al_seleccionar_remito(str(primero))
        else:
            self.lbl_estado_recepcion.configure(text="")

    def _al_seleccionar_remito(self, clave: str) -> None:
        remito = self._remitos.get(clave)
        if remito is None:
            return
        remito = self.servicio.obtener_remito(remito.id)
        self._remitos[clave] = remito
        recepcion = self.servicio.obtener_recepcion_por_remito(remito.id)
        controles = {c.bulto_id: c for c in recepcion.controles} if recepcion else {}

        if recepcion is None:
            self.lbl_estado_recepcion.configure(
                text=f"Remito {remito.numero}: En tránsito (falta registrar llegada)"
            )
        elif not recepcion.cerrada:
            self.recibido_por.set(recepcion.recibido_por)
            self.obs_recepcion.set(recepcion.observaciones)
            self.lbl_estado_recepcion.configure(
                text=f"Recepción abierta (#{recepcion.id}) – Controlados {len(controles)}/{len(remito.bultos)} bultos"
            )
        else:
            self.recibido_por.set(recepcion.recibido_por)
            self.obs_recepcion.set(recepcion.observaciones)
            self.lbl_estado_recepcion.configure(
                text=f"Recepción cerrada (#{recepcion.id}) – {nombre_estado_logistica(remito.estado)}"
            )

        self._bultos_remito = {str(b.id): b for b in remito.bultos}
        self.grilla_bultos.cargar(
            remito.bultos,
            lambda b: (
                b.codigo,
                nombre_estado_logistica(b.estado),
                b.precinto.numero if b.precinto else "—",
                controles[b.id].numero_precinto_leido if b.id in controles else "— pendiente —",
                (
                    "Sí"
                    if (b.id in controles and controles[b.id].precinto_integro)
                    else ("No (roto)" if b.id in controles else "—")
                ),
                controles[b.id].resultado if b.id in controles else "Pendiente",
                b.motivo_rechazo or (controles[b.id].observacion if b.id in controles else ""),
            ),
            clave=lambda b: b.id,
        )
        if remito.bultos:
            primero_b = remito.bultos[0].id
            self.grilla_bultos.seleccionar(primero_b)
            self._al_seleccionar_bulto(str(primero_b))

    def _al_seleccionar_bulto(self, clave: str) -> None:
        bulto = self._bultos_remito.get(clave)
        if bulto is None:
            return
        esperado = bulto.precinto.numero if bulto.precinto else "—"
        self.lbl_bulto_elegido.configure(
            text=f"Bulto {bulto.codigo} ({nombre_estado_logistica(bulto.estado)})"
        )
        self.lbl_precinto_cd.configure(text=f"Precinto colocado en CD: {esperado}")
        control = self.servicio.control_de_bulto(bulto.id)
        if control is not None:
            self.form_control.cargar(
                {
                    "precinto_leido": control.numero_precinto_leido,
                    "integro": OPCION_INTEGRO_SI if control.precinto_integro else OPCION_INTEGRO_NO,
                    "observacion": control.observacion,
                }
            )
        else:
            self.form_control.cargar(
                {
                    "precinto_leido": esperado if esperado != "—" else "",
                    "integro": OPCION_INTEGRO_SI,
                    "observacion": "",
                }
            )

    def _copiar_precinto_esperado(self) -> None:
        bulto = self._bulto_elegido()
        if bulto is not None and bulto.precinto is not None:
            self.form_control.cargar({"precinto_leido": bulto.precinto.numero})

    def _registrar_llegada(self) -> None:
        remito = self._remito_elegido()
        if remito is None:
            mostrar_error("Elegí un remito de la tabla superior.", padre=self)
            return
        recepcion = ejecutar_con_manejo_de_errores(
            lambda: self.servicio.recibir_remito(
                remito_id=remito.id,
                recibido_por=self.recibido_por.get(),
                observaciones=self.obs_recepcion.get(),
            ),
            self,
        )
        if recepcion is not None:
            self.refrescar(seleccionar_remito=remito.id)
            mostrar_info(
                f"Se registró la llegada del remito «{remito.numero}».\n"
                "Sus bultos pasaron a estado «Recibido». Ahora controlá el precinto de cada bulto.",
                "Llegada registrada (Paso 1)",
                self,
            )

    def _registrar_control_bulto(self) -> None:
        remito = self._remito_elegido()
        bulto = self._bulto_elegido()
        if remito is None or bulto is None:
            mostrar_error("Seleccioná un remito y un bulto para controlar.", padre=self)
            return

        def controlar():
            recepcion = self.servicio.obtener_recepcion_por_remito(remito.id)
            if recepcion is None:
                recepcion = self.servicio.recibir_remito(
                    remito_id=remito.id,
                    recibido_por=self.recibido_por.get(),
                    observaciones=self.obs_recepcion.get(),
                )
            datos = self.form_control.valores()
            integro = datos["integro"] == OPCION_INTEGRO_SI
            return self.servicio.registrar_control_bulto(
                recepcion_id=recepcion.id,
                bulto_id=bulto.id,
                numero_precinto_leido=datos["precinto_leido"],
                precinto_integro=integro,
                observacion=datos["observacion"],
                usuario=self.recibido_por.get(),
            )

        control = ejecutar_con_manejo_de_errores(controlar, self)
        if control is not None:
            self.refrescar(seleccionar_remito=remito.id)
            mostrar_info(
                f"Bulto «{bulto.codigo}» controlado → Resultado: {control.resultado}.",
                "Control de precinto registrado",
                self,
            )

    def _cerrar_recepcion(self) -> None:
        remito = self._remito_elegido()
        if remito is None:
            mostrar_error("Elegí un remito para cerrar su recepción.", padre=self)
            return
        recepcion = self.servicio.obtener_recepcion_por_remito(remito.id)
        if recepcion is None:
            mostrar_error("Primero registrá la llegada y el control de los bultos del remito.", padre=self)
            return
        cerrada = ejecutar_con_manejo_de_errores(
            lambda: self.servicio.cerrar_recepcion(recepcion.id, usuario=self.recibido_por.get()),
            self,
        )
        if cerrada is not None:
            remito_act = self.servicio.obtener_remito(remito.id)
            self.filtro_estado.set(TODOS)
            self.refrescar(seleccionar_remito=remito.id)
            mostrar_info(
                f"Recepción cerrada: el remito «{remito_act.numero}» quedó "
                f"«{nombre_estado_logistica(remito_act.estado)}».\n"
                "Los bultos verificados ya están en stock DISPONIBLE para la venta y los "
                "rechazados se registraron como MERMA (V1).",
                "Recepción cerrada (V1)",
                self,
            )

    def _verificar_todos_y_cerrar(self) -> None:
        remito = self._remito_elegido()
        if remito is None:
            mostrar_error("Elegí un remito de la lista.", padre=self)
            return
        if not confirmar(
            f"¿Verificar todos los bultos del remito {remito.numero} con su precinto íntegro y cerrar la recepción?",
            padre=self,
        ):
            return

        def procesar():
            rem = self.servicio.obtener_remito(remito.id)
            controles = [
                (b.id, b.precinto.numero if b.precinto else "", True, "Verificado conforme")
                for b in rem.bultos
            ]
            return self.servicio.procesar_recepcion_completa(
                remito_id=rem.id,
                recibido_por=self.recibido_por.get() or "encargado_local",
                controles_por_bulto=controles,
                observaciones=self.obs_recepcion.get(),
            )

        if ejecutar_con_manejo_de_errores(procesar, self) is not None:
            self.filtro_estado.set(TODOS)
            self.refrescar(seleccionar_remito=remito.id)
            mostrar_info(
                f"Remito {remito.numero} verificado al 100%: su mercadería ya está disponible para vender.",
                "Recepción completada",
                self,
            )


# === V2: Trazabilidad inmutable de bultos ======================================================


class PantallaTrazabilidadBultos(tk.Toplevel):
    """V2: Consulta de bultos y visualización de su historial inmutable de cambios de estado."""

    def __init__(self, padre: tk.Misc) -> None:
        super().__init__(padre)
        self.title("Logística – Trazabilidad inmutable de bultos (V2 · Patrón State)")
        self.geometry("1220x700")
        self.catalogo = _Catalogo()
        self.servicio = _logistica_service(padre)
        self._bultos: dict[str, Bulto] = {}

        marco = ttk.Frame(self, padding=12)
        marco.pack(fill="both", expand=True)

        barra = ttk.Frame(marco)
        barra.pack(fill="x")
        self._sucursales = {TODAS: None} | self.catalogo.opciones_ubicaciones(solo_sucursales=True)
        self._estados = {TODOS: None} | {
            nombre_estado_logistica(e): e.value for e in CodigoEstadoBulto
        }
        self.sucursal = tk.StringVar(value=TODAS)
        self.estado = tk.StringVar(value=TODOS)
        self.busqueda = tk.StringVar()
        combo_s = _combo(barra, "Sucursal destino:", self.sucursal, self._sucursales, ancho=26)
        combo_e = _combo(barra, "Estado actual:", self.estado, self._estados, ancho=18)
        combo_s.bind("<<ComboboxSelected>>", lambda _e: self.refrescar())
        combo_e.bind("<<ComboboxSelected>>", lambda _e: self.refrescar())
        ttk.Label(barra, text="Buscar (bulto / precinto / remito):").pack(side="left")
        ttk.Entry(barra, textvariable=self.busqueda, width=20).pack(side="left", padx=(4, 8))
        ttk.Button(barra, text="Buscar", command=self.refrescar).pack(side="left")

        self.resumen = ttk.Label(marco, text="", font=("TkDefaultFont", 10, "bold"))
        self.resumen.pack(anchor="w", pady=(8, 4))

        self.grilla_bultos = Grilla(
            marco,
            [
                ("codigo", "Bulto", 95),
                ("remito", "Remito", 95),
                ("destino", "Sucursal destino", 210),
                ("estado", "Estado actual (State)", 130),
                ("precinto", "Precinto CD", 115),
                ("peso", "Peso (kg)", 75),
                ("unidades", "Unidades", 75),
                ("motivo", "Motivo de rechazo / Estado final", 280),
            ],
            alto=8,
        )
        self.grilla_bultos.pack(fill="x", pady=(0, 8))
        self.grilla_bultos.al_seleccionar(self._mostrar_detalle_bulto)

        inferior = ttk.Frame(marco)
        inferior.pack(fill="both", expand=True)

        panel_hist = ttk.LabelFrame(
            inferior,
            text="Historial inmutable de cambios de estado del bulto (V2 – protegido por triggers SQLite)",
            padding=8,
        )
        panel_hist.pack(side="left", fill="both", expand=True, padx=(0, 6))

        panel_cont = ttk.LabelFrame(
            inferior,
            text="Contenido del bulto y acta de control de precinto",
            padding=8,
        )
        panel_cont.pack(side="right", fill="both", padx=(6, 0))

        self.grilla_historial = Grilla(
            panel_hist,
            [
                ("paso", "#", 35),
                ("fecha", "Fecha y hora", 135),
                ("anterior", "Estado anterior", 115),
                ("nuevo", "Estado nuevo", 115),
                ("usuario", "Usuario", 110),
                ("observacion", "Observación", 280),
            ],
            alto=7,
        )
        self.grilla_historial.pack(fill="both", expand=True)
        ttk.Label(
            panel_hist,
            text="Transición válida: Preparado → Precintado → En tránsito → Recibido → Verificado / Rechazado. "
            "Nunca se hace UPDATE ni DELETE sobre esta tabla.",
            foreground="gray30",
        ).pack(anchor="w", pady=(4, 0))

        self.grilla_contenido = Grilla(
            panel_cont,
            [("producto", "Producto", 240), ("cantidad", "Unidades", 75)],
            alto=5,
        )
        self.grilla_contenido.pack(fill="x")
        self.lbl_info_control = ttk.Label(
            panel_cont, text="Seleccioná un bulto para ver su control de recepción.", wraplength=320
        )
        self.lbl_info_control.pack(anchor="w", pady=(8, 0))

        self.refrescar()

    def refrescar(self) -> None:
        bultos = self.servicio.listar_bultos(
            destino_id=self._sucursales.get(self.sucursal.get()),
            estado=self._estados.get(self.estado.get()),
            texto_busqueda=self.busqueda.get(),
        )
        remitos = {r.id: r for r in self.servicio.listar_remitos()}
        self._bultos = {str(b.id): b for b in bultos}

        self.grilla_bultos.cargar(
            bultos,
            lambda b: (
                b.codigo,
                remitos[b.remito_id].numero if b.remito_id in remitos else b.remito_id,
                (
                    self.catalogo.ubicacion(remitos[b.remito_id].destino_id)
                    if b.remito_id in remitos
                    else "—"
                ),
                nombre_estado_logistica(b.estado),
                b.precinto.numero if b.precinto else "— sin precinto —",
                f"{b.peso_kg:.1f}" if b.peso_kg else "—",
                b.total_unidades(),
                b.motivo_rechazo or ("Verificado OK" if b.nombre_estado == "VERIFICADO" else ""),
            ),
            clave=lambda b: b.id,
        )
        self.resumen.configure(
            text=f"{len(bultos)} bultos encontrados · "
            f"{sum(1 for b in bultos if b.nombre_estado == 'VERIFICADO')} verificados · "
            f"{sum(1 for b in bultos if b.nombre_estado == 'RECHAZADO')} rechazados · "
            f"{sum(1 for b in bultos if b.nombre_estado == 'EN_TRANSITO')} en tránsito"
        )
        self.grilla_historial.cargar([], lambda _: ())
        self.grilla_contenido.cargar([], lambda _: ())
        if bultos:
            primero = bultos[0].id
            self.grilla_bultos.seleccionar(primero)
            self._mostrar_detalle_bulto(str(primero))

    def _mostrar_detalle_bulto(self, clave: str) -> None:
        bulto = self._bultos.get(clave)
        if bulto is None:
            return
        historial = bulto.historial()
        self.grilla_historial.cargar(
            enumerate(historial, start=1),
            lambda par: (
                par[0],
                par[1].fecha_hora.strftime("%Y-%m-%d %H:%M:%S"),
                nombre_estado_logistica(par[1].estado_anterior) if par[1].estado_anterior else "— Inicio —",
                nombre_estado_logistica(par[1].estado_nuevo),
                par[1].usuario,
                par[1].observacion,
            ),
            clave=lambda par: par[0],
        )
        self.grilla_contenido.cargar(
            bulto.detalles,
            lambda d: (self.catalogo.producto(d.producto_id), d.cantidad),
            clave=lambda d: d.producto_id,
        )
        control = self.servicio.control_de_bulto(bulto.id)
        if control is None:
            self.lbl_info_control.configure(
                text=f"Bulto {bulto.codigo}: todavía no registra acta de control en sucursal."
            )
        else:
            self.lbl_info_control.configure(
                text=(
                    f"Control en sucursal ({control.fecha_hora_control.strftime('%Y-%m-%d %H:%M')}):\n"
                    f"• Precinto colocado CD: {bulto.precinto.numero if bulto.precinto else '—'}\n"
                    f"• Precinto leído en local: {control.numero_precinto_leido}\n"
                    f"• ¿Íntegro?: {'Sí' if control.precinto_integro else 'No (violado)'} · "
                    f"¿Coincide?: {'Sí' if control.coincide_precinto else 'No'}\n"
                    f"• Resultado final: {control.resultado}\n"
                    f"• Detalle: {control.observacion}"
                )
            )


# === R5: Reporte de bultos rechazados y mermas por rotura de precinto ==========================


class PantallaReporteRechazos(tk.Toplevel):
    """R5: Bultos rechazados y mermas valorizadas por rotura o adulteración de precinto logístico."""

    def __init__(self, padre: tk.Misc) -> None:
        super().__init__(padre)
        self.title("R5 – Bultos rechazados y mermas por rotura de precinto logístico")
        self.geometry("1240x740")
        self.catalogo = _Catalogo()
        stock = _stock_service(padre)
        self.reporte = ReporteBultosRechazados(stock.db)

        marco = ttk.Frame(self, padding=12)
        marco.pack(fill="both", expand=True)

        barra = ttk.Frame(marco)
        barra.pack(fill="x")
        hoy = date.today()
        self.desde = tk.StringVar(value=hoy.replace(day=1).isoformat())
        self.hasta = tk.StringVar(value=hoy.isoformat())
        ttk.Label(barra, text="Desde:").pack(side="left")
        ttk.Entry(barra, textvariable=self.desde, width=11).pack(side="left", padx=(4, 10))
        ttk.Label(barra, text="Hasta:").pack(side="left")
        ttk.Entry(barra, textvariable=self.hasta, width=11).pack(side="left", padx=(4, 10))

        self._sucursales = {TODAS: None} | self.catalogo.opciones_ubicaciones(solo_sucursales=True)
        self._categorias = {TODAS: None} | {
            c.nombre: c.id for c in CategoriaService(stock.db).listar()
        }
        self._anomalias = {
            TODOS: TipoAnomaliaPrecinto.TODOS.value,
            NOMBRE_ANOMALIA[TipoAnomaliaPrecinto.PRECINTO_ROTO.value]: TipoAnomaliaPrecinto.PRECINTO_ROTO.value,
            NOMBRE_ANOMALIA[TipoAnomaliaPrecinto.PRECINTO_NO_COINCIDE.value]: TipoAnomaliaPrecinto.PRECINTO_NO_COINCIDE.value,
            NOMBRE_ANOMALIA[TipoAnomaliaPrecinto.ROTO_Y_NO_COINCIDE.value]: TipoAnomaliaPrecinto.ROTO_Y_NO_COINCIDE.value,
        }
        self.sucursal = tk.StringVar(value=TODAS)
        self.categoria = tk.StringVar(value=TODAS)
        self.anomalia = tk.StringVar(value=TODOS)
        _combo(barra, "Sucursal:", self.sucursal, self._sucursales, ancho=22)
        _combo(barra, "Categoría:", self.categoria, self._categorias, ancho=14)
        _combo(barra, "Anomalía:", self.anomalia, self._anomalias, ancho=20)
        ttk.Button(barra, text="Consultar", command=self._consultar).pack(side="left")

        self.resumen = ttk.Label(marco, text="", font=("TkDefaultFont", 10, "bold"))
        self.resumen.pack(anchor="w", pady=(10, 4))

        pestañas = ttk.Notebook(marco)
        pestañas.pack(fill="both", expand=True)

        # Pestaña 1: Resumen por sucursal + Gráfico de barras
        tab_suc = ttk.Frame(pestañas, padding=8)
        pestañas.add(tab_suc, text="Resumen por sucursal y gráfico")
        self.grilla_sucursales = Grilla(
            tab_suc,
            [
                ("sucursal", "Sucursal destino", 250),
                ("recibidos", "Bultos recibidos", 120),
                ("verificados", "Bultos verificados", 125),
                ("rechazados", "Bultos rechazados", 125),
                ("tasa", "% Rechazo", 100),
                ("unidades", "Unidades en merma", 130),
                ("valor", "Merma valorizada (costo)", 165),
            ],
            alto=6,
        )
        self.grilla_sucursales.pack(fill="x")
        self.grafico = GraficoBarras(
            tab_suc,
            titulo="Merma valorizada al costo por sucursal ($)",
            leyenda="Rojo con ⚠: sucursal con bultos rechazados por rotura o adulteración de precinto",
            filas_maximas=6,
        )
        self.grafico.pack(fill="x", pady=(10, 0))

        # Pestaña 2: Detalle de bultos rechazados
        tab_bultos = ttk.Frame(pestañas, padding=8)
        pestañas.add(tab_bultos, text="Detalle de bultos rechazados")
        self.grilla_bultos = Grilla(
            tab_bultos,
            [
                ("fecha", "Fecha control", 120),
                ("bulto", "Bulto", 80),
                ("remito", "Remito", 85),
                ("sucursal", "Sucursal", 165),
                ("colocado", "Precinto CD", 105),
                ("leido", "Precinto leído", 105),
                ("anomalia", "Tipo de anomalía", 145),
                ("unidades", "Unid.", 55),
                ("valor", "Costo merma", 110),
                ("motivo", "Motivo detallado", 230),
            ],
            alto=15,
        )
        self.grilla_bultos.pack(fill="both", expand=True)

        # Pestaña 3: Mermas valorizadas por producto
        tab_prod = ttk.Frame(pestañas, padding=8)
        pestañas.add(tab_prod, text="Mermas valorizadas por producto")
        self.grilla_productos = Grilla(
            tab_prod,
            [
                ("sku", "SKU", 85),
                ("producto", "Producto", 230),
                ("categoria", "Categoría", 120),
                ("sucursal", "Sucursal", 185),
                ("bultos", "Bultos afectados", 115),
                ("unidades", "Unidades merma", 115),
                ("costo", "Costo unit.", 110),
                ("valor", "Merma total", 130),
            ],
            alto=15,
        )
        self.grilla_productos.pack(fill="both", expand=True)

        self._consultar()

    def _consultar(self) -> None:
        def consultar() -> ResumenReporteRechazos:
            return self.reporte.consultar(
                desde=_a_fecha(self.desde.get(), "Desde"),
                hasta=_a_fecha(self.hasta.get(), "Hasta"),
                sucursal_id=self._sucursales[self.sucursal.get()],
                categoria_id=self._categorias[self.categoria.get()],
                tipo_anomalia=self._anomalias[self.anomalia.get()],
            )

        resumen = ejecutar_con_manejo_de_errores(consultar, self)
        if resumen is not None:
            self._mostrar(resumen)

    def _mostrar(self, r: ResumenReporteRechazos) -> None:
        self.resumen.configure(
            text=(
                f"Bultos evaluados: {r.total_bultos_evaluados} · "
                f"Bultos rechazados: {r.total_bultos_rechazados} "
                f"({formato_porcentaje(r.tasa_rechazo_global)}) · "
                f"Unidades en merma: {r.total_unidades_merma} u. · "
                f"Pérdida total valorizada al costo: {formato_dinero(r.total_valor_merma)}"
            )
        )
        self.grilla_sucursales.cargar(
            r.por_sucursal,
            lambda s: (
                s.sucursal,
                s.total_bultos_recibidos,
                s.bultos_verificados,
                s.bultos_rechazados,
                formato_porcentaje(s.porcentaje_rechazo),
                s.unidades_merma,
                formato_dinero(s.valor_merma),
            ),
            clave=lambda s: s.sucursal_id,
        )
        self.grafico.dibujar(
            [
                Barra(
                    etiqueta=s.sucursal,
                    valor=float(s.valor_merma),
                    texto_valor=f"{formato_dinero(s.valor_merma)} ({s.bultos_rechazados} bultos)",
                    alerta=f"{formato_porcentaje(s.porcentaje_rechazo)} rechazo"
                    if s.bultos_rechazados > 0
                    else None,
                )
                for s in r.por_sucursal
            ]
        )
        self.grilla_bultos.cargar(
            r.bultos_rechazados,
            lambda b: (
                b.fecha_rechazo.strftime("%Y-%m-%d %H:%M"),
                b.codigo_bulto,
                b.numero_remito,
                b.sucursal,
                b.precinto_colocado,
                b.precinto_leido,
                b.tipo_anomalia,
                b.unidades_totales,
                formato_dinero(b.valor_merma),
                b.motivo_rechazo,
            ),
            clave=lambda b: b.bulto_id,
        )
        self.grilla_productos.cargar(
            enumerate(r.mermas_por_producto),
            lambda par: (
                par[1].sku,
                par[1].producto,
                par[1].categoria,
                par[1].sucursal,
                par[1].bultos_afectados,
                par[1].unidades_merma,
                formato_dinero(par[1].costo_unitario),
                formato_dinero(par[1].valor_merma),
            ),
            clave=lambda par: par[0],
        )


# === Funciones públicas invocadas desde src/ui/menu.py =========================================


def abrir_armado_bultos(padre: tk.Misc) -> None:
    PantallaArmadoBultos(padre)


def abrir_despacho(padre: tk.Misc) -> None:
    PantallaDespacho(padre)


def abrir_recepcion(padre: tk.Misc) -> None:
    PantallaRecepcion(padre)


def abrir_trazabilidad_bultos(padre: tk.Misc) -> None:
    PantallaTrazabilidadBultos(padre)


def abrir_reporte_rechazos(padre: tk.Misc) -> None:
    PantallaReporteRechazos(padre)


def abrir_cargar_logistica_de_prueba(padre: tk.Misc) -> None:
    if not confirmar(
        "¿Cargar los datos de prueba de logística?\n\n"
        "Se crearán órdenes de reposición, bultos precintados, remitos despachados, "
        "recepciones verificadas, bultos rechazados por precinto roto/adulterado (R5) "
        "y un remito en tránsito listo para recepcionar.",
        padre=padre,
    ):
        return
    stock = _stock_service(padre)
    cantidades = ejecutar_con_manejo_de_errores(
        lambda: cargar_logistica_de_prueba(db=stock.db, stock_service=stock), padre
    )
    if cantidades is not None:
        detalle = "\n".join(f"• {cantidad} {tipo}" for tipo, cantidad in cantidades.items())
        mostrar_info(
            f"Se cargaron los datos de prueba de logística:\n\n{detalle}",
            "Logística de prueba",
            padre,
        )
