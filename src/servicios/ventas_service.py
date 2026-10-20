"""Casos de uso de P7; delega cada cambio de inventario a StockService."""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Protocol

from src.dominio.ventas.modelos import (
    Caja,
    Cliente,
    Cobro,
    ComprobanteFactory,
    CondicionIva,
    Devolucion,
    DetalleDevolucion,
    DetalleVenta,
    EstadoVenta,
    crear_medio_pago,
    dinero,
)
from src.excepciones import EntidadNoEncontradaError, ValidacionError
from src.persistencia.conexion import BaseDeDatos
from src.persistencia.repositorio_ventas import ClienteRepositorio, VentasRepositorio


class StockService(Protocol):
    """Contrato publicado por pohlsi; Ventas no implementa ni persiste inventario."""

    def stock_disponible(self, ubicacion_id: int, producto_id: int) -> int: ...

    def egresar(self, ubicacion_id: int, producto_id: int, cantidad: int, ref: str) -> None: ...

    def reingresar(self, ubicacion_id: int, producto_id: int, cantidad: int, ref: str) -> None: ...


@dataclass
class PagoSolicitado:
    """Parte base de un pago mixto; nunca contiene número ni clave de tarjeta."""

    medio_pago: str
    monto: Decimal
    datos: dict[str, str] = field(default_factory=dict)
    cuotas: int = 1


