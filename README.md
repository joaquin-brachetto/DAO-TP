# DAO-TP

TP Integrador de Desarrollo de Aplicaciones con Objetos, tema 3: **Sistema de Ventas e Inventario
(Centro de Distribución → Locales)**.

- Consigna: [`TPI VENTAS.pdf`](TPI%20VENTAS.pdf)
- División de tareas: [`PLAN_DE_TRABAJO.md`](PLAN_DE_TRABAJO.md)
- Modelo de dominio: [`docs/modelo_dominio.md`](docs/modelo_dominio.md)

## Cómo ejecutar

Requiere **Python 3.11 o superior** con Tkinter (en Windows y macOS viene incluido; en Linux
puede hacer falta instalar `python3-tk`). No hay dependencias externas por ahora.

```bash
python main.py
```

La primera vez se crea la base de datos en `datos/ventas.db` con todas las tablas. Esa carpeta
no se sube al repositorio: cada uno tiene su propia base local.

> Si alguien cambia un `CREATE TABLE` que ya existía, hay que **borrar `datos/ventas.db`**
> para que se vuelva a crear con la estructura nueva.

## Cómo correr los tests

```bash
python -m unittest
```

Los tests usan una base en memoria, así que no tocan `datos/ventas.db`.

## Estructura

```
main.py                     # punto de entrada
src/
  config.py                 # ruta de la base, título, etc.
  excepciones.py            # errores de negocio comunes (ValidacionError, EntidadDuplicadaError...)
  persistencia/
    conexion.py             # BaseDeDatos (Singleton): conexión, transacciones, consultas
    repositorio_base.py     # RepositorioBase (Repository): guardar / obtener / listar / eliminar
    esquema/                # un .sql por módulo, se ejecutan en orden
      01_maestros.sql       #   brache
      02_inventario.sql     #   pohlsi
      03_logistica.sql      #   turco
      04_ventas.sql         #   vinchi
  dominio/                  # clases del dominio, una carpeta por módulo
    maestros/ inventario/ logistica/ ventas/
  servicios/                # lógica de negocio y validaciones
  ui/
    ventana_principal.py    # ventana con el menú
    menu.py                 # opciones del menú: acá se enchufa cada pantalla
    componentes.py          # Grilla, Formulario, mensajes de error/confirmación
  reportes/
tests/
docs/
```

## Cómo agregar algo de tu módulo

1. **Tablas:** escribí tus `CREATE TABLE IF NOT EXISTS` en tu archivo de `src/persistencia/esquema/`.
2. **Clase de dominio:** un `@dataclass` en `src/dominio/<tu_modulo>/`, con un atributo `id: int | None = None`.
3. **Repositorio:** heredá de `RepositorioBase` e indicá la tabla y la clase:

   ```python
   class ProveedorRepositorio(RepositorioBase[Proveedor]):
       tabla = "proveedor"
       entidad = Proveedor
       campo_activo = "activo"   # opcional: eliminar = baja lógica
   ```

   Ya tenés `guardar`, `obtener`, `obtener_por_id`, `listar`, `buscar_por`, `existe` y `eliminar`.
   Si un atributo no coincide con una columna (por ejemplo `categoria: Categoria` y `categoria_id`),
   redefiní `_a_entidad` y `_a_fila`.
4. **Servicio:** las reglas de negocio van en `src/servicios/`. Ante un dato inválido, lanzá
   `ValidacionError` (o otra de `src/excepciones.py`) con un mensaje para el usuario.
   Si una operación toca varias tablas, envolvela en `with BaseDeDatos().transaccion():`.
5. **Pantalla:** creá una función `abrir_xxx(padre)` que abra un `tk.Toplevel`, y reemplazá el
   `None` correspondiente en `src/ui/menu.py`. Usá `Grilla`, `Formulario` y
   `ejecutar_con_manejo_de_errores` de `src/ui/componentes.py`.
6. **Tests:** en `tests/`, heredando de `TestConBaseEnMemoria` (`tests/utilidades.py`).

## Convenciones de la base de datos

| Qué | Convención | Ejemplo |
|-----|-----------|---------|
| Tablas y columnas | `snake_case`, tabla en singular | `orden_reposicion`, `fecha_emision` |
| Clave primaria | `id INTEGER PRIMARY KEY AUTOINCREMENT` | |
| Clave foránea | `<tabla>_id` + `REFERENCES <tabla> (id)` | `producto_id INTEGER NOT NULL REFERENCES producto (id)` |
| Dinero | `DECIMAL(12, 2)` → en Python es `Decimal` (nunca `float`) | `precio_unitario DECIMAL(12, 2)` |
| Fecha y hora | `TIMESTAMP` → `datetime` | `fecha_hora TIMESTAMP NOT NULL` |
| Solo fecha | `DATE` → `date` | |
| Sí / no | `BOOLEAN` + `CHECK (x IN (0, 1))` → `bool` | `activo BOOLEAN NOT NULL DEFAULT 1` |
| Estados y tipos | `TEXT` + `CHECK (... IN (...))`, en mayúsculas | `estado TEXT NOT NULL CHECK (estado IN ('PENDIENTE', 'DESPACHADA'))` |
| Ubicaciones | Sucursales y CD están en la tabla `ubicacion` (`tipo` = `'SUCURSAL'` o `'CD'`) | `destino_id INTEGER REFERENCES ubicacion (id)` |

## Forma de trabajo

Ver la sección 6 de [`PLAN_DE_TRABAJO.md`](PLAN_DE_TRABAJO.md): una rama por tarea, Pull Request a
`main` y revisión de otro integrante antes de mergear.
