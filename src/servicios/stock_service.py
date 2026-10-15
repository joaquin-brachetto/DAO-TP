"""Servicio de stock (pohlsi): TODO cambio de stock del sistema pasa por acá.

Es el contrato que usan logística (turco) y ventas (vinchi):

    stock_disponible(ubicacion_id, producto_id)                -> int
    ingresar_pendiente(ubicacion_id, producto_id, cant, ref)   llega mercadería sin verificar
    confirmar_disponible(ubicacion_id, producto_id, cant, ref) bulto verificado: pendiente -> disponible
    registrar_merma(ubicacion_id, producto_id, cant, ref)      bulto rechazado:  pendiente -> merma
    egresar(ubicacion_id, producto_id, cant, ref)              venta / despacho (valida que alcance)
    reingresar(ubicacion_id, producto_id, cant, ref)           devolución

Además: `ingresar_compra` (el proveedor entrega al CD) y `suscribir` (Observer).

`ref` es el documento que originó el movimiento: una `Referencia("VENTA", 15)`
o, más simple, un texto con el tipo de documento ("VENTA").

Cada operación actualiza el stock y agrega un `MovimientoStock` en la misma
transacción. Si el llamador ya abrió una (por ejemplo, la confirmación de una
venta), el servicio se suma a ella: si algo falla, se deshace todo junto.

Patrón **Observer**: después de cada egreso, si el disponible llegó al mínimo
(que define maestros), se notifica a los `ObservadorStock` suscriptos.
"""

import logging
from datetime import datetime
from decimal import Decimal

from src.dominio.inventario.modelos import MovimientoStock, Referencia, Stock, TipoMovimiento
from src.excepciones import EntidadNoEncontradaError, ValidacionError
from src.persistencia.conexion import BaseDeDatos
from src.persistencia.repositorio_inventario import LecturaMaestros, MovimientoStockRepositorio, StockRepositorio
from src.servicios.maestros_service import StockMinimoService
from src.servicios.observadores_stock import ObservadorStock
from src.servicios.validaciones_inventario import decimal_no_negativo, entero_positivo

registro = logging.getLogger(__name__)

TIPOS_DE_EGRESO = (TipoMovimiento.EGRESO_VENTA, TipoMovimiento.EGRESO_DESPACHO)


class StockInsuficienteError(ValidacionError):
    """No alcanza el stock disponible (o pendiente de verificación) para la operación."""


