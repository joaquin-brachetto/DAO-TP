"""Punto de entrada: `python main.py` desde la raíz del proyecto.

Levanta la aplicación web y la abre en el navegador (http://127.0.0.1:5000).
Opciones:
    --sin-navegador   no abre el navegador (solo levanta el servidor)
    --escritorio      abre la versión de escritorio anterior, hecha con Tkinter
"""

import sys
import threading
import webbrowser

from src.persistencia.conexion import BaseDeDatos

DIRECCION = "127.0.0.1"
PUERTO = 5000


def main() -> None:
    BaseDeDatos().inicializar_esquema()

    if "--escritorio" in sys.argv:
        from src.ui.ventana_principal import VentanaPrincipal

        VentanaPrincipal().mainloop()
        return

    from src.web.app import crear_app

    app = crear_app()
    url = f"http://{DIRECCION}:{PUERTO}"
    if "--sin-navegador" not in sys.argv:
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    print(f"Sistema de Ventas e Inventario funcionando en {url}  (Ctrl+C para cerrarlo)")
    # Un solo hilo: la conexión a SQLite es única (Singleton) y no se comparte entre hilos.
    app.run(host=DIRECCION, port=PUERTO, debug=False, threaded=False)


if __name__ == "__main__":
    main()
