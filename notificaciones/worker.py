import os
import time
import logging
import threading
from datetime import datetime, timedelta
from database import get_db_connection
from mailer import preparar_contenido_correo, enviar_correo, enmascarar_correo

logger = logging.getLogger("notificaciones.worker")

_worker_thread = None
_worker_lock = threading.Lock()
_worker_running = threading.Event()

# Intervalos de backoff exponencial en segundos: 30s, 2m, 10m, 1h, 1h
BACKOFF_STEPS = [30, 120, 600, 3600, 3600]


def procesar_notificaciones_pendientes():
    max_intentos = int(os.getenv("MAX_INTENTOS", 5))
    ahora_dt = datetime.now()
    ahora_str = ahora_dt.isoformat()

    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        # 1. Obtener candidatos en estado PENDIENTE listos para procesar
        cursor.execute(
            """
            SELECT id, tipo, usuario, correo_destino, asunto, mensaje, datos, intentos
            FROM notificaciones
            WHERE estado = 'PENDIENTE'
              AND (proximo_intento IS NULL OR proximo_intento <= ?)
              AND intentos < ?
            ORDER BY id ASC
            LIMIT 10
            """,
            (ahora_str, max_intentos)
        )
        candidatos = [dict(row) for row in cursor.fetchall()]

        for item in candidatos:
            notif_id = item['id']
            correo_destino = item['correo_destino']
            intentos_actuales = item['intentos'] or 0

            # Si por alguna razón no tiene correo destino, pasa a FALLIDA directamente
            if not correo_destino or "@" not in correo_destino:
                cursor.execute(
                    """
                    UPDATE notificaciones
                    SET estado = 'FALLIDA', ultimo_error = 'sin correo destino', proximo_intento = NULL
                    WHERE id = ?
                    """,
                    (notif_id,)
                )
                conn.commit()
                continue

            # 2. Reclamar la fila atómicamente con bloqueo de 120s
            bloqueo_dt = datetime.now() + timedelta(seconds=120)
            bloqueo_str = bloqueo_dt.isoformat()
            cursor.execute(
                """
                UPDATE notificaciones
                SET proximo_intento = ?
                WHERE id = ?
                  AND estado = 'PENDIENTE'
                  AND (proximo_intento IS NULL OR proximo_intento <= ?)
                """,
                (bloqueo_str, notif_id, ahora_str)
            )
            conn.commit()

            if cursor.rowcount == 0:
                # Ya fue reclamada por otro hilo
                continue

            # 3. Intentar envío de correo
            try:
                asunto, texto_plano, html_content = preparar_contenido_correo(
                    tipo=item['tipo'],
                    usuario=item['usuario'],
                    asunto=item['asunto'],
                    mensaje=item['mensaje'],
                    datos_raw=item['datos']
                )

                enviar_correo(
                    correo_destino=correo_destino,
                    asunto=asunto,
                    texto_plano=texto_plano,
                    html_content=html_content
                )

                fecha_envio = datetime.now().isoformat()
                cursor.execute(
                    """
                    UPDATE notificaciones
                    SET estado = 'ENVIADA', fecha_envio = ?, ultimo_error = NULL
                    WHERE id = ?
                    """,
                    (fecha_envio, notif_id)
                )
                conn.commit()
                logger.info(
                    f"Notificación #{notif_id} [{item['tipo']}] enviada exitosamente a {enmascarar_correo(correo_destino)}"
                )

            except Exception as e:
                nuevos_intentos = intentos_actuales + 1
                error_str = str(e)
                logger.warning(
                    f"Fallo al enviar notificación #{notif_id} a {enmascarar_correo(correo_destino)} "
                    f"(intento {nuevos_intentos}/{max_intentos}): {error_str}"
                )

                if nuevos_intentos >= max_intentos:
                    cursor.execute(
                        """
                        UPDATE notificaciones
                        SET estado = 'FALLIDA', intentos = ?, ultimo_error = ?, proximo_intento = NULL
                        WHERE id = ?
                        """,
                        (nuevos_intentos, error_str, notif_id)
                    )
                else:
                    backoff_seg = BACKOFF_STEPS[min(nuevos_intentos - 1, len(BACKOFF_STEPS) - 1)]
                    proximo = (datetime.now() + timedelta(seconds=backoff_seg)).isoformat()
                    cursor.execute(
                        """
                        UPDATE notificaciones
                        SET intentos = ?, ultimo_error = ?, proximo_intento = ?
                        WHERE id = ?
                        """,
                        (nuevos_intentos, error_str, proximo, notif_id)
                    )
                conn.commit()

    finally:
        conn.close()


def _worker_loop():
    logger.info("Bucle del worker de notificaciones iniciado.")
    while _worker_running.is_set():
        try:
            procesar_notificaciones_pendientes()
        except Exception as err:
            logger.error(f"Error inesperado en ciclo de procesamiento del worker: {err}")

        intervalo = float(os.getenv("WORKER_INTERVAL", 5))
        # Dormir en pequeños intervalos para responder rápidamente a detención
        tiempo_dormido = 0.0
        while tiempo_dormido < intervalo and _worker_running.is_set():
            time.sleep(min(0.5, intervalo - tiempo_dormido))
            tiempo_dormido += 0.5


def start_worker():
    """Inicia el hilo demonio del worker si aún no está corriendo (con guarda global)."""
    global _worker_thread
    with _worker_lock:
        if _worker_thread is not None and _worker_thread.is_alive():
            return
        _worker_running.set()
        _worker_thread = threading.Thread(
            target=_worker_loop,
            name="NotificacionesWorker",
            daemon=True
        )
        _worker_thread.start()
        logger.info("Hilo demonio de Notificaciones iniciado correctamente.")

