"""Servicio de logística (turco): armado de bultos, precintos, remitos, despacho,
recepción en sucursal y consultas de trazabilidad inmutable (P4, P5, P6, V1, V2).

Integra transaccionalmente el modelo de dominio de logística (Patrón State en `Bulto`)
con `StockService` y `ReposicionService` (pohlsi):

- P4 (Empaquetado): a partir de una `OrdenReposicion`, valida stock disponible en el CD,
  arma los bultos, registra el avance (`registrar_preparado`), coloca precintos únicos
  (`Preparado -> Precintado`) y emite el `Remito`.
- P5 (Despacho): valida que todos los bultos del remito estén `Precintado`, los pasa a
  `EnTransito`, descuenta del disponible del CD (`EGRESO_DESPACHO`) e ingresa como
  pendiente de verificación en la sucursal destino (`INGRESO_PENDIENTE`) usando
  `Referencia("REMITO", remito.id)` (contrato con el reporte R4).
- P6 y V1 (Recepción y Verificación): registra la llegada del remito (`EnTransito -> Recibido`,
  el stock sigue pendiente y no vendible), controla el precinto de cada bulto
  (íntegro y coincidente -> `Verificado`; roto o distinto -> `Rechazado`) y, recién al
  cerrar la recepción, impacta el stock en el local (`confirmar_disponible` para verificados,
  `registrar_merma` para rechazados) y actualiza/cierra la `OrdenReposicion`.
- V2 (Trazabilidad inmutable): cada cambio de estado del bulto queda persistido en
  `cambio_estado_bulto` (protegido contra UPDATE y DELETE).
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable, Iterable, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from src.dominio.inventario.modelos import (
    EstadoOrdenReposicion,
    OrdenReposicion,
    Referencia,
    TipoMovimiento,
)
from src.dominio.logistica.modelos import (
    Bulto,
    CambioEstadoBulto,
    CodigoEstadoBulto,
    ControlBulto,
    Despacho,
    EstadoRemito,
    Precinto,
    Preparado,
    Recepcion,
    Remito,
    ResultadoControl,
    TransicionInvalidaError,
    nombre_estado_logistica,
)
from src.excepciones import EntidadDuplicadaError, EntidadNoEncontradaError, ValidacionError
from src.persistencia.conexion import BaseDeDatos
from src.persistencia.repositorio_inventario import LecturaMaestros
from src.persistencia.repositorio_logistica import (
    BultoRepositorio,
    CambioEstadoBultoRepositorio,
    ControlBultoRepositorio,
    DespachoRepositorio,
    DetalleBultoRepositorio,
    PrecintoRepositorio,
    RecepcionRepositorio,
    RemitoRepositorio,
)
from src.servicios.reposicion_service import ReposicionService
from src.servicios.stock_service import StockInsuficienteError, StockService
from src.servicios.validaciones_inventario import entero_positivo

DOCUMENTO_REMITO = "REMITO"


@dataclass
class EspecificacionBulto:
    """Datos para armar un bulto dentro de un remito."""

    renglones: Sequence[tuple[int, int]]
    numero_precinto: str | None = None
    codigo: str | None = None
    peso_kg: float | None = None


class LogisticaService:
    """Caso de uso y reglas de negocio del módulo de Logística (P4, P5, P6, V1, V2)."""

    def __init__(
        self,
        db: BaseDeDatos | None = None,
        stock_service: StockService | None = None,
        reposicion_service: ReposicionService | None = None,
        ahora: Callable[[], datetime] = datetime.now,
    ) -> None:
        self.db = db or BaseDeDatos()
        self._ahora = ahora
        self.stock_service = stock_service or StockService(self.db, ahora=self._obtener_ahora)
        self.reposicion_service = reposicion_service or ReposicionService(self.db)
        self._remitos = RemitoRepositorio(self.db)
        self._bultos = BultoRepositorio(self.db)
        self._detalles_bulto = DetalleBultoRepositorio(self.db)
        self._precintos = PrecintoRepositorio(self.db)
        self._cambios_estado = CambioEstadoBultoRepositorio(self.db)
        self._despachos = DespachoRepositorio(self.db)
        self._recepciones = RecepcionRepositorio(self.db)
        self._controles = ControlBultoRepositorio(self.db)
        self._maestros = LecturaMaestros(self.db)
        self._fecha_forzada: datetime | None = None

    def _obtener_ahora(self) -> datetime:
        if self._fecha_forzada is not None:
            return self._fecha_forzada
        return self._ahora()

    @contextmanager
    def _con_fecha(self, fecha_hora: datetime | None):
        anterior_propia = self._fecha_forzada
        anterior_stock = getattr(self.stock_service, "_ahora", None)
        if fecha_hora is not None:
            self._fecha_forzada = fecha_hora
            if anterior_stock is not None:
                self.stock_service._ahora = lambda: fecha_hora
        try:
            yield self._obtener_ahora()
        finally:
            self._fecha_forzada = anterior_propia
            if fecha_hora is not None and anterior_stock is not None:
                self.stock_service._ahora = anterior_stock

    # === Consultas e hidratación ===============================================================

    def _hidratar_bulto(self, bulto: Bulto) -> Bulto:
        if bulto.id is not None:
            bulto.detalles = self._detalles_bulto.de_bulto(bulto.id)
            bulto.precinto = self._precintos.de_bulto(bulto.id)
            bulto.cambios_estado = self._cambios_estado.de_bulto(bulto.id)
        return bulto

    def _hidratar_remito(self, remito: Remito) -> Remito:
        if remito.id is not None:
            bultos = self._bultos.de_remito(remito.id)
            remito.bultos = [self._hidratar_bulto(b) for b in bultos]
        return remito

    def _hidratar_recepcion(self, recepcion: Recepcion) -> Recepcion:
        if recepcion.id is not None:
            recepcion.controles = self._controles.de_recepcion(recepcion.id)
        return recepcion

    def obtener_bulto(self, bulto_id: int) -> Bulto:
        bulto = self._bultos.obtener(bulto_id)
        return self._hidratar_bulto(bulto)

    def obtener_bulto_por_codigo(self, codigo: str) -> Bulto:
        bulto = self._bultos.por_codigo(codigo)
        if bulto is None:
            raise EntidadNoEncontradaError(f"No existe un bulto con código «{codigo}».")
        return self._hidratar_bulto(bulto)

    def listar_bultos(
        self,
        remito_id: int | None = None,
        destino_id: int | None = None,
        estado: CodigoEstadoBulto | str | None = None,
        texto_busqueda: str | None = None,
    ) -> list[Bulto]:
        sql = (
            "SELECT b.* FROM bulto b "
            "JOIN remito r ON r.id = b.remito_id "
            "LEFT JOIN precinto p ON p.bulto_id = b.id "
            "WHERE 1 = 1"
        )
        parametros: list[Any] = []
        if remito_id is not None:
            sql += " AND b.remito_id = ?"
            parametros.append(remito_id)
        if destino_id is not None:
            sql += " AND r.destino_id = ?"
            parametros.append(destino_id)
        if estado is not None:
            sql += " AND b.estado = ?"
            parametros.append(str(estado).strip().upper())
        if texto_busqueda and texto_busqueda.strip():
            patron = f"%{texto_busqueda.strip().upper()}%"
            sql += " AND (UPPER(b.codigo) LIKE ? OR UPPER(COALESCE(p.numero, '')) LIKE ? OR UPPER(r.numero) LIKE ?)"
            parametros.extend([patron, patron, patron])
        sql += " ORDER BY b.id DESC"
        filas = self.db.consultar(sql, parametros)
        return [self._hidratar_bulto(self._bultos._a_entidad(fila)) for fila in filas]

    def historial_bulto(self, bulto_id: int) -> tuple[CambioEstadoBulto, ...]:
        """Devuelve la línea de tiempo inmutable de cambios de estado del bulto (V2)."""
        self._bultos.obtener(bulto_id)
        return tuple(self._cambios_estado.de_bulto(bulto_id))

    def control_de_bulto(self, bulto_id: int) -> ControlBulto | None:
        return self._controles.de_bulto(bulto_id)

    def obtener_remito(self, remito_id: int) -> Remito:
        remito = self._remitos.obtener(remito_id)
        return self._hidratar_remito(remito)

    def listar_remitos(
        self,
        estado: EstadoRemito | str | None = None,
        destino_id: int | None = None,
        orden_reposicion_id: int | None = None,
    ) -> list[Remito]:
        filtros: dict[str, Any] = {}
        if estado is not None:
            filtros["estado"] = str(estado)
        if destino_id is not None:
            filtros["destino_id"] = destino_id
        if orden_reposicion_id is not None:
            filtros["orden_reposicion_id"] = orden_reposicion_id
        remitos = self._remitos.buscar_por(**filtros) if filtros else self._remitos.listar()
        return [self._hidratar_remito(r) for r in remitos]

    def obtener_despacho(self, despacho_id: int) -> Despacho:
        return self._despachos.obtener(despacho_id)

    def listar_despachos(self) -> list[Despacho]:
        return self._despachos.listar()

    def obtener_recepcion(self, recepcion_id: int) -> Recepcion:
        recepcion = self._recepciones.obtener(recepcion_id)
        return self._hidratar_recepcion(recepcion)

    def obtener_recepcion_por_remito(self, remito_id: int) -> Recepcion | None:
        recepcion = self._recepciones.de_remito(remito_id)
        return self._hidratar_recepcion(recepcion) if recepcion else None

    def listar_recepciones(
        self, destino_id: int | None = None, solo_abiertas: bool = False
    ) -> list[Recepcion]:
        sql = "SELECT rec.* FROM recepcion rec JOIN remito rem ON rem.id = rec.remito_id WHERE 1 = 1"
        parametros: list[Any] = []
        if destino_id is not None:
            sql += " AND rem.destino_id = ?"
            parametros.append(destino_id)
        if solo_abiertas:
            sql += " AND rec.cerrada = 0"
        sql += " ORDER BY rec.fecha_hora_llegada DESC, rec.id DESC"
        filas = self.db.consultar(sql, parametros)
        return [self._hidratar_recepcion(self._recepciones._a_entidad(f)) for f in filas]

    # === P4: Empaquetado, Armado de Bultos, Precintado y Emisión de Remito =====================

    def crear_remito(
        self,
        orden_reposicion_id: int,
        numero_remito: str | None = None,
        fecha_emision: datetime | None = None,
    ) -> Remito:
        """Crea un remito en estado `EMITIDO` para una orden de reposición."""
        with self._con_fecha(fecha_emision) as momento, self.db.transaccion():
            orden = self._asegurar_orden_en_preparacion(orden_reposicion_id)
            numero = (numero_remito or self._remitos.proximo_numero()).strip().upper()
            if not numero:
                raise ValidacionError("El número de remito no puede estar vacío.")
            if self._remitos.por_numero(numero) is not None:
                raise EntidadDuplicadaError(f"Ya existe un remito con el número «{numero}».")
            remito = Remito(
                numero=numero,
                orden_reposicion_id=orden.id,
                origen_id=orden.origen_id,
                destino_id=orden.destino_id,
                fecha_emision=momento,
                estado=EstadoRemito.EMITIDO,
            )
            self._remitos.guardar(remito)
            return remito

    def armar_bulto(
        self,
        remito_id: int,
        renglones: Iterable[tuple[int, int]],
        codigo: str | None = None,
        peso_kg: float | None = None,
        numero_precinto: str | None = None,
        usuario: str = "sistema",
        fecha_hora: datetime | None = None,
    ) -> Bulto:
        """Empaqueta productos de la orden en un nuevo `Bulto` asociado al `Remito` (P4).

        - Valida que los productos pertenezcan a la `OrdenReposicion` y no superen lo pendiente de preparar.
        - Valida que el Centro de Distribución tenga stock disponible suficiente.
        - Registra el primer evento inmutable en `cambio_estado_bulto` (`None -> PREPARADO`).
        - Informa el avance a `ReposicionService.registrar_preparado`.
        - Si se informa `numero_precinto`, precinta el bulto en el mismo acto (`PREPARADO -> PRECINTADO`).
        """
        with self._con_fecha(fecha_hora) as momento, self.db.transaccion():
            remito = self.obtener_remito(remito_id)
            if remito.estado != EstadoRemito.EMITIDO:
                raise TransicionInvalidaError(
                    f"No se pueden armar bultos para el remito «{remito.numero}» porque está "
                    f"«{nombre_estado_logistica(remito.estado)}»."
                )
            orden = self._asegurar_orden_en_preparacion(remito.orden_reposicion_id)
            agrupados = self._normalizar_renglones_bulto(renglones, orden)

            # Validar stock disponible en el CD considerando otros bultos aún no despachados
            comprometido_cd = self._stock_comprometido_en_remitos_emitidos(orden.origen_id)
            for producto_id, cantidad in agrupados.items():
                disponible_cd = self.stock_service.stock_disponible(orden.origen_id, producto_id)
                ya_empaquetado = comprometido_cd.get(producto_id, 0)
                disponible_real = disponible_cd - ya_empaquetado
                if cantidad > disponible_real:
                    prod = self._maestros.producto(producto_id)
                    nombre_prod = prod["nombre"] if prod else f"ID {producto_id}"
                    raise StockInsuficienteError(
                        f"Stock insuficiente en el CD para empaquetar «{nombre_prod}»: se intentan armar "
                        f"{cantidad} u. y hay {max(disponible_real, 0)} u. libres en el CD."
                    )

            codigo_bulto = (codigo or self._bultos.proximo_codigo()).strip().upper()
            if not codigo_bulto:
                raise ValidacionError("El código del bulto no puede estar vacío.")
            if self._bultos.por_codigo(codigo_bulto) is not None:
                raise EntidadDuplicadaError(f"Ya existe un bulto con el código «{codigo_bulto}».")

            bulto = Bulto(
                codigo=codigo_bulto,
                remito_id=remito.id,
                fecha_creacion=momento,
                peso_kg=peso_kg,
                estado=Preparado(),
            )
            for producto_id, cantidad in agrupados.items():
                bulto.agregar_producto(producto_id, cantidad)

            self._bultos.guardar(bulto)
            for detalle in bulto.detalles:
                detalle.bulto_id = bulto.id
                self._detalles_bulto.guardar(detalle)

            cambio_inicial = CambioEstadoBulto(
                bulto_id=bulto.id,
                fecha_hora=momento,
                estado_anterior=None,
                estado_nuevo=CodigoEstadoBulto.PREPARADO.value,
                usuario=(usuario or "sistema").strip() or "sistema",
                observacion=f"Bulto armado en remito {remito.numero}",
            )
            self._cambios_estado.guardar(cambio_inicial)
            bulto.cambios_estado.append(cambio_inicial)

            for producto_id, cantidad in agrupados.items():
                self.reposicion_service.registrar_preparado(orden.id, producto_id, cantidad)

            if numero_precinto is not None and str(numero_precinto).strip():
                bulto = self.precintar_bulto(
                    bulto.id,
                    numero_precinto=str(numero_precinto),
                    usuario=usuario,
                    fecha_hora=momento,
                )

            return self.obtener_bulto(bulto.id)

    def precintar_bulto(
        self,
        bulto_id: int,
        numero_precinto: str,
        usuario: str = "sistema",
        fecha_hora: datetime | None = None,
    ) -> Bulto:
        """Coloca un precinto de seguridad con número único a un bulto en estado `Preparado` (P4)."""
        numero_limpio = (numero_precinto or "").strip().upper()
        if not numero_limpio:
            raise ValidacionError("El número de precinto es obligatorio.")

        with self._con_fecha(fecha_hora) as momento, self.db.transaccion():
            bulto = self.obtener_bulto(bulto_id)
            if self._precintos.por_numero(numero_limpio) is not None:
                raise EntidadDuplicadaError(
                    f"Ya existe un precinto registrado con el número «{numero_limpio}»."
                )
            precinto = Precinto(
                numero=numero_limpio,
                bulto_id=bulto.id,
                fecha_colocacion=momento,
                usuario_colocacion=(usuario or "sistema").strip() or "sistema",
            )
            # Delega en EstadoBulto (Patrón State): Preparado -> Precintado
            bulto.precintar(precinto, usuario=usuario, fecha_hora=momento)
            self._precintos.guardar(precinto)
            self._bultos.guardar(bulto)
            ultimo_cambio = bulto.cambios_estado[-1]
            object.__setattr__(ultimo_cambio, "bulto_id", bulto.id)
            self._cambios_estado.guardar(ultimo_cambio)
            return self.obtener_bulto(bulto.id)

    def armar_remito(
        self,
        orden_reposicion_id: int,
        bultos: Sequence[EspecificacionBulto | dict[str, Any] | tuple],
        numero_remito: str | None = None,
        usuario: str = "sistema",
        fecha_hora: datetime | None = None,
    ) -> Remito:
        """Crea un `Remito` y empaqueta todos sus `Bulto`s en una sola transacción (P4)."""
        if not bultos:
            raise ValidacionError("Debe especificar al menos un bulto para armar el remito.")
        with self._con_fecha(fecha_hora) as momento, self.db.transaccion():
            remito = self.crear_remito(
                orden_reposicion_id=orden_reposicion_id,
                numero_remito=numero_remito,
                fecha_emision=momento,
            )
            for item in bultos:
                spec = self._convertir_especificacion_bulto(item)
                self.armar_bulto(
                    remito_id=remito.id,
                    renglones=spec.renglones,
                    codigo=spec.codigo,
                    peso_kg=spec.peso_kg,
                    numero_precinto=spec.numero_precinto,
                    usuario=usuario,
                    fecha_hora=momento,
                )
            return self.obtener_remito(remito.id)

    # === P5: Despacho desde el Centro de Distribución ==========================================

    def registrar_despacho(
        self,
        remito_ids: Iterable[int],
        transportista: str,
        patente: str,
        usuario: str = "sistema",
        observaciones: str = "",
        fecha_hora: datetime | None = None,
    ) -> Despacho:
        """Registra la salida de uno o más remitos desde el CD hacia las sucursales (P5).

        - Verifica que cada remito esté `EMITIDO` y tenga todos sus bultos en estado `Precintado`.
        - Transiciona cada bulto a `EnTransito` (Patrón State) y guarda su `CambioEstadoBulto` (V2).
        - Descuenta del stock disponible del CD (`EGRESO_DESPACHO`) e ingresa como pendiente
          en la sucursal destino (`INGRESO_PENDIENTE`) con `Referencia("REMITO", remito.id)` (V1, R4).
        - Actualiza el estado del remito a `EN_TRANSITO` y la `OrdenReposicion` a `DESPACHADA`.
        """
        ids = list(dict.fromkeys(remito_ids))
        if not ids:
            raise ValidacionError("Debe seleccionar al menos un remito para despachar.")

        with self._con_fecha(fecha_hora) as momento, self.db.transaccion():
            despacho = Despacho(
                fecha_hora_salida=momento,
                transportista=transportista,
                patente=patente,
                usuario=usuario,
                observaciones=observaciones,
                remito_ids=ids,
            )
            ordenes_a_revisar: set[int] = set()

            for remito_id in ids:
                remito = self.obtener_remito(remito_id)
                if remito.estado != EstadoRemito.EMITIDO:
                    raise TransicionInvalidaError(
                        f"El remito «{remito.numero}» no se puede despachar porque está en estado "
                        f"«{nombre_estado_logistica(remito.estado)}»."
                    )
                if not remito.bultos:
                    raise ValidacionError(
                        f"El remito «{remito.numero}» no tiene bultos asociados para despachar."
                    )

                totales_por_producto: dict[int, int] = defaultdict(int)
                for bulto in remito.bultos:
                    # Delega en el estado del bulto (Patrón State): exige que esté Precintado
                    bulto.despachar(usuario=despacho.usuario, fecha_hora=momento)
                    self._bultos.guardar(bulto)
                    ultimo_cambio = bulto.cambios_estado[-1]
                    object.__setattr__(ultimo_cambio, "bulto_id", bulto.id)
                    self._cambios_estado.guardar(ultimo_cambio)
                    for detalle in bulto.detalles:
                        totales_por_producto[detalle.producto_id] += detalle.cantidad

                ref = Referencia(DOCUMENTO_REMITO, remito.id, usuario=despacho.usuario)
                for producto_id, cantidad in totales_por_producto.items():
                    self.stock_service.egresar(
                        remito.origen_id,
                        producto_id,
                        cantidad,
                        ref,
                        tipo=TipoMovimiento.EGRESO_DESPACHO,
                    )
                    self.stock_service.ingresar_pendiente(
                        remito.destino_id,
                        producto_id,
                        cantidad,
                        ref,
                    )

                remito.estado = EstadoRemito.EN_TRANSITO
                self._remitos.guardar(remito)
                ordenes_a_revisar.add(remito.orden_reposicion_id)

            self._despachos.guardar(despacho)

            for orden_id in ordenes_a_revisar:
                orden = self.reposicion_service.obtener(orden_id)
                if orden.estado == EstadoOrdenReposicion.EN_PREPARACION:
                    remitos_orden = self._remitos.de_orden(orden_id)
                    hay_emitidos = any(r.estado == EstadoRemito.EMITIDO for r in remitos_orden)
                    if not hay_emitidos:
                        self.reposicion_service.marcar_despachada(orden_id)

            return self.obtener_despacho(despacho.id)

    # === P6, V1, V2: Recepción en Sucursal y Verificación de Precintos ==========================

    def recibir_remito(
        self,
        remito_id: int,
        recibido_por: str,
        observaciones: str = "",
        fecha_hora: datetime | None = None,
    ) -> Recepcion:
        """Registra la llegada física de un remito `EN_TRANSITO` a la sucursal destino (Paso A de P6).

        Todos sus bultos pasan de `EnTransito` a `Recibido` (Patrón State), dejando constancia
        en `cambio_estado_bulto`. El stock en la sucursal permanece como *pendiente* (V1).
        """
        with self._con_fecha(fecha_hora) as momento, self.db.transaccion():
            remito = self.obtener_remito(remito_id)
            if remito.estado != EstadoRemito.EN_TRANSITO:
                raise TransicionInvalidaError(
                    f"El remito «{remito.numero}» no puede recibirse porque está en estado "
                    f"«{nombre_estado_logistica(remito.estado)}» (debe estar En tránsito)."
                )
            if self._recepciones.de_remito(remito.id) is not None:
                raise EntidadDuplicadaError(
                    f"El remito «{remito.numero}» ya tiene una recepción registrada."
                )

            recepcion = Recepcion(
                remito_id=remito.id,
                fecha_hora_llegada=momento,
                recibido_por=recibido_por,
                observaciones=observaciones,
                cerrada=False,
            )
            self._recepciones.guardar(recepcion)

            for bulto in remito.bultos:
                bulto.recibir(usuario=recepcion.recibido_por, fecha_hora=momento)
                self._bultos.guardar(bulto)
                ultimo_cambio = bulto.cambios_estado[-1]
                object.__setattr__(ultimo_cambio, "bulto_id", bulto.id)
                self._cambios_estado.guardar(ultimo_cambio)

            remito.estado = EstadoRemito.RECIBIDO
            self._remitos.guardar(remito)
            return self.obtener_recepcion(recepcion.id)

    iniciar_recepcion = recibir_remito

    def registrar_control_bulto(
        self,
        recepcion_id: int,
        bulto_id: int,
        numero_precinto_leido: str,
        precinto_integro: bool,
        observacion: str = "",
        usuario: str | None = None,
        fecha_hora: datetime | None = None,
    ) -> ControlBulto:
        """Evalúa el precinto de un bulto recibido y lo transiciona a `Verificado` o `Rechazado` (P6, V1)."""
        leido = (numero_precinto_leido or "").strip().upper()
        if not leido:
            raise ValidacionError("Debe ingresar el número de precinto leído en el bulto.")

        with self._con_fecha(fecha_hora) as momento, self.db.transaccion():
            recepcion = self.obtener_recepcion(recepcion_id)
            if recepcion.cerrada:
                raise TransicionInvalidaError(
                    "No se pueden controlar más bultos porque la recepción ya fue cerrada."
                )
            bulto = self.obtener_bulto(bulto_id)
            if bulto.remito_id != recepcion.remito_id:
                raise ValidacionError(
                    f"El bulto «{bulto.codigo}» no pertenece al remito de esta recepción."
                )
            if self._controles.de_bulto(bulto.id) is not None:
                raise EntidadDuplicadaError(
                    f"El bulto «{bulto.codigo}» ya fue controlado en esta recepción."
                )

            esperado = bulto.precinto.numero.strip().upper() if bulto.precinto else ""
            coincide = bool(esperado) and (leido == esperado)
            integro = bool(precinto_integro)
            responsable = (usuario or recepcion.recibido_por or "sistema").strip() or "sistema"
            obs_limpia = (observacion or "").strip()

            if integro and coincide:
                obs_verificado = obs_limpia or f"Precinto {leido} íntegro y coincidente"
                bulto.verificar(usuario=responsable, observacion=obs_verificado, fecha_hora=momento)
                resultado = ResultadoControl.VERIFICADO.value
                observacion_control = obs_verificado
            else:
                motivo = self._armar_motivo_rechazo(
                    esperado=esperado,
                    leido=leido,
                    integro=integro,
                    coincide=coincide,
                    observacion=obs_limpia,
                )
                bulto.rechazar(motivo=motivo, usuario=responsable, fecha_hora=momento)
                resultado = ResultadoControl.RECHAZADO.value
                observacion_control = motivo

            self._bultos.guardar(bulto)
            ultimo_cambio = bulto.cambios_estado[-1]
            object.__setattr__(ultimo_cambio, "bulto_id", bulto.id)
            self._cambios_estado.guardar(ultimo_cambio)

            control = ControlBulto(
                recepcion_id=recepcion.id,
                bulto_id=bulto.id,
                numero_precinto_leido=leido,
                precinto_integro=integro,
                coincide_precinto=coincide,
                resultado=resultado,
                observacion=observacion_control,
                fecha_hora_control=momento,
            )
            self._controles.guardar(control)
            return control

    def cerrar_recepcion(
        self,
        recepcion_id: int,
        usuario: str | None = None,
        fecha_hora: datetime | None = None,
    ) -> Recepcion:
        """Cierra la recepción cuando todos los bultos del remito fueron controlados e impacta el stock (V1).

        - Si todos los bultos están `Verificado`, el remito pasa a `VERIFICADO`.
        - Si al menos un bulto está `Rechazado`, el remito pasa a `VERIFICADO_CON_RECHAZOS`.
        - Recién en este punto se llama a `StockService.confirmar_disponible` para los bultos
          verificados (habilitando la venta) y a `StockService.registrar_merma` para los rechazados
          (bloqueando la venta y registrando pérdida por rechazo logístico).
        """
        with self._con_fecha(fecha_hora), self.db.transaccion():
            recepcion = self.obtener_recepcion(recepcion_id)
            if recepcion.cerrada:
                raise TransicionInvalidaError("La recepción ya se encuentra cerrada.")
            remito = self.obtener_remito(recepcion.remito_id)
            if remito.estado != EstadoRemito.RECIBIDO:
                raise TransicionInvalidaError(
                    f"El remito «{remito.numero}» debe estar en estado Recibido para cerrar su verificación "
                    f"(actualmente está «{nombre_estado_logistica(remito.estado)}»)."
                )

            # Verifica que todos los bultos hayan llegado a estado final (Verificado o Rechazado)
            remito.cerrar_verificacion()
            self._remitos.guardar(remito)

            recepcion.cerrada = True
            self._recepciones.guardar(recepcion)

            responsable = (usuario or recepcion.recibido_por or "sistema").strip() or "sistema"
            ref = Referencia(DOCUMENTO_REMITO, remito.id, usuario=responsable)

            orden = self.reposicion_service.obtener(remito.orden_reposicion_id)
            if orden.estado == EstadoOrdenReposicion.EN_PREPARACION:
                self.reposicion_service.marcar_despachada(orden.id)

            for bulto in remito.bultos:
                if bulto.nombre_estado == CodigoEstadoBulto.VERIFICADO.value:
                    for detalle in bulto.detalles:
                        self.stock_service.confirmar_disponible(
                            remito.destino_id,
                            detalle.producto_id,
                            detalle.cantidad,
                            ref,
                        )
                        self.reposicion_service.registrar_recibido(
                            remito.orden_reposicion_id,
                            detalle.producto_id,
                            detalle.cantidad,
                        )
                elif bulto.nombre_estado == CodigoEstadoBulto.RECHAZADO.value:
                    for detalle in bulto.detalles:
                        self.stock_service.registrar_merma(
                            remito.destino_id,
                            detalle.producto_id,
                            detalle.cantidad,
                            ref,
                        )

            self._intentar_cerrar_orden_reposicion(remito.orden_reposicion_id)
            return self.obtener_recepcion(recepcion.id)

    def procesar_recepcion_completa(
        self,
        remito_id: int,
        recibido_por: str,
        controles_por_bulto: Sequence[dict[str, Any] | tuple],
        observaciones: str = "",
        fecha_hora: datetime | None = None,
    ) -> Recepcion:
        """Ejecuta en una sola transacción la llegada del remito, el control de cada bulto y el cierre (P6, V1)."""
        with self._con_fecha(fecha_hora) as momento, self.db.transaccion():
            remito = self.obtener_remito(remito_id)
            if remito.estado == EstadoRemito.EN_TRANSITO:
                recepcion = self.recibir_remito(
                    remito_id=remito.id,
                    recibido_por=recibido_por,
                    observaciones=observaciones,
                    fecha_hora=momento,
                )
            elif remito.estado == EstadoRemito.RECIBIDO:
                existente = self.obtener_recepcion_por_remito(remito.id)
                if existente is None:
                    raise ValidacionError(
                        f"El remito «{remito.numero}» figura recibido pero no tiene acta de recepción."
                    )
                recepcion = existente
            else:
                raise TransicionInvalidaError(
                    f"El remito «{remito.numero}» no puede recepcionarse porque está "
                    f"«{nombre_estado_logistica(remito.estado)}»."
                )

            if not controles_por_bulto:
                raise ValidacionError("Debe informar el control de precinto de los bultos del remito.")

            ya_controlados = {c.bulto_id for c in recepcion.controles}
            for item in controles_por_bulto:
                bulto_id, precinto_leido, integro, obs = self._desempaquetar_control(item)
                if bulto_id not in ya_controlados:
                    self.registrar_control_bulto(
                        recepcion_id=recepcion.id,
                        bulto_id=bulto_id,
                        numero_precinto_leido=precinto_leido,
                        precinto_integro=integro,
                        observacion=obs,
                        usuario=recibido_por,
                        fecha_hora=momento,
                    )

            return self.cerrar_recepcion(
                recepcion_id=recepcion.id,
                usuario=recibido_por,
                fecha_hora=momento,
            )

    # === Auxiliares internos ===================================================================

    def _asegurar_orden_en_preparacion(self, orden_reposicion_id: int) -> OrdenReposicion:
        orden = self.reposicion_service.obtener(orden_reposicion_id)
        if orden.estado == EstadoOrdenReposicion.PENDIENTE:
            orden = self.reposicion_service.iniciar_preparacion(orden.id)
        elif orden.estado != EstadoOrdenReposicion.EN_PREPARACION:
            raise ValidacionError(
                f"La orden de reposición N° {orden.numero} está en estado «{orden.estado}»: "
                "solo se pueden armar bultos para órdenes pendientes o en preparación."
            )
        return orden

    def _normalizar_renglones_bulto(
        self, renglones: Iterable[tuple[int, int]], orden: OrdenReposicion
    ) -> dict[int, int]:
        por_producto_orden = {d.producto_id: d for d in orden.detalles}
        agrupados: dict[int, int] = defaultdict(int)
        for item in renglones:
            if not isinstance(item, (tuple, list)) or len(item) != 2:
                raise ValidacionError("Cada renglón del bulto debe ser un par (producto_id, cantidad).")
            producto_id, cantidad = item
            producto_id = entero_positivo(producto_id, "producto_id")
            cantidad = entero_positivo(cantidad, "cantidad")
            if producto_id not in por_producto_orden:
                raise EntidadNoEncontradaError(
                    f"El producto {producto_id} no forma parte de la orden de reposición N° {orden.numero}."
                )
            agrupados[producto_id] += cantidad

        if not agrupados:
            raise ValidacionError("El bulto debe contener al menos un producto.")

        for producto_id, cantidad_total in agrupados.items():
            detalle_orden = por_producto_orden[producto_id]
            pendiente_preparar = detalle_orden.cantidad_solicitada - detalle_orden.cantidad_preparada
            if cantidad_total > pendiente_preparar:
                prod = self._maestros.producto(producto_id)
                nombre_prod = prod["nombre"] if prod else f"ID {producto_id}"
                raise ValidacionError(
                    f"No se pueden empaquetar {cantidad_total} u. de «{nombre_prod}»: "
                    f"la orden N° {orden.numero} solicitó {detalle_orden.cantidad_solicitada} u. "
                    f"y ya tiene {detalle_orden.cantidad_preparada} u. preparadas "
                    f"(pendiente de preparar: {pendiente_preparar} u.)."
                )
        return dict(agrupados)

    def _stock_comprometido_en_remitos_emitidos(self, origen_id: int) -> dict[int, int]:
        filas = self.db.consultar(
            "SELECT db.producto_id, COALESCE(SUM(db.cantidad), 0) AS comprometido "
            "FROM detalle_bulto db "
            "JOIN bulto b ON b.id = db.bulto_id "
            "JOIN remito r ON r.id = b.remito_id "
            "WHERE r.origen_id = ? AND r.estado = 'EMITIDO' "
            "GROUP BY db.producto_id",
            (origen_id,),
        )
        return {f["producto_id"]: int(f["comprometido"]) for f in filas}

    @staticmethod
    def _convertir_especificacion_bulto(
        item: EspecificacionBulto | dict[str, Any] | tuple,
    ) -> EspecificacionBulto:
        if isinstance(item, EspecificacionBulto):
            return item
        if isinstance(item, dict):
            return EspecificacionBulto(
                renglones=item.get("renglones", []),
                numero_precinto=item.get("numero_precinto") or item.get("precinto"),
                codigo=item.get("codigo"),
                peso_kg=item.get("peso_kg"),
            )
        if isinstance(item, (tuple, list)):
            if len(item) == 2:
                return EspecificacionBulto(renglones=item[0], numero_precinto=item[1])
            if len(item) == 3:
                return EspecificacionBulto(renglones=item[0], numero_precinto=item[1], peso_kg=item[2])
            if len(item) >= 4:
                return EspecificacionBulto(
                    renglones=item[0], numero_precinto=item[1], codigo=item[2], peso_kg=item[3]
                )
        raise ValidacionError("Especificación de bulto inválida.")

    @staticmethod
    def _desempaquetar_control(item: dict[str, Any] | tuple) -> tuple[int, str, bool, str]:
        if isinstance(item, dict):
            return (
                int(item["bulto_id"]),
                str(item["numero_precinto_leido"]),
                bool(item["precinto_integro"]),
                str(item.get("observacion", "")),
            )
        if isinstance(item, (tuple, list)) and len(item) >= 3:
            obs = str(item[3]) if len(item) >= 4 else ""
            return int(item[0]), str(item[1]), bool(item[2]), obs
        raise ValidacionError(
            "Cada control de bulto debe indicar (bulto_id, numero_precinto_leido, precinto_integro[, observacion])."
        )

    @staticmethod
    def _armar_motivo_rechazo(
        *,
        esperado: str,
        leido: str,
        integro: bool,
        coincide: bool,
        observacion: str,
    ) -> str:
        if not integro and not coincide:
            base = f"Precinto roto/violado y no coincide (esperado: {esperado or 'S/D'}, leído: {leido})"
        elif not integro:
            base = f"Precinto roto/violado (N° {leido})"
        else:
            base = f"Precinto no coincide (esperado: {esperado or 'S/D'}, leído: {leido})"
        if observacion:
            return f"{base} – {observacion}"
        return base

    def _intentar_cerrar_orden_reposicion(self, orden_reposicion_id: int) -> None:
        orden = self.reposicion_service.obtener(orden_reposicion_id)
        if orden.estado != EstadoOrdenReposicion.DESPACHADA:
            return
        remitos = self._remitos.de_orden(orden_reposicion_id)
        if not remitos:
            return
        todos_cerrados = all(
            r.estado in (EstadoRemito.VERIFICADO, EstadoRemito.VERIFICADO_CON_RECHAZOS)
            for r in remitos
        )
        if todos_cerrados:
            self.reposicion_service.cerrar(orden_reposicion_id)