class StockService:
    def __init__(self, db: BaseDeDatos | None = None, minimos: StockMinimoService | None = None) -> None:
        self.db = db or BaseDeDatos()
        self._stock = StockRepositorio(self.db)
        self._movimientos = MovimientoStockRepositorio(self.db)
        self._maestros = LecturaMaestros(self.db)
        self.minimos = minimos or StockMinimoService(self.db)
        self._observadores: list[ObservadorStock] = []

    # --- Observer (el servicio es el Subject) ------------------------------------

    def suscribir(self, observador: ObservadorStock) -> None:
        if observador not in self._observadores:
            self._observadores.append(observador)

    def desuscribir(self, observador: ObservadorStock) -> None:
        if observador in self._observadores:
            self._observadores.remove(observador)

    def _notificar(self, stock: Stock) -> None:
        for observador in list(self._observadores):
            try:
                observador.stock_bajo_minimo(stock)
            except Exception:  # un observador con problemas no debe frenar una venta o un despacho
                registro.exception("Falló el observador %r al notificar stock bajo el mínimo", observador)

    # --- Consultas -----------------------------------------------------------------

    def stock_disponible(self, ubicacion_id: int, producto_id: int) -> int:
        """Unidades verificadas que se pueden vender. Si nunca hubo stock, es 0."""
        stock = self._stock.de(ubicacion_id, producto_id)
        return stock.cantidad_disponible if stock else 0

    def stock_de(self, ubicacion_id: int, producto_id: int) -> Stock:
        """Stock completo (disponible, pendiente y merma). Si no hay registro, devuelve uno en cero."""
        return self._stock.de(ubicacion_id, producto_id) or Stock(producto_id, ubicacion_id)

    def listar_ubicacion(self, ubicacion_id: int) -> list[Stock]:
        return self._stock.de_ubicacion(ubicacion_id)

    # --- Operaciones del contrato ----------------------------------------------------

    def ingresar_compra(
        self,
        ubicacion_id: int,
        producto_id: int,
        cantidad: int,
        ref: Referencia | str,
        costo_unitario: Decimal | None = None,
    ) -> Stock:
        """El proveedor entrega mercadería al Centro de Distribución: sube el disponible del CD."""
        ubicacion = self._maestros.ubicacion(ubicacion_id)
        if ubicacion is not None and ubicacion["tipo"] != "CD":
            raise ValidacionError("Las compras a proveedores solo pueden ingresar al Centro de Distribución.")
        return self._mover(
            ubicacion_id, producto_id, cantidad, ref, TipoMovimiento.INGRESO_COMPRA,
            disponible=+1, costo_unitario=costo_unitario,
        )

    def ingresar_pendiente(self, ubicacion_id: int, producto_id: int, cantidad: int, ref: Referencia | str) -> Stock:
        """Llega mercadería a un local sin verificar: queda pendiente y NO se puede vender (V1)."""
        return self._mover(ubicacion_id, producto_id, cantidad, ref, TipoMovimiento.INGRESO_PENDIENTE, pendiente=+1)

    def confirmar_disponible(self, ubicacion_id: int, producto_id: int, cantidad: int, ref: Referencia | str) -> Stock:
        """Bulto verificado: las unidades pasan de pendiente a disponible, recién ahí se pueden vender."""
        return self._mover(
            ubicacion_id, producto_id, cantidad, ref, TipoMovimiento.CONFIRMACION_VERIFICADO,
            pendiente=-1, disponible=+1,
        )

    def registrar_merma(self, ubicacion_id: int, producto_id: int, cantidad: int, ref: Referencia | str) -> Stock:
        """Bulto rechazado (precinto roto): las unidades pasan de pendiente a merma y no habilitan venta."""
        return self._mover(
            ubicacion_id, producto_id, cantidad, ref, TipoMovimiento.MERMA_RECHAZO, pendiente=-1, merma=+1
        )

    def egresar(
        self,
        ubicacion_id: int,
        producto_id: int,
        cantidad: int,
        ref: Referencia | str,
        tipo: TipoMovimiento = TipoMovimiento.EGRESO_VENTA,
    ) -> Stock:
        """Sale mercadería del disponible: una venta (por defecto) o un despacho del CD.

        Para un despacho: `egresar(cd_id, producto_id, cant, ref, tipo=TipoMovimiento.EGRESO_DESPACHO)`.
        Lanza `StockInsuficienteError` si no alcanza el disponible (V3).
        """
        if tipo not in TIPOS_DE_EGRESO:
            raise ValidacionError("Un egreso solo puede ser por venta o por despacho.")
        with self.db.transaccion():
            stock = self._mover(ubicacion_id, producto_id, cantidad, ref, tipo, disponible=-1)
            if self.minimos.esta_en_minimo(producto_id, ubicacion_id, stock.cantidad_disponible):
                self._notificar(stock)
        return stock

    def reingresar(self, ubicacion_id: int, producto_id: int, cantidad: int, ref: Referencia | str) -> Stock:
        """Devolución de una venta: las unidades vuelven al disponible."""
        return self._mover(ubicacion_id, producto_id, cantidad, ref, TipoMovimiento.REINGRESO_DEVOLUCION, disponible=+1)

    # --- Internos ------------------------------------------------------------------------

    def _mover(
        self,
        ubicacion_id: int,
        producto_id: int,
        cantidad: int,
        ref: Referencia | str,
        tipo: TipoMovimiento,
        *,
        disponible: int = 0,
        pendiente: int = 0,
        merma: int = 0,
        costo_unitario: Decimal | None = None,
    ) -> Stock:
        """Aplica el movimiento: los signos de `disponible`, `pendiente` y `merma` dicen qué balde sube (+1) o baja (-1)."""
        cantidad = entero_positivo(cantidad)
        ref = self._normalizar_referencia(ref)
        producto = self._validar_existencia(producto_id, ubicacion_id)
        costo = Decimal(producto["costo_actual"]) if costo_unitario is None else decimal_no_negativo(costo_unitario)

        with self.db.transaccion():
            stock = self._stock.de(ubicacion_id, producto_id) or Stock(producto_id, ubicacion_id)
            nuevo_disponible = stock.cantidad_disponible + disponible * cantidad
            nuevo_pendiente = stock.cantidad_pendiente + pendiente * cantidad
            if nuevo_disponible < 0:
                raise StockInsuficienteError(
                    f"Stock insuficiente de «{producto['nombre']}»: se piden {cantidad} "
                    f"y hay {stock.cantidad_disponible} disponibles."
                )
            if nuevo_pendiente < 0:
                raise StockInsuficienteError(
                    f"No se pueden verificar ni rechazar {cantidad} unidades de «{producto['nombre']}»: "
                    f"solo hay {stock.cantidad_pendiente} pendientes de verificación."
                )
            stock.cantidad_disponible = nuevo_disponible
            stock.cantidad_pendiente = nuevo_pendiente
            stock.cantidad_merma += merma * cantidad
            self._stock.guardar(stock)
            self._movimientos.guardar(
                MovimientoStock(
                    stock_id=stock.id,
                    tipo=tipo,
                    cantidad=cantidad,
                    costo_unitario=costo,
                    tipo_documento=ref.tipo_documento,
                    documento_id=ref.documento_id,
                    usuario=ref.usuario,
                    fecha_hora=datetime.now(),
                )
            )
        return stock

    @staticmethod
    def _normalizar_referencia(ref: Referencia | str | None) -> Referencia:
        """Acepta una `Referencia` o un texto: "VENTA" o "VENTA:15" (tipo de documento y su id)."""
        if isinstance(ref, Referencia):
            return ref
        if isinstance(ref, str) and ref.strip():
            tipo, separador, numero = ref.strip().partition(":")
            if separador and numero.strip().isdigit():
                return Referencia(tipo.strip(), int(numero))
            return Referencia(ref.strip())
        raise ValidacionError("Todo movimiento de stock debe indicar el documento que lo origina.")

    def _validar_existencia(self, producto_id: int, ubicacion_id: int):
        producto = self._maestros.producto(producto_id)
        if producto is None:
            raise EntidadNoEncontradaError(f"No existe un producto con id {producto_id}.")
        if self._maestros.ubicacion(ubicacion_id) is None:
            raise EntidadNoEncontradaError(f"No existe una ubicación con id {ubicacion_id}.")
        return producto
