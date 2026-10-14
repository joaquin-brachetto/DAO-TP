"""Pantallas P7: punto de venta, devoluciones, caja y reporte R6."""

import tkinter as tk
from datetime import date, datetime
from decimal import Decimal
from tkinter import messagebox, ttk

from src.dominio.ventas.modelos import Cliente, CondicionIva, DetalleDevolucion
from src.excepciones import ErrorDeNegocio
from src.persistencia.conexion import BaseDeDatos
from src.reportes.ventas_reporte import FilaReporteVentas, ReporteVentas
from src.servicios.ventas_service import PagoSolicitado, VentasService


class PantallaVentas(tk.Toplevel):
    """Ventana de uso diario para ventas, reintegros y caja de sucursal."""

    def __init__(self, padre: tk.Misc, pestaña_inicial: str = "Venta") -> None:
        super().__init__(padre)
        self.title("Ventas y caja")
        self.geometry("1040x700")
        self.minsize(820, 560)
        self.db = BaseDeDatos()
        self.service = getattr(padre, "ventas_service", None) or VentasService(
            self.db, getattr(padre, "stock_service", None)
        )
        self.reporte = ReporteVentas(self.db)
        self.items: dict[int, int] = {}
        self.pagos: list[PagoSolicitado] = []
        self.productos: dict[str, int] = {}
        self.sucursales: dict[str, int] = {}
        self._armar_interfaz(pestaña_inicial)

    def _armar_interfaz(self, pestaña_inicial: str) -> None:
        self.tabs = ttk.Notebook(self)
        self.tabs.pack(fill="both", expand=True, padx=10, pady=10)
        self.tab_venta = ttk.Frame(self.tabs, padding=12)
        self.tab_devolucion = ttk.Frame(self.tabs, padding=12)
        self.tab_caja = ttk.Frame(self.tabs, padding=12)
        self.tab_reporte = ttk.Frame(self.tabs, padding=12)
        for panel, titulo in (
            (self.tab_venta, "Venta"),
            (self.tab_devolucion, "Devolución"),
            (self.tab_caja, "Caja"),
            (self.tab_reporte, "Reporte R6"),
        ):
            self.tabs.add(panel, text=titulo)
        self._armar_tab_venta()
        self._armar_tab_devolucion()
        self._armar_tab_caja()
        self._armar_tab_reporte()
        for indice in range(self.tabs.index("end")):
            if self.tabs.tab(indice, "text") == pestaña_inicial:
                self.tabs.select(indice)
                break

    def _sucursales_activas(self) -> list[tuple[str, int]]:
        filas = self.db.consultar(
            "SELECT id, codigo, nombre FROM ubicacion WHERE tipo = 'SUCURSAL' AND activa = 1 ORDER BY nombre"
        )
        return [(f"{fila['codigo']} - {fila['nombre']}", int(fila["id"])) for fila in filas]

    def _cargar_combo_sucursales(self, combo: ttk.Combobox, incluir_todas: bool = False) -> dict[str, int]:
        opciones = self._sucursales_activas()
        mapa = {etiqueta: identificador for etiqueta, identificador in opciones}
        valores = list(mapa)
        if incluir_todas:
            valores.insert(0, "Todas las sucursales")
        combo.configure(values=valores)
        if valores:
            combo.current(0)
        return mapa

    def _armar_tab_venta(self) -> None:
        panel = self.tab_venta
        self.sucursal_venta = ttk.Combobox(panel, state="readonly", width=35)
        self.sucursales = self._cargar_combo_sucursales(self.sucursal_venta)
        self.vendedor = tk.StringVar()
        self.cliente_id = tk.StringVar()
        self.producto_combo = ttk.Combobox(panel, state="readonly", width=50)
        filas = self.db.consultar(
            "SELECT id, sku, nombre FROM producto WHERE activo = 1 ORDER BY nombre"
        )
        self.productos = {f"{fila['sku']} - {fila['nombre']} (#{fila['id']})": int(fila["id"]) for fila in filas}
        self.producto_combo.configure(values=list(self.productos))
        if self.productos:
            self.producto_combo.current(0)
        self.cantidad = tk.StringVar(value="1")
        self._fila_campo(panel, 0, "Sucursal", self.sucursal_venta)
        self._fila_campo(panel, 1, "Vendedor", ttk.Entry(panel, textvariable=self.vendedor))
        cliente_frame = ttk.Frame(panel)
        ttk.Entry(cliente_frame, textvariable=self.cliente_id, width=12).pack(side="left")
        ttk.Button(cliente_frame, text="Nuevo cliente", command=self._nuevo_cliente).pack(side="left", padx=6)
        self._fila_campo(panel, 2, "Cliente (id, opcional)", cliente_frame)

        ttk.Label(panel, text="Productos").grid(row=3, column=0, sticky="nw", pady=(12, 4))
        selector = ttk.Frame(panel)
        selector.grid(row=3, column=1, sticky="ew", pady=(12, 4))
        self.producto_combo.pack(in_=selector, side="left", fill="x", expand=True)
        ttk.Label(selector, text="Cantidad").pack(side="left", padx=(10, 4))
        ttk.Entry(selector, textvariable=self.cantidad, width=6).pack(side="left")
        ttk.Button(selector, text="Agregar", command=self._agregar_item).pack(side="left", padx=6)
        ttk.Button(selector, text="Quitar seleccionado", command=self._quitar_item).pack(side="left")
        self.tabla_items = self._tabla(panel, 4, [("producto", "Producto", 360), ("cantidad", "Cantidad", 90), ("subtotal", "Subtotal", 120)])
        ttk.Button(panel, text="Quitar renglón", command=self._quitar_item).grid(row=4, column=0, sticky="w")
        self.total_var = tk.StringVar(value="Total: $0.00")
        ttk.Label(panel, textvariable=self.total_var, font=("TkDefaultFont", 11, "bold")).grid(
            row=5, column=1, sticky="e", pady=5
        )

        ttk.Separator(panel).grid(row=6, column=0, columnspan=2, sticky="ew", pady=8)
        self.medio_pago = ttk.Combobox(
            panel, state="readonly", values=("EFECTIVO", "DEBITO", "CREDITO", "TRANSFERENCIA"), width=18
        )
        self.medio_pago.current(0)
        self.monto_pago = tk.StringVar()
        self.referencia_pago = tk.StringVar()
        self.cuotas_pago = tk.StringVar(value="1")
        pago_frame = ttk.Frame(panel)
        pago_frame.grid(row=7, column=1, sticky="ew")
        self.medio_pago.pack(in_=pago_frame, side="left")
        ttk.Entry(pago_frame, textvariable=self.monto_pago, width=12).pack(side="left", padx=6)
        ttk.Label(pago_frame, text="Cuotas").pack(side="left")
        ttk.Spinbox(pago_frame, from_=1, to=12, textvariable=self.cuotas_pago, width=4).pack(side="left", padx=4)
        ttk.Entry(pago_frame, textvariable=self.referencia_pago, width=18).pack(side="left", padx=4)
        ttk.Button(pago_frame, text="Agregar cobro", command=self._agregar_pago).pack(side="left", padx=4)
        ttk.Label(panel, text="Medio / importe base / referencia").grid(row=7, column=0, sticky="w")
        self.tabla_pagos = self._tabla(panel, 8, [("medio", "Medio", 160), ("monto", "Importe base", 130), ("referencia", "Referencia", 180)])
        ttk.Button(panel, text="Quitar cobro", command=self._quitar_pago).grid(row=8, column=0, sticky="w")
        ttk.Button(panel, text="Confirmar venta", command=self._confirmar_venta).grid(
            row=9, column=1, sticky="e", pady=(8, 0)
        )
        panel.columnconfigure(1, weight=1)

    def _agregar_item(self) -> None:
        try:
            producto_id = self.productos[self.producto_combo.get()]
            cantidad = int(self.cantidad.get())
            if cantidad <= 0:
                raise ValueError("La cantidad debe ser positiva.")
            total_cantidad = self.items.get(producto_id, 0) + cantidad
            ubicacion_id = self.sucursales[self.sucursal_venta.get()]
            self.service.validar_disponibilidad(ubicacion_id, producto_id, total_cantidad)
            self.items[producto_id] = total_cantidad
            self._refrescar_items()
        except (ErrorDeNegocio, KeyError, ValueError) as error:
            self._error(str(error) or "Seleccione un producto y una cantidad válida.")

    def _refrescar_items(self) -> None:
        self.tabla_items.delete(*self.tabla_items.get_children())
        total = Decimal("0.00")
        for producto_id, cantidad in self.items.items():
            producto = self.db.consultar_uno(
                "SELECT sku, nombre, precio_venta_actual FROM producto WHERE id = ?", (producto_id,)
            )
            subtotal = Decimal(producto["precio_venta_actual"]) * cantidad
            total += subtotal
            self.tabla_items.insert(
                "", "end", iid=str(producto_id),
                values=(f"{producto['sku']} - {producto['nombre']}", cantidad, f"${subtotal:.2f}"),
            )
        self.total_var.set(f"Total base: ${total:.2f}")

    def _quitar_item(self) -> None:
        seleccion = self.tabla_items.selection()
        if seleccion:
            self.items.pop(int(seleccion[0]), None)
            self._refrescar_items()

    def _nuevo_cliente(self) -> None:
        ventana = tk.Toplevel(self)
        ventana.title("Nuevo cliente")
        ventana.transient(self)
        ventana.grab_set()
        documento = tk.StringVar()
        nombre = tk.StringVar()
        condicion = ttk.Combobox(
            ventana, state="readonly", values=tuple(valor.value for valor in CondicionIva), width=28
        )
        condicion.set(CondicionIva.CONSUMIDOR_FINAL.value)
        self._fila_campo(ventana, 0, "Documento", ttk.Entry(ventana, textvariable=documento))
        self._fila_campo(ventana, 1, "Nombre", ttk.Entry(ventana, textvariable=nombre))
        self._fila_campo(ventana, 2, "Condición IVA", condicion)

        def registrar() -> None:
            try:
                cliente = self.service.registrar_cliente(
                    Cliente(documento.get(), nombre.get(), CondicionIva(condicion.get()))
                )
                self.cliente_id.set(str(cliente.id))
                ventana.destroy()
            except (ErrorDeNegocio, ValueError) as error:
                self._error(str(error))

        ttk.Button(ventana, text="Registrar cliente", command=registrar).grid(
            row=3, column=1, sticky="e", padx=8, pady=8
        )
        ventana.columnconfigure(1, weight=1)

    def _agregar_pago(self) -> None:
        try:
            medio = self.medio_pago.get()
            monto = Decimal(self.monto_pago.get()).quantize(Decimal("0.01"))
            datos: dict[str, str] = {}
            referencia = self.referencia_pago.get().strip()
            if medio in ("DEBITO", "CREDITO"):
                datos["autorizacion"] = referencia
            elif medio == "TRANSFERENCIA":
                datos["referencia"] = referencia
            cuotas = int(self.cuotas_pago.get()) if medio == "CREDITO" else 1
            pago = PagoSolicitado(medio, monto, datos, cuotas)
            self.pagos.append(pago)
            self.tabla_pagos.insert(
                "", "end", values=(medio, f"${monto:.2f}", referencia or "-")
            )
            self.monto_pago.set("")
            self.referencia_pago.set("")
        except (ValueError, ArithmeticError) as error:
            self._error(f"Importe de cobro inválido: {error}")

    def _quitar_pago(self) -> None:
        seleccion = self.tabla_pagos.selection()
        if seleccion:
            indice = self.tabla_pagos.index(seleccion[0])
            self.pagos.pop(indice)
            self.tabla_pagos.delete(seleccion[0])

    def _confirmar_venta(self) -> None:
        try:
            ubicacion_id = self.sucursales[self.sucursal_venta.get()]
            cliente_id = int(self.cliente_id.get()) if self.cliente_id.get() else None
            venta_id = self.service.registrar_venta(
                ubicacion_id, self.items, self.pagos, cliente_id, self.vendedor.get()
            )
            comprobante = self.db.consultar_uno(
                "SELECT tipo, punto_venta, numero, total FROM comprobante WHERE venta_id = ?", (venta_id,)
            )
            detalle_comprobante = (
                f"{comprobante['tipo']} {comprobante['punto_venta']:04d}-"
                f"{comprobante['numero']:08d}\nTotal: ${comprobante['total']:.2f}"
            )
            messagebox.showinfo(
                "Venta", f"Venta registrada: {venta_id}\n{detalle_comprobante}", parent=self
            )
            self.items.clear()
            self.pagos.clear()
            self.tabla_pagos.delete(*self.tabla_pagos.get_children())
            self._refrescar_items()
        except (ErrorDeNegocio, KeyError, ValueError) as error:
            self._error(str(error))

    def _armar_tab_devolucion(self) -> None:
        panel = self.tab_devolucion
        self.venta_devolucion = tk.StringVar()
        self.detalles_devolucion = tk.StringVar()
        self.motivo_devolucion = tk.StringVar()
        self.reingresa_stock = tk.BooleanVar(value=True)
        self._fila_campo(panel, 0, "Venta (id)", ttk.Entry(panel, textvariable=self.venta_devolucion))
        self._fila_campo(panel, 1, "Renglones id:cantidad", ttk.Entry(panel, textvariable=self.detalles_devolucion))
        self._fila_campo(panel, 2, "Motivo", ttk.Entry(panel, textvariable=self.motivo_devolucion))
        ttk.Checkbutton(panel, text="Reingresar productos al stock", variable=self.reingresa_stock).grid(
            row=3, column=1, sticky="w", pady=6
        )
        ttk.Button(panel, text="Registrar devolución", command=self._registrar_devolucion).grid(
            row=4, column=1, sticky="e", pady=8
        )

    def _registrar_devolucion(self) -> None:
        try:
            venta_id = int(self.venta_devolucion.get())
            renglones = []
            for parte in self.detalles_devolucion.get().split(","):
                detalle_id, cantidad = (int(valor.strip()) for valor in parte.split(":"))
                renglones.append(DetalleDevolucion(detalle_id, cantidad, self.reingresa_stock.get()))
            devolucion_id = self.service.registrar_devolucion(
                venta_id, renglones, self.motivo_devolucion.get()
            )
            messagebox.showinfo("Devolución", f"Devolución registrada: {devolucion_id}", parent=self)
            self.venta_devolucion.set("")
            self.detalles_devolucion.set("")
            self.motivo_devolucion.set("")
        except (ErrorDeNegocio, ValueError) as error:
            self._error(str(error))

    def _armar_tab_caja(self) -> None:
        panel = self.tab_caja
        self.sucursal_caja = ttk.Combobox(panel, state="readonly", width=40)
        self.sucursales_caja = self._cargar_combo_sucursales(self.sucursal_caja)
        self.saldo_inicial = tk.StringVar(value="0.00")
        self.estado_caja = tk.StringVar(value="Sin consulta")
        self._fila_campo(panel, 0, "Sucursal", self.sucursal_caja)
        self._fila_campo(panel, 1, "Saldo inicial", ttk.Entry(panel, textvariable=self.saldo_inicial))
        acciones = ttk.Frame(panel)
        acciones.grid(row=2, column=1, sticky="w", pady=8)
        ttk.Button(acciones, text="Abrir caja", command=self._abrir_caja).pack(side="left")
        ttk.Button(acciones, text="Cerrar caja", command=self._cerrar_caja).pack(side="left", padx=6)
        ttk.Button(acciones, text="Actualizar saldo", command=self._actualizar_saldo).pack(side="left")
        ttk.Label(panel, textvariable=self.estado_caja, font=("TkDefaultFont", 12, "bold")).grid(
            row=3, column=1, sticky="w", pady=10
        )
        panel.columnconfigure(1, weight=1)

    def _abrir_caja(self) -> None:
        try:
            ubicacion_id = self.sucursales_caja[self.sucursal_caja.get()]
            caja = self.service.abrir_caja(ubicacion_id, Decimal(self.saldo_inicial.get()))
            self.estado_caja.set(f"Caja #{caja.id} abierta · saldo ${caja.saldo_inicial:.2f}")
        except (ErrorDeNegocio, KeyError, ValueError) as error:
            self._error(str(error))

    def _cerrar_caja(self) -> None:
        try:
            ubicacion_id = self.sucursales_caja[self.sucursal_caja.get()]
            saldo = self.service.cerrar_caja(ubicacion_id)
            self.estado_caja.set(f"Caja cerrada · saldo final ${saldo:.2f}")
        except (ErrorDeNegocio, KeyError) as error:
            self._error(str(error))

    def _actualizar_saldo(self) -> None:
        try:
            ubicacion_id = self.sucursales_caja[self.sucursal_caja.get()]
            saldo = self.service.saldo_caja_abierta(ubicacion_id)
            self.estado_caja.set("Caja cerrada" if saldo is None else f"Saldo actual ${saldo:.2f}")
        except (ErrorDeNegocio, KeyError) as error:
            self._error(str(error))

    def _armar_tab_reporte(self) -> None:
        panel = self.tab_reporte
        hoy = date.today()
        self.desde = tk.StringVar(value=hoy.replace(day=1).isoformat())
        self.hasta = tk.StringVar(value=hoy.isoformat())
        filtros = ttk.Frame(panel)
        filtros.pack(fill="x")
        ttk.Label(filtros, text="Desde").pack(side="left")
        ttk.Entry(filtros, textvariable=self.desde, width=12).pack(side="left", padx=4)
        ttk.Label(filtros, text="Hasta").pack(side="left", padx=(8, 0))
        ttk.Entry(filtros, textvariable=self.hasta, width=12).pack(side="left", padx=4)
        self.sucursal_reporte = ttk.Combobox(filtros, state="readonly", width=32)
        self.sucursales_reporte = self._cargar_combo_sucursales(self.sucursal_reporte, incluir_todas=True)
        self.sucursal_reporte.pack(side="left", padx=8)
        ttk.Button(filtros, text="Consultar", command=self._consultar_reporte).pack(side="left")
        contenido = ttk.Panedwindow(panel, orient="vertical")
        contenido.pack(fill="both", expand=True, pady=(10, 0))
        tabla_frame = ttk.Frame(contenido)
        self.tabla_reporte = ttk.Treeview(
            tabla_frame,
            columns=("sucursal", "medio", "ventas", "total"),
            show="headings",
            height=8,
        )
        for columna, titulo, ancho in (
            ("sucursal", "Sucursal", 280), ("medio", "Medio de pago", 170),
            ("ventas", "Ventas", 90), ("total", "Total cobrado", 140),
        ):
            self.tabla_reporte.heading(columna, text=titulo)
            self.tabla_reporte.column(columna, width=ancho, anchor="w")
        self.tabla_reporte.pack(fill="both", expand=True)
        self.grafico = tk.Canvas(contenido, height=220, background="#f4f5f2", highlightthickness=0)
        contenido.add(tabla_frame, weight=3)
        contenido.add(self.grafico, weight=2)

    def _consultar_reporte(self) -> None:
        try:
            desde = date.fromisoformat(self.desde.get())
            hasta = date.fromisoformat(self.hasta.get())
            sucursal = self.sucursal_reporte.get()
            ubicacion_id = self.sucursales_reporte.get(sucursal)
            filas = self.reporte.consultar(desde, hasta, ubicacion_id)
            self._dibujar_reporte(filas)
        except (ValueError, ErrorDeNegocio) as error:
            self._error(str(error))

    def _dibujar_reporte(self, filas: list[FilaReporteVentas]) -> None:
        self.tabla_reporte.delete(*self.tabla_reporte.get_children())
        for indice, fila in enumerate(filas):
            self.tabla_reporte.insert(
                "", "end", iid=str(indice),
                values=(fila.sucursal, fila.medio_pago, fila.cantidad_ventas, f"${fila.total_cobrado:.2f}"),
            )
        self.grafico.delete("all")
        if not filas:
            self.grafico.create_text(20, 24, anchor="w", text="Sin ventas para el período seleccionado")
            return
        maximo = max(fila.total_cobrado for fila in filas) or Decimal("1")
        ancho = max(self.grafico.winfo_width() - 210, 100)
        colores = ("#176b55", "#d88736", "#347b9a", "#8d4d46")
        for indice, fila in enumerate(filas[:8]):
            y = 22 + indice * 24
            largo = int(ancho * float(fila.total_cobrado / maximo))
            self.grafico.create_text(8, y + 7, anchor="w", text=f"{fila.sucursal[:16]} · {fila.medio_pago}")
            self.grafico.create_rectangle(205, y, 205 + largo, y + 14, fill=colores[indice % len(colores)], width=0)
            self.grafico.create_text(212 + largo, y + 7, anchor="w", text=f"${fila.total_cobrado:.2f}")

    @staticmethod
    def _fila_campo(panel: ttk.Frame, fila: int, etiqueta: str, widget: tk.Widget) -> None:
        ttk.Label(panel, text=etiqueta).grid(row=fila, column=0, sticky="w", padx=(0, 10), pady=4)
        widget.grid(row=fila, column=1, sticky="ew", pady=4)

    @staticmethod
    def _tabla(panel: ttk.Frame, fila: int, columnas: list[tuple[str, str, int]]) -> ttk.Treeview:
        tabla = ttk.Treeview(panel, columns=[c[0] for c in columnas], show="headings", height=5)
        for clave, titulo, ancho in columnas:
            tabla.heading(clave, text=titulo)
            tabla.column(clave, width=ancho, anchor="w")
        tabla.grid(row=fila, column=1, sticky="nsew", pady=4)
        panel.rowconfigure(fila, weight=1)
        return tabla

    def _error(self, mensaje: str) -> None:
        messagebox.showerror("Ventas", mensaje, parent=self)


def abrir_ventas(padre: tk.Misc) -> None:
    """Abre el flujo P7 completo; acepta servicios inyectados desde la aplicación."""
    PantallaVentas(padre)


def abrir_reporte_ventas(padre: tk.Misc) -> None:
    """Abre Ventas directamente en el reporte R6."""
    PantallaVentas(padre, "Reporte R6")


def abrir_devoluciones(padre: tk.Misc) -> None:
    """Abre Ventas directamente en la pestaña de devoluciones (V5)."""
    PantallaVentas(padre, "Devolución")


def abrir_caja(padre: tk.Misc) -> None:
    """Abre Ventas directamente en la administración de caja (P7)."""
    PantallaVentas(padre, "Caja")