class VentasService:
    """Confirma ventas, administra caja y valida devoluciones antes de persistir."""

    def __init__(
        self,
        db: BaseDeDatos | None = None,
        stock_service: StockService | None = None,
        plazo_devolucion_dias: int = 30,
    ) -> None:
        if plazo_devolucion_dias < 0:
            raise ValueError("El plazo de devolución no puede ser negativo.")
        self.db = db or BaseDeDatos()
        self.repo = VentasRepositorio(self.db)
        self.clientes = ClienteRepositorio(self.db)
        self.stock = stock_service
        self.plazo_devolucion_dias = plazo_devolucion_dias

    def registrar_cliente(self, cliente: Cliente) -> Cliente:
        """Registra un comprador con documento único para emitir comprobantes."""
        cliente.documento = cliente.documento.strip()
        cliente.nombre = cliente.nombre.strip()
        if not cliente.documento or not cliente.nombre:
            raise ValidacionError("El documento y el nombre del cliente son obligatorios.")
        try:
            return self.clientes.guardar(cliente)
        except ValueError as error:
            raise ValidacionError(str(error)) from error

    def abrir_caja(self, ubicacion_id: int, saldo_inicial: Decimal | str | int = 0) -> Caja:
        """Abre una caja por sucursal; no permite dos cajas abiertas en paralelo."""
        sucursal = self._validar_sucursal(ubicacion_id)
        saldo = dinero(saldo_inicial)
        if saldo < 0:
            raise ValidacionError("El saldo inicial no puede ser negativo.")
        fecha = datetime.now()
        try:
            with self.db.transaccion():
                if self.repo.caja_abierta(ubicacion_id):
                    raise ValidacionError("Ya existe una caja abierta para esta sucursal.")
                caja_id = self.repo.crear_caja(ubicacion_id, fecha, saldo)
        except Exception as error:
            if isinstance(error, ValidacionError):
                raise
            raise ValidacionError("No se pudo abrir la caja; verifique que no haya otra abierta.") from error
        return Caja(ubicacion_id, fecha, saldo, id=caja_id)

    def validar_disponibilidad(self, ubicacion_id: int, producto_id: int, cantidad: int) -> None:
        """Valida un renglón al agregarlo a la venta; la confirmación repite V3."""
        stock = self._stock_requerido()
        self._validar_sucursal(ubicacion_id)
        if not isinstance(cantidad, int) or cantidad <= 0:
            raise ValidacionError("La cantidad debe ser un entero positivo.")
        producto = self.repo.obtener_producto(producto_id)
        if producto is None or not producto["activo"]:
            raise EntidadNoEncontradaError(f"El producto {producto_id} no existe o está inactivo.")
        if stock.stock_disponible(ubicacion_id, producto_id) < cantidad:
            raise ValidacionError(
                f"Stock disponible insuficiente para '{producto['nombre']}'. "
                "Solo se puede vender stock verificado."
            )

    def cerrar_caja(self, ubicacion_id: int) -> Decimal:
        """Cierra la caja activa y devuelve el saldo contado esperado."""
        caja = self.repo.caja_abierta(ubicacion_id)
        if caja is None:
            raise ValidacionError("No hay una caja abierta para esta sucursal.")
        saldo = self.repo.saldo_caja(int(caja["id"]))
        with self.db.transaccion():
            self.repo.cerrar_caja(int(caja["id"]), datetime.now())
        return saldo

    def saldo_caja_abierta(self, ubicacion_id: int) -> Decimal | None:
        """Consulta saldo inicial más ingresos y egresos de la caja activa."""
        caja = self.repo.caja_abierta(ubicacion_id)
        return self.repo.saldo_caja(int(caja["id"])) if caja else None

    def registrar_venta(
        self,
        ubicacion_id: int,
        items: dict[int, int],
        pagos: list[PagoSolicitado],
        cliente_id: int | None = None,
        vendedor: str = "",
        fecha_hora: datetime | None = None,
    ) -> int:
        """Vende 1..n productos, cobra en uno o varios medios y emite comprobante (P7)."""
        stock = self._stock_requerido()
        sucursal = self._validar_sucursal(ubicacion_id)
        if not items:
            raise ValidacionError("La venta debe incluir al menos un producto.")
        if not vendedor.strip():
            raise ValidacionError("El vendedor es obligatorio.")
        if cliente_id is not None and not self.repo.existe_cliente(cliente_id):
            raise EntidadNoEncontradaError(f"No existe el cliente con id {cliente_id}.")

        detalles: list[dict] = []
        total_base = Decimal("0.00")
        for producto_id, cantidad in items.items():
            if not isinstance(cantidad, int) or cantidad <= 0:
                raise ValidacionError("La cantidad de cada producto debe ser un entero positivo.")
            producto = self.repo.obtener_producto(producto_id)
            if producto is None or not producto["activo"]:
                raise EntidadNoEncontradaError(f"El producto {producto_id} no existe o está inactivo.")
            if stock.stock_disponible(ubicacion_id, producto_id) < cantidad:
                raise ValidacionError(
                    f"Stock disponible insuficiente para '{producto['nombre']}'. "
                    "Solo se puede vender stock verificado."
                )
            precio = dinero(producto["precio_venta_actual"])
            costo = dinero(producto["costo_actual"])
            total_base += dinero(precio * cantidad)
            detalles.append({
                "producto_id": producto_id,
                "cantidad": cantidad,
                "precio_unitario": precio,
                "costo_unitario": costo,
                "recargo_asignado": Decimal("0.00"),
            })
        total_base = dinero(total_base)
        if total_base <= 0:
            raise ValidacionError("El total de la venta debe ser mayor que cero.")

        cobros, total_cobrado, recargo_total = self._preparar_pagos(pagos, total_base, fecha_hora)
        if total_cobrado <= 0:
            raise ValidacionError("La venta debe tener al menos un cobro válido.")
        for indice, detalle in enumerate(detalles):
            if indice == len(detalles) - 1:
                asignado = recargo_total - sum(
                    (item["recargo_asignado"] for item in detalles[:-1]), Decimal("0.00")
                )
            else:
                asignado = dinero(recargo_total * detalle["precio_unitario"] * detalle["cantidad"] / total_base)
            detalle["recargo_asignado"] = dinero(asignado)

        cliente = self._obtener_cliente(cliente_id)
        fecha = fecha_hora or datetime.now()
        caja = self.repo.caja_abierta(ubicacion_id)
        if caja is None:
            raise ValidacionError("Abra la caja de la sucursal antes de registrar ventas.")

        with self.db.transaccion():
            # Revalida antes de egresar: evita confirmar con una lectura anterior del stock.
            for detalle in detalles:
                if stock.stock_disponible(ubicacion_id, detalle["producto_id"]) < detalle["cantidad"]:
                    raise ValidacionError("El stock disponible cambió; actualice la venta e intente otra vez.")
            if self.repo.caja_abierta(ubicacion_id) is None:
                raise ValidacionError("La caja se cerró antes de confirmar la venta.")
            numero = self.repo.siguiente_numero_venta(ubicacion_id)
            numero_comprobante = self.repo.siguiente_numero_comprobante(
                int(sucursal["punto_venta"]), ComprobanteFactory.tipo_para_venta(cliente)
            )
            comprobante = ComprobanteFactory.crear_para_venta(
                cliente, int(sucursal["punto_venta"]), numero_comprobante, fecha, total_cobrado
            )
            venta_id, _ = self.repo.guardar_venta(
                ubicacion_id=ubicacion_id,
                cliente_id=cliente_id,
                numero=numero,
                fecha_hora=fecha,
                vendedor=vendedor.strip(),
                total=total_cobrado,
                detalles=detalles,
                cobros=cobros,
                caja_id=int(caja["id"]),
                punto_venta=int(sucursal["punto_venta"]),
                tipo_comprobante=comprobante.tipo,
                comprobante_numero=comprobante.numero,
            )
            for detalle in detalles:
                stock.egresar(
                    ubicacion_id, detalle["producto_id"], detalle["cantidad"], f"VENTA:{venta_id}"
                )
        return venta_id

    def registrar_devolucion(
        self,
        venta_id: int,
        detalles: list[DetalleDevolucion],
        motivo: str,
        fecha_hora: datetime | None = None,
    ) -> int:
        """Acepta devoluciones de ventas reales dentro del plazo y con cantidades remanentes (V5)."""
        stock = self._stock_requerido()
        venta = self.repo.obtener_venta(venta_id)
        if venta is None:
            raise EntidadNoEncontradaError(f"No existe la venta con id {venta_id}.")
        if venta["estado"] != EstadoVenta.CONFIRMADA.value:
            raise ValidacionError("Solo se aceptan devoluciones de ventas confirmadas.")
        if not detalles:
            raise ValidacionError("La devolución debe incluir al menos un renglón.")
        if not motivo.strip():
            raise ValidacionError("El motivo de la devolución es obligatorio.")
        fecha = fecha_hora or datetime.now()
        fecha_venta = venta["fecha_hora"]
        if fecha > fecha_venta + timedelta(days=self.plazo_devolucion_dias):
            raise ValidacionError(
                f"El plazo de devolución es de {self.plazo_devolucion_dias} días desde la venta."
            )
        cobros_originales = self.repo.listar_cobros(venta_id)
        if not cobros_originales or any(
            not crear_medio_pago(cobro["medio_pago"], int(cobro["cuotas"])).permite_reintegro()
            for cobro in cobros_originales
        ):
            raise ValidacionError("Los medios de pago de esta venta no permiten reintegros.")

        ubicacion_id = int(venta["ubicacion_id"])
        sucursal = self._validar_sucursal(ubicacion_id)
        caja = self.repo.caja_abierta(ubicacion_id)
        if caja is None:
            raise ValidacionError("Abra la caja de la sucursal para registrar el reintegro.")

        filas_devolucion: list[dict] = []
        total_reintegrar = Decimal("0.00")
        ids_procesados: set[int] = set()
        for detalle_solicitado in detalles:
            detalle_id = detalle_solicitado.detalle_venta_id
            if detalle_id in ids_procesados:
                raise ValidacionError("No repita el mismo renglón en una devolución.")
            ids_procesados.add(detalle_id)
            original = self.repo.detalle_venta(detalle_id)
            if original is None or int(original["venta_id"]) != venta_id:
                raise ValidacionError("Cada renglón devuelto debe pertenecer a la venta indicada.")
            cantidad = detalle_solicitado.cantidad
            disponible = int(original["cantidad"]) - int(original["cantidad_devuelta"])
            if not isinstance(cantidad, int) or cantidad <= 0 or cantidad > disponible:
                raise ValidacionError(
                    f"La cantidad a devolver debe estar entre 1 y las {disponible} unidades restantes."
                )
            cantidad_devuelta_total = int(original["cantidad_devuelta"]) + cantidad
            importe_total_renglon = dinero(
                Decimal(original["precio_unitario"]) * int(original["cantidad"])
                + Decimal(original["recargo_asignado"])
            )
            if cantidad_devuelta_total == int(original["cantidad"]):
                objetivo_reintegrado = importe_total_renglon
            else:
                objetivo_reintegrado = dinero(
                    importe_total_renglon * cantidad_devuelta_total / int(original["cantidad"])
                )
            reintegro = dinero(objetivo_reintegrado - Decimal(original["monto_reintegrado"]))
            total_reintegrar += reintegro
            filas_devolucion.append({
                "detalle_venta_id": detalle_id,
                "producto_id": int(original["producto_id"]),
                "cantidad": cantidad,
                "reingresa_stock": detalle_solicitado.reingresa_stock,
                "monto_reintegrado": reintegro,
                "cantidad_devuelta_previa": int(original["cantidad_devuelta"]),
                "cantidad_devuelta_total": cantidad_devuelta_total,
                "monto_reintegrado_total": objetivo_reintegrado,
            })
        total_reintegrar = dinero(total_reintegrar)

        with self.db.transaccion():
            if self.repo.caja_abierta(ubicacion_id) is None:
                raise ValidacionError("La caja se cerró antes de confirmar la devolución.")
            for detalle in filas_devolucion:
                actual = self.repo.detalle_venta(detalle["detalle_venta_id"])
                if actual is None or int(actual["cantidad_devuelta"]) != detalle["cantidad_devuelta_previa"]:
                    raise ValidacionError(
                        "El renglón cambió por otra devolución; actualice las cantidades e intente otra vez."
                    )
            devolucion_id, _ = self.repo.crear_devolucion(
                venta_id=venta_id,
                fecha_hora=fecha,
                motivo=motivo.strip(),
                total=total_reintegrar,
                detalles=filas_devolucion,
                caja_id=int(caja["id"]),
                punto_venta=int(sucursal["punto_venta"]),
                nota_credito=ComprobanteFactory.crear_nota_credito(
                    int(sucursal["punto_venta"]),
                    self.repo.siguiente_numero_comprobante(
                        int(sucursal["punto_venta"]), "NOTA_CREDITO"
                    ),
                    fecha,
                    total_reintegrar,
                ),
            )
            for detalle in filas_devolucion:
                if detalle["reingresa_stock"]:
                    stock.reingresar(
                        ubicacion_id,
                        detalle["producto_id"],
                        detalle["cantidad"],
                        f"DEVOLUCION:{devolucion_id}",
                    )
        return devolucion_id

    def _preparar_pagos(
        self, pagos: list[PagoSolicitado], total_base: Decimal, fecha: datetime | None
    ) -> tuple[list[dict], Decimal, Decimal]:
        if not pagos:
            raise ValidacionError("La venta debe tener al menos un medio de pago.")
        filas: list[dict] = []
        suma_base = Decimal("0.00")
        suma_recargos = Decimal("0.00")
        for pago in pagos:
            try:
                medio = crear_medio_pago(pago.medio_pago, pago.cuotas)
            except ValueError as error:
                raise ValidacionError(str(error)) from error
            monto = dinero(pago.monto)
            if monto <= 0:
                raise ValidacionError("Cada importe de pago debe ser mayor que cero.")
            if not medio.validar(pago.datos):
                if pago.medio_pago.upper() == "CREDITO" and not 1 <= pago.cuotas <= 12:
                    raise ValidacionError("La tarjeta de crédito admite entre 1 y 12 cuotas.")
                raise ValidacionError(f"Faltan datos válidos para el pago {pago.medio_pago.upper()}.")
            recargo = dinero(medio.calcular_recargo(monto))
            suma_base += monto
            suma_recargos += recargo
            filas.append({
                "medio_pago": medio.tipo,
                "monto": monto,
                "recargo": recargo,
                "cuotas": pago.cuotas if medio.tipo == "CREDITO" else 1,
                "nro_autorizacion": pago.datos.get("autorizacion", pago.datos.get("referencia", "")).strip(),
            })
        if dinero(suma_base) != total_base:
            raise ValidacionError(
                f"Los importes base de los pagos deben sumar {total_base}; se ingresaron {dinero(suma_base)}."
            )
        return filas, dinero(suma_base + suma_recargos), dinero(suma_recargos)

    def _validar_sucursal(self, ubicacion_id: int):
        sucursal = self.repo.obtener_sucursal(ubicacion_id)
        if sucursal is None or sucursal["tipo"] != "SUCURSAL" or not sucursal["activa"]:
            raise ValidacionError("La operación requiere una sucursal activa.")
        if not sucursal["punto_venta"]:
            raise ValidacionError("La sucursal necesita un punto de venta configurado.")
        return sucursal

    def _obtener_cliente(self, cliente_id: int | None) -> Cliente | None:
        fila = self.repo.obtener_cliente(cliente_id)
        if fila is None:
            return None
        return Cliente(
            documento=fila["documento"], nombre=fila["nombre"],
            condicion_iva=CondicionIva(fila["condicion_iva"]), id=int(fila["id"]),
        )

    def _stock_requerido(self) -> StockService:
        if self.stock is None:
            raise ValidacionError("Ventas necesita el StockService de inventario para operar.")
        return self.stock