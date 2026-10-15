"""Reposición (P3, pohlsi): de las necesidades de los locales a una orden CD -> local.

    crear_necesidad(sucursal, renglones)   necesidad manual (o automática, la crea el Observer)
    sugerir_necesidad(sucursal)            calcula qué falta: stock mínimo - disponible - lo que ya viene en camino
    consolidar(necesidades)                junta necesidades PENDIENTES de un mismo local en UNA orden de reposición

Ciclo de vida de la orden (cada transición válida está en `TRANSICIONES`):

    PENDIENTE -> EN_PREPARACION -> DESPACHADA -> CERRADA_COMPLETA | CERRADA_CON_FALTANTES

Logística (turco) usa `iniciar_preparacion`, `registrar_preparado`, `marcar_despachada`
y `registrar_recibido` para ir reflejando el avance sobre la orden.
"""

from collections import defaultdict
from collections.abc import Iterable
from datetime import date, datetime

from src.dominio.inventario.modelos import (
    DetalleNecesidad,
    DetalleOrdenReposicion,
    EstadoNecesidad,
    EstadoOrdenReposicion,
    NecesidadReposicion,
    OrdenReposicion,
    OrigenNecesidad,
)
from src.excepciones import EntidadNoEncontradaError, ValidacionError
from src.persistencia.conexion import BaseDeDatos
from src.persistencia.repositorio_inventario import (
    DetalleNecesidadRepositorio,
    DetalleOrdenReposicionRepositorio,
    LecturaMaestros,
    NecesidadReposicionRepositorio,
    OrdenReposicionRepositorio,
)
from src.servicios.validaciones_inventario import entero_positivo

E = EstadoOrdenReposicion

TRANSICIONES: dict[EstadoOrdenReposicion, set[EstadoOrdenReposicion]] = {
    E.PENDIENTE: {E.EN_PREPARACION},
    E.EN_PREPARACION: {E.DESPACHADA},
    E.DESPACHADA: {E.CERRADA_COMPLETA, E.CERRADA_CON_FALTANTES},
    E.CERRADA_COMPLETA: set(),
    E.CERRADA_CON_FALTANTES: set(),
}


