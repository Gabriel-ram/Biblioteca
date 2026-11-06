import os
import logging
import requests
from requests.exceptions import RequestException

logger = logging.getLogger("prestamos.clients")


class ServicioNoDisponible(Exception):
    """Excepción lanzada cuando un microservicio dependiente no responde o se agota el timeout."""
    def __init__(self, servicio: str, detalle: str = None):
        super().__init__(f"Servicio '{servicio}' no disponible: {detalle}")
        self.servicio = servicio
        self.detalle = detalle


class CatalogoClient:
    """Cliente HTTP para comunicación con el microservicio Catálogo."""

    def __init__(self, base_url: str = None, timeout: float = None):
        self.base_url = (base_url or os.getenv("CATALOGO_URL", "http://catalogo:8001")).rstrip('/')
        raw_timeout = timeout if timeout is not None else float(os.getenv("CATALOGO_TIMEOUT", 3))
        # Tupla (conexión, lectura)
        self.timeout = (raw_timeout, raw_timeout) if isinstance(raw_timeout, (int, float)) else raw_timeout
        self.session = requests.Session()

    def _request(self, method: str, endpoint: str, **kwargs) -> requests.Response:
        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        kwargs.setdefault("timeout", self.timeout)
        try:
            return self.session.request(method, url, **kwargs)
        except RequestException as e:
            logger.error(f"Fallo de comunicación con Catálogo [{method} {endpoint}]: {e}")
            raise ServicioNoDisponible("Catálogo", str(e)) from e

    def descontar_disponibilidad(self, libro_id: int) -> requests.Response:
        """Descuenta disponibilidad de un libro (operación atómica, no idempotente)."""
        return self._request("PATCH", f"/libros/{libro_id}/disponibilidad", json={"operacion": "descontar"})

    def reponer_disponibilidad(self, libro_id: int) -> requests.Response:
        """Repone disponibilidad de un libro (operación atómica, no idempotente)."""
        return self._request("PATCH", f"/libros/{libro_id}/disponibilidad", json={"operacion": "reponer"})

    def obtener_libros(self, params: dict = None) -> requests.Response:
        return self._request("GET", "/libros", params=params)

    def obtener_libro(self, libro_id: int) -> requests.Response:
        return self._request("GET", f"/libros/{libro_id}")

    def crear_libro(self, data: dict) -> requests.Response:
        return self._request("POST", "/libros", json=data)

    def actualizar_libro(self, libro_id: int, data: dict) -> requests.Response:
        return self._request("PUT", f"/libros/{libro_id}", json=data)

    def eliminar_libro(self, libro_id: int) -> requests.Response:
        return self._request("DELETE", f"/libros/{libro_id}")

    def reincorporar_libro(self, libro_id: int) -> requests.Response:
        return self._request("POST", f"/libros/{libro_id}/reincorporar")

    def obtener_autores(self, params: dict = None) -> requests.Response:
        return self._request("GET", "/autores", params=params)

    def crear_autor(self, data: dict) -> requests.Response:
        return self._request("POST", "/autores", json=data)


class NotificacionesClient:
    """Cliente HTTP para comunicación con el microservicio Notificaciones."""

    def __init__(self, base_url: str = None, timeout: float = None):
        self.base_url = (base_url or os.getenv("NOTIFICACIONES_URL", "http://notificaciones:8003")).rstrip('/')
        raw_timeout = timeout if timeout is not None else float(os.getenv("NOTIFICACIONES_TIMEOUT", 2))
        self.timeout = (raw_timeout, raw_timeout) if isinstance(raw_timeout, (int, float)) else raw_timeout
        self.session = requests.Session()

    def _request(self, method: str, endpoint: str, **kwargs) -> requests.Response:
        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        kwargs.setdefault("timeout", self.timeout)
        try:
            return self.session.request(method, url, **kwargs)
        except RequestException as e:
            logger.warning(f"Fallo de comunicación con Notificaciones [{method} {endpoint}]: {e}")
            raise ServicioNoDisponible("Notificaciones", str(e)) from e

    def enviar_notificacion(
        self,
        tipo: str,
        usuario: str,
        correo: str = None,
        mensaje: str = None,
        datos: dict = None,
        clave: str = None
    ) -> requests.Response:
        """Envía una notificación al microservicio Notificaciones (asíncrona / best-effort)."""
        payload = {
            "tipo": tipo,
            "usuario": usuario
        }
        if correo is not None:
            payload["correo"] = correo
        if mensaje is not None:
            payload["mensaje"] = mensaje
        if datos is not None:
            payload["datos"] = datos
        if clave is not None:
            payload["clave"] = clave
        return self._request("POST", "/notificar", json=payload)

    def obtener_notificaciones(self, params: dict = None) -> requests.Response:
        return self._request("GET", "/notificaciones", params=params)