class ReposicionService:
    def __init__(self, db: BaseDeDatos | None = None) -> None:
        self.db = db or BaseDeDatos()
        self._necesidades = NecesidadReposicionRepositorio(self.db)
        self._detalles_necesidad = DetalleNecesidadRepositorio(self.db)
        self._ordenes = OrdenReposicionRepositorio(self.db)
        self._detalles_orden = DetalleOrdenReposicionRepositorio(self.db)
        self._maestros = LecturaMaestros(self.db)

    # === Necesidades =========================================================================

    def obtener_necesidad(self, necesidad_id: int) -> NecesidadReposicion:
        necesidad = self._necesidades.obtener(necesidad_id)
        necesidad.detalles = self._detalles_necesidad.de_necesidad(necesidad_id)
        return necesidad

    def listar_necesidades(
        self, estado: EstadoNecesidad | None = None, sucursal_id: int | None = None
    ) -> list[NecesidadReposicion]:
        filtros = {}
        if estado is not None:
            filtros["estado"] = str(estado)
        if sucursal_id is not None:
            filtros["ubicacion_id"] = sucursal_id
        necesidades = self._necesidades.buscar_por(**filtros)
        for necesidad in necesidades:
            necesidad.detalles = self._detalles_necesidad.de_necesidad(necesidad.id)
        return necesidades

    def crear_necesidad(
        self,
        sucursal_id: int,
        renglones: Iterable[tuple[int, int]],
        origen: OrigenNecesidad = OrigenNecesidad.MANUAL,
        fecha: date | None = None,
    ) -> NecesidadReposicion:
        """Registra lo que necesita una sucursal. Cada renglón es `(producto_id, cantidad)`."""
        self._exigir_sucursal(sucursal_id)
        detalles = self._armar_detalles_necesidad(renglones)
        with self.db.transaccion():
            necesidad = NecesidadReposicion(ubicacion_id=sucursal_id, fecha=fecha or date.today(), origen=origen)
            self._necesidades.guardar(necesidad)
            for detalle in detalles:
                detalle.necesidad_reposicion_id = necesidad.id
                self._detalles_necesidad.guardar(detalle)
            necesidad.detalles = detalles
        return necesidad

    def anular_necesidad(self, necesidad_id: int) -> NecesidadReposicion:
        with self.db.transaccion():
            necesidad = self.obtener_necesidad(necesidad_id)
            if necesidad.estado != EstadoNecesidad.PENDIENTE:
                raise ValidacionError(f"Solo se pueden anular necesidades PENDIENTES (esta está {necesidad.estado}).")
            necesidad.estado = EstadoNecesidad.ANULADA
            self._necesidades.guardar(necesidad)
        return necesidad

    def sugerir_necesidad(self, sucursal_id: int, producto_id: int | None = None) -> list[tuple[int, int]]:
        """Qué conviene pedir: `(producto_id, cantidad)` para los productos en o bajo su stock mínimo.

        cantidad = mínimo - disponible - pendiente de verificación (lo que ya viene en camino no se vuelve a pedir).
        """
        sugerencias = []
        for fila in self._maestros.minimos_de_sucursal(sucursal_id, producto_id):
            if fila["disponible"] > fila["cantidad_minima"]:
                continue
            faltante = fila["cantidad_minima"] - fila["disponible"] - fila["pendiente"]
            if faltante > 0:
                sugerencias.append((fila["producto_id"], faltante))
        return sugerencias

    def hay_necesidad_abierta(self, sucursal_id: int, producto_id: int) -> bool:
        """¿Ya hay una necesidad sin consolidar que pida este producto? (evita duplicados automáticos)"""
        return self._necesidades.con_producto_pendiente(sucursal_id, producto_id)

    # === Consolidación (P3) ======================================================================

    def consolidar(self, necesidad_ids: Iterable[int], fecha: datetime | None = None) -> OrdenReposicion:
        """Junta necesidades PENDIENTES de un mismo local en una orden CD -> local, sumando por producto."""
        ids = list(dict.fromkeys(necesidad_ids))
        if not ids:
            raise ValidacionError("Hay que elegir al menos una necesidad para consolidar.")
        necesidades = [self.obtener_necesidad(id_) for id_ in ids]
        for necesidad in necesidades:
            if necesidad.estado != EstadoNecesidad.PENDIENTE:
                raise ValidacionError(
                    f"La necesidad {necesidad.id} está {necesidad.estado}: solo se consolidan las PENDIENTES."
                )
        destinos = {necesidad.ubicacion_id for necesidad in necesidades}
        if len(destinos) > 1:
            raise ValidacionError("Una orden de reposición tiene un solo destino: elegí necesidades del mismo local.")
        destino_id = destinos.pop()
        centro = self._maestros.centro_distribucion_activo()
        if centro is None:
            raise ValidacionError("No hay un Centro de Distribución activo desde donde reponer.")

        totales: dict[int, int] = defaultdict(int)
        for necesidad in necesidades:
            for detalle in necesidad.detalles:
                totales[detalle.producto_id] += detalle.cantidad_solicitada

        with self.db.transaccion():
            orden = OrdenReposicion(
                numero=self._maestros.proximo_numero("orden_reposicion"),
                fecha_emision=fecha or datetime.now(),
                origen_id=centro["id"],
                destino_id=destino_id,
            )
            self._ordenes.guardar(orden)
            for producto_id, cantidad in totales.items():
                detalle = DetalleOrdenReposicion(
                    producto_id=producto_id, cantidad_solicitada=cantidad, orden_reposicion_id=orden.id
                )
                self._detalles_orden.guardar(detalle)
                orden.detalles.append(detalle)
            for necesidad in necesidades:
                necesidad.estado = EstadoNecesidad.CONSOLIDADA
                necesidad.orden_reposicion_id = orden.id
                self._necesidades.guardar(necesidad)
        return orden

    # === Órdenes de reposición ======================================================================

    def obtener(self, orden_id: int) -> OrdenReposicion:
        orden = self._ordenes.obtener(orden_id)
        orden.detalles = self._detalles_orden.de_orden(orden_id)
        return orden

    def listar(self, estado: EstadoOrdenReposicion | None = None) -> list[OrdenReposicion]:
        ordenes = self._ordenes.buscar_por(estado=str(estado)) if estado else self._ordenes.listar()
        for orden in ordenes:
            orden.detalles = self._detalles_orden.de_orden(orden.id)
        return ordenes

    def iniciar_preparacion(self, orden_id: int) -> OrdenReposicion:
        return self._cambiar_estado(orden_id, E.EN_PREPARACION)

    def marcar_despachada(self, orden_id: int) -> OrdenReposicion:
        return self._cambiar_estado(orden_id, E.DESPACHADA)

    def cerrar(self, orden_id: int) -> OrdenReposicion:
        """Cierra una orden DESPACHADA: completa si se recibió y verificó todo, con faltantes si no."""
        with self.db.transaccion():
            orden = self.obtener(orden_id)
            nuevo = E.CERRADA_COMPLETA if orden.esta_completa() else E.CERRADA_CON_FALTANTES
            self._validar_transicion(orden, nuevo)
            orden.estado = nuevo
            self._ordenes.guardar(orden)
        return orden

    def registrar_preparado(self, orden_id: int, producto_id: int, cantidad: int) -> OrdenReposicion:
        """El CD empaquetó `cantidad` unidades más de este producto (no puede superar lo solicitado)."""
        cantidad = entero_positivo(cantidad)
        with self.db.transaccion():
            orden = self.obtener(orden_id)
            self._exigir_estado(orden, E.EN_PREPARACION, "registrar lo preparado")
            detalle = self._detalle(orden, producto_id)
            if detalle.cantidad_preparada + cantidad > detalle.cantidad_solicitada:
                raise ValidacionError(
                    f"No se puede preparar más de lo solicitado: se pidieron {detalle.cantidad_solicitada} "
                    f"y ya hay {detalle.cantidad_preparada} preparadas."
                )
            detalle.cantidad_preparada += cantidad
            self._detalles_orden.guardar(detalle)
        return orden

    def registrar_recibido(self, orden_id: int, producto_id: int, cantidad: int) -> OrdenReposicion:
        """El local verificó `cantidad` unidades más de este producto (no puede superar lo preparado)."""
        cantidad = entero_positivo(cantidad)
        with self.db.transaccion():
            orden = self.obtener(orden_id)
            self._exigir_estado(orden, E.DESPACHADA, "registrar lo recibido")
            detalle = self._detalle(orden, producto_id)
            if detalle.cantidad_recibida + cantidad > detalle.cantidad_preparada:
                raise ValidacionError(
                    f"No se puede recibir más de lo despachado: se prepararon {detalle.cantidad_preparada} "
                    f"y ya se recibieron {detalle.cantidad_recibida}."
                )
            detalle.cantidad_recibida += cantidad
            self._detalles_orden.guardar(detalle)
        return orden

    # === Internos ===============================================================================

    def _cambiar_estado(self, orden_id: int, nuevo: EstadoOrdenReposicion) -> OrdenReposicion:
        with self.db.transaccion():
            orden = self.obtener(orden_id)
            self._validar_transicion(orden, nuevo)
            orden.estado = nuevo
            self._ordenes.guardar(orden)
        return orden

    @staticmethod
    def _validar_transicion(orden: OrdenReposicion, nuevo: EstadoOrdenReposicion) -> None:
        if nuevo not in TRANSICIONES[orden.estado]:
            raise ValidacionError(
                f"La orden de reposición {orden.numero} no puede pasar de {orden.estado} a {nuevo}."
            )

    @staticmethod
    def _exigir_estado(orden: OrdenReposicion, estado: EstadoOrdenReposicion, accion: str) -> None:
        if orden.estado != estado:
            raise ValidacionError(
                f"No se puede {accion} de la orden {orden.numero}: debe estar {estado} y está {orden.estado}."
            )

    @staticmethod
    def _detalle(orden: OrdenReposicion, producto_id: int) -> DetalleOrdenReposicion:
        for detalle in orden.detalles:
            if detalle.producto_id == producto_id:
                return detalle
        raise EntidadNoEncontradaError(f"La orden {orden.numero} no incluye el producto {producto_id}.")

    def _exigir_sucursal(self, sucursal_id: int) -> None:
        ubicacion = self._maestros.ubicacion(sucursal_id)
        if ubicacion is None:
            raise EntidadNoEncontradaError(f"No existe una ubicación con id {sucursal_id}.")
        if ubicacion["tipo"] != "SUCURSAL" or not ubicacion["activa"]:
            raise ValidacionError("Las necesidades de reposición son de una sucursal activa.")

    def _armar_detalles_necesidad(self, renglones: Iterable[tuple[int, int]]) -> list[DetalleNecesidad]:
        detalles: list[DetalleNecesidad] = []
        vistos: set[int] = set()
        for producto_id, cantidad in renglones:
            producto = self._maestros.producto(producto_id)
            if producto is None:
                raise EntidadNoEncontradaError(f"No existe un producto con id {producto_id}.")
            if not producto["activo"]:
                raise ValidacionError(f"El producto «{producto['nombre']}» está dado de baja.")
            if producto_id in vistos:
                raise ValidacionError(f"El producto «{producto['nombre']}» está repetido.")
            vistos.add(producto_id)
            detalles.append(DetalleNecesidad(producto_id=producto_id, cantidad_solicitada=entero_positivo(cantidad)))
        if not detalles:
            raise ValidacionError("La necesidad necesita al menos un producto.")
        return detalles
