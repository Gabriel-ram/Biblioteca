import os
import re
import ssl
import json
import html
import smtplib
import logging
import email.utils
from email.message import EmailMessage

logger = logging.getLogger("notificaciones.mailer")


def enmascarar_correo(correo: str) -> str:
    """Enmascara una dirección de correo para logs de seguridad (ej. a***@dominio.com)."""
    if not correo or "@" not in correo:
        return "<sin-correo>"
    partes = correo.strip().split("@", 1)
    user_part = partes[0]
    domain_part = partes[1]
    if len(user_part) <= 1:
        mascara = user_part + "***"
    else:
        mascara = user_part[0] + "***"
    return f"{mascara}@{domain_part}"


def preparar_contenido_correo(tipo: str, usuario: str, asunto: str = None, mensaje: str = None, datos_raw = None):
    """Genera asunto, texto plano y HTML autosuficientes según los 9 estados oficiales de notificación."""
    datos = {}
    if isinstance(datos_raw, str) and datos_raw.strip():
        try:
            parsed = json.loads(datos_raw)
            datos = parsed if isinstance(parsed, dict) else {}
        except Exception:
            datos = {}
    elif isinstance(datos_raw, dict):
        datos = datos_raw
    else:
        datos = {}

    titulo = datos.get("titulo") or datos.get("libro_titulo") or "Libro de la biblioteca"
    fecha_limite = datos.get("fecha_limite") or "Consultar en el sistema"
    fecha_prestamo = datos.get("fecha_prestamo") or "Fecha registrada"
    fecha_devolucion = datos.get("fecha_devolucion") or "Hoy"
    monto = datos.get("monto") or datos.get("monto_multa")
    dias_retraso = datos.get("dias_retraso")

    contacto = os.getenv("BIBLIOTECA_CONTACTO") or "Biblioteca Central — contacto@biblioteca.example.com"
    tipo_norm = (tipo or "").strip().upper()

    # 1. PRESTAMO_REGISTRADO: se registra el préstamo
    if tipo_norm in ("PRESTAMO_REGISTRADO", "PRESTAMO"):
        asunto_def = f"Biblioteca: Préstamo registrado - {titulo}"
        dias_prestamo = datos.get("dias_prestamo")
        dias_txt = f"- Duración del préstamo: {dias_prestamo} día(s)\n" if dias_prestamo else ""
        dias_html = f"\n    <li><strong>Duración del préstamo:</strong> {dias_prestamo} día(s)</li>" if dias_prestamo else ""
        texto_plano = (
            f"Estimado/a {usuario}:\n\n"
            f"Confirmamos el registro exitoso de tu préstamo:\n"
            f"- Libro: {titulo}\n"
            f"- Fecha de préstamo: {fecha_prestamo}\n"
            f"{dias_txt}"
            f"- Fecha límite de entrega: {fecha_limite}\n\n"
            f"{mensaje if mensaje else 'Recuerda devolver el libro a tiempo para mantener tu cuenta al día.'}\n\n"
            f"---\n"
            f"{contacto}\n"
        )
        html_content = f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
  <h2 style="color: #2563eb;">Préstamo Registrado</h2>
  <p>Estimado/a <strong>{html.escape(usuario)}</strong>:</p>
  <p>Confirmamos el registro exitoso de tu préstamo:</p>
  <ul>
    <li><strong>Libro:</strong> {html.escape(titulo)}</li>
    <li><strong>Fecha de préstamo:</strong> {html.escape(str(fecha_prestamo))}</li>{dias_html}
    <li><strong>Fecha límite de entrega:</strong> {html.escape(str(fecha_limite))}</li>
  </ul>
  <p>{html.escape(mensaje if mensaje else 'Recuerda devolver el libro a tiempo para mantener tu cuenta al día.')}</p>
  <hr style="border: 0; border-top: 1px solid #ddd; margin: 20px 0;">
  <p style="font-size: 0.85em; color: #7f8c8d;">{html.escape(contacto)}</p>
</body>
</html>"""

    # 2. RECORDATORIO: falta 1 día
    elif tipo_norm in ("RECORDATORIO", "POR_VENCER"):
        asunto_def = f"Biblioteca: Recordatorio (1 día antes) - {titulo}"
        texto_plano = (
            f"Estimado/a {usuario}:\n\n"
            f"Te recordamos que falta exactamente 1 día para la fecha límite de entrega de tu libro:\n"
            f"- Libro: {titulo}\n"
            f"- Fecha límite de entrega: {fecha_limite}\n\n"
            f"Por favor realiza la devolución a tiempo para evitar vencimientos y sanciones.\n\n"
            f"---\n"
            f"{contacto}\n"
        )
        html_content = f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
  <h2 style="color: #d97706;">Recordatorio de Vencimiento (1 día antes)</h2>
  <p>Estimado/a <strong>{html.escape(usuario)}</strong>:</p>
  <p>Te recordamos que <strong>mañana es la fecha límite</strong> para la entrega de tu préstamo:</p>
  <ul>
    <li><strong>Libro:</strong> {html.escape(titulo)}</li>
    <li><strong>Fecha límite acordada:</strong> {html.escape(str(fecha_limite))}</li>
  </ul>
  <p>Por favor realiza la devolución a tiempo en la biblioteca para evitar sanciones en tu cuenta.</p>
  <hr style="border: 0; border-top: 1px solid #ddd; margin: 20px 0;">
  <p style="font-size: 0.85em; color: #7f8c8d;">{html.escape(contacto)}</p>
</body>
</html>"""

    # 3. VENCIMIENTO: se acabó el plazo, tiene 7 días extras
    elif tipo_norm == "VENCIMIENTO":
        asunto_def = f"Biblioteca: Plazo vencido - Tienes 7 días extras ({titulo})"
        texto_plano = (
            f"Estimado/a {usuario}:\n\n"
            f"Te informamos que se ha cumplido el plazo de entrega pactado para el libro:\n\n"
            f"Libro: {titulo}\n"
            f"Fecha límite vencida: {fecha_limite}\n\n"
            f"PERÍODO DE TOLERANCIA: Dispones de 7 días extras. Por favor devuelve el libro a la brevedad. Si transcurren los 7 días extras sin devolver el libro, tu cuenta será bloqueada automáticamente por incumplimiento.\n\n"
            f"---\n"
            f"{contacto}\n"
        )
        html_content = f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
  <h2 style="color: #ea580c;">Plazo Vencido — Tienes 7 Días Extras</h2>
  <p>Estimado/a <strong>{html.escape(usuario)}</strong>:</p>
  <p>Te informamos que se ha cumplido el plazo de entrega pactado para el libro:</p>
  <ul>
    <li><strong>Libro:</strong> {html.escape(titulo)}</li>
    <li><strong>Fecha límite vencida:</strong> {html.escape(str(fecha_limite))}</li>
  </ul>
  <div style="background:#fff7ed; border:1px solid #fed7aa; border-radius:6px; padding:12px; margin:16px 0; color:#9a3412;">
    <strong>PERÍODO DE TOLERANCIA: Dispones de 7 días extras.</strong><br>
    Por favor devuelve el libro a la brevedad. Si transcurren los 7 días extras sin devolver el libro, tu cuenta será <strong>bloqueada automáticamente</strong> por incumplimiento.
  </div>
  <hr style="border: 0; border-top: 1px solid #ddd; margin: 20px 0;">
  <p style="font-size: 0.85em; color: #7f8c8d;">{html.escape(contacto)}</p>
</body>
</html>"""

    # 4. BLOQUEO_POR_INCUMPLIMIENTO: pasaron los 7 días extras y no devolvió
    elif tipo_norm == "BLOQUEO_POR_INCUMPLIMIENTO":
        asunto_def = f"Biblioteca: Cuenta Bloqueada por Incumplimiento ({titulo})"
        texto_plano = (
            f"Estimado/a {usuario}:\n\n"
            f"Han transcurrido los 7 días extras de prórroga y aún NO has registrado la entrega del libro:\n\n"
            f"Libro: {titulo}\n"
            f"Fecha límite vencida: {fecha_limite}\n\n"
            f"SANCIÓN APLICADA: CUENTA BLOQUEADA POR INCUMPLIMIENTO. Tu cuenta ha sido deshabilitada. No podrás solicitar ningún préstamo hasta presentarte en la biblioteca, devolver el ejemplar y regularizar tu situación.\n\n"
            f"---\n"
            f"{contacto}\n"
        )
        html_content = f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
  <h2 style="color: #dc2626;">Cuenta Bloqueada por Incumplimiento</h2>
  <p>Estimado/a <strong>{html.escape(usuario)}</strong>:</p>
  <p>Han transcurrido los 7 días extras de prórroga y aún NO has registrado la entrega del libro:</p>
  <ul>
    <li><strong>Libro:</strong> {html.escape(titulo)}</li>
    <li><strong>Fecha límite vencida:</strong> {html.escape(str(fecha_limite))}</li>
  </ul>
  <div style="background:#fef2f2; border:1px solid #fecaca; border-radius:6px; padding:14px; margin:16px 0; color:#991b1b;">
    <strong>SANCIÓN APLICADA: CUENTA BLOQUEADA POR INCUMPLIMIENTO.</strong><br>
    Tu cuenta ha sido deshabilitada. No podrás solicitar ningún préstamo hasta presentarte en la biblioteca, devolver el ejemplar y regularizar tu situación.
  </div>
  <hr style="border: 0; border-top: 1px solid #ddd; margin: 20px 0;">
  <p style="font-size: 0.85em; color: #7f8c8d;">{html.escape(contacto)}</p>
</body>
</html>"""

    # 5. DEVOLUCION_CONFIRMADA: devolvió a tiempo
    elif tipo_norm == "DEVOLUCION_CONFIRMADA":
        asunto_def = f"Biblioteca: Devolución Confirmada (A tiempo) - {titulo}"
        texto_plano = (
            f"Estimado/a {usuario}:\n\n"
            f"Confirmamos la recepción satisfactoria de tu libro:\n"
            f"- Libro: {titulo}\n"
            f"- Fecha de entrega: {fecha_devolucion}\n"
            f"- Estado: Puntual / A tiempo (Sin sanciones)\n\n"
            f"¡Muchas gracias por devolver la obra a tiempo y contribuir al cuidado de la biblioteca!\n\n"
            f"---\n"
            f"{contacto}\n"
        )
        html_content = f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
  <h2 style="color: #16a34a;">Devolución Confirmada (A Tiempo)</h2>
  <p>Estimado/a <strong>{html.escape(usuario)}</strong>:</p>
  <p>Confirmamos que se ha recibido la devolución de tu libro dentro del plazo:</p>
  <ul>
    <li><strong>Libro:</strong> {html.escape(titulo)}</li>
    <li><strong>Fecha de recepción:</strong> {html.escape(str(fecha_devolucion))}</li>
    <li><strong>Estado:</strong> A tiempo (Sin sanciones)</li>
  </ul>
  <p style="color:#15803d; font-weight:bold;">¡Agradecemos tu puntualidad y responsabilidad!</p>
  <hr style="border: 0; border-top: 1px solid #ddd; margin: 20px 0;">
  <p style="font-size: 0.85em; color: #7f8c8d;">{html.escape(contacto)}</p>
</body>
</html>"""

    # 6. DEVOLUCION_TARDIA_1: devolvió en los 7 días extras, primera vez (advertencia)
    elif tipo_norm == "DEVOLUCION_TARDIA_1":
        asunto_def = f"Biblioteca: Devolución Tardía (1ª Advertencia) - {titulo}"
        monto_str = f"Bs. {float(monto):.2f}" if monto is not None and float(monto) > 0 else "Sin multa"
        texto_plano = (
            f"Estimado/a {usuario}:\n\n"
            f"Confirmamos la recepción de tu libro entregado dentro de los 7 días extras de tolerancia:\n"
            f"- Libro: {titulo}\n"
            f"- Fecha de recepción: {fecha_devolucion}\n"
            f"- Días de retraso: {dias_retraso or 1}\n"
            f"- Multa generada: {monto_str}\n\n"
            f"AVISO DISCIPLINARIO (1ª ADVERTENCIA):\n"
            f"Esta es tu 1ª devolución tardía registrada. Recuerda que a la 3ª devolución tardía tu cuenta será bloqueada por reincidencia.\n\n"
            f"---\n"
            f"{contacto}\n"
        )
        html_content = f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
  <h2 style="color: #b45309;">Devolución Tardía (1ª Advertencia)</h2>
  <p>Estimado/a <strong>{html.escape(usuario)}</strong>:</p>
  <p>Se ha registrado la recepción de tu libro dentro de los 7 días extras:</p>
  <ul>
    <li><strong>Libro:</strong> {html.escape(titulo)}</li>
    <li><strong>Fecha de entrega:</strong> {html.escape(str(fecha_devolucion))}</li>
    <li><strong>Días de retraso:</strong> {html.escape(str(dias_retraso or 1))}</li>
    <li><strong>Multa:</strong> {html.escape(monto_str)}</li>
  </ul>
  <div style="background:#fefce8; border:1px solid #fef08a; border-radius:6px; padding:12px; margin:16px 0; color:#854d0e;">
    <strong>1ª Advertencia Registrada:</strong><br>
    Has devuelto el ejemplar con retraso. Recuerda entregar puntualmente en tus próximos préstamos: acumular 3 devoluciones tardías causará el bloqueo de tu cuenta.
  </div>
  <hr style="border: 0; border-top: 1px solid #ddd; margin: 20px 0;">
  <p style="font-size: 0.85em; color: #7f8c8d;">{html.escape(contacto)}</p>
</body>
</html>"""

    # 7. DEVOLUCION_TARDIA_2: segunda vez (última advertencia)
    elif tipo_norm == "DEVOLUCION_TARDIA_2":
        asunto_def = f"Biblioteca: Devolución Tardía (ÚLTIMA ADVERTENCIA) - {titulo}"
        monto_str = f"Bs. {float(monto):.2f}" if monto is not None and float(monto) > 0 else "Sin multa"
        texto_plano = (
            f"Estimado/a {usuario}:\n\n"
            f"Confirmamos la recepción de tu libro entregado con retraso:\n"
            f"- Libro: {titulo}\n"
            f"- Fecha de recepción: {fecha_devolucion}\n"
            f"- Días de retraso: {dias_retraso or 1}\n"
            f"- Multa generada: {monto_str}\n\n"
            f"ALERTA CRÍTICA (ÚLTIMA ADVERTENCIA):\n"
            f"Esta es tu 2ª devolución tardía. Si incurres en una 3ª entrega tardía, tu cuenta será BLOQUEADA POR REINCIDENCIA de manera automática.\n\n"
            f"---\n"
            f"{contacto}\n"
        )
        html_content = f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
  <h2 style="color: #c2410c;">Devolución Tardía (Última Advertencia)</h2>
  <p>Estimado/a <strong>{html.escape(usuario)}</strong>:</p>
  <p>Se ha registrado la entrega de tu libro con retraso:</p>
  <ul>
    <li><strong>Libro:</strong> {html.escape(titulo)}</li>
    <li><strong>Fecha de entrega:</strong> {html.escape(str(fecha_devolucion))}</li>
    <li><strong>Días de retraso:</strong> {html.escape(str(dias_retraso or 1))}</li>
    <li><strong>Multa:</strong> {html.escape(monto_str)}</li>
  </ul>
  <div style="background:#fff7ed; border:1px solid #ffedd5; border-radius:6px; padding:12px; margin:16px 0; color:#9a3412;">
    <strong>ÚLTIMA ADVERTENCIA (2ª Devolución Tardía):</strong><br>
    Has acumulado 2 entregas con retraso. Si vuelves a entregar tarde por 3ª vez, tu cuenta será suspendida definitivamente por reincidencia.
  </div>
  <hr style="border: 0; border-top: 1px solid #ddd; margin: 20px 0;">
  <p style="font-size: 0.85em; color: #7f8c8d;">{html.escape(contacto)}</p>
</body>
</html>"""

    # 8. BLOQUEO_POR_REINCIDENCIA: tercera tardía, se bloquea
    elif tipo_norm == "BLOQUEO_POR_REINCIDENCIA":
        asunto_def = f"Biblioteca: Cuenta Bloqueada por Reincidencia ({titulo})"
        texto_plano = (
            f"Estimado/a {usuario}:\n\n"
            f"Se ha recibido la devolución del libro con retraso acumulado:\n\n"
            f"Libro: {titulo}\n"
            f"Fecha de entrega: {fecha_devolucion}\n\n\n"
            f"BLOQUEO POR REINCIDENCIA (3 Devoluciones Tardías): Has alcanzado el límite de 3 devoluciones fuera de plazo. De acuerdo al reglamento, tu cuenta ha sido BLOQUEADA POR REINCIDENCIA. Debes presentarte con administración bibliotecaria para regularizar tu situación.\n\n"
            f"---\n"
            f"{contacto}\n"
        )
        html_content = f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
  <h2 style="color: #991b1b;">Cuenta Bloqueada por Reincidencia</h2>
  <p>Estimado/a <strong>{html.escape(usuario)}</strong>:</p>
  <p>Se ha recibido la devolución del libro con retraso acumulado:</p>
  <ul>
    <li><strong>Libro:</strong> {html.escape(titulo)}</li>
    <li><strong>Fecha de entrega:</strong> {html.escape(str(fecha_devolucion))}</li>
  </ul>
  <div style="background:#fef2f2; border:1px solid #fecaca; border-radius:6px; padding:14px; margin:16px 0; color:#7f1d1d;">
    <strong>BLOQUEO POR REINCIDENCIA (3 Devoluciones Tardías):</strong><br>
    Has alcanzado el límite de 3 devoluciones fuera de plazo. De acuerdo al reglamento, tu cuenta ha sido <strong>BLOQUEADA POR REINCIDENCIA</strong>. Debes presentarte con administración bibliotecaria para regularizar tu situación.
  </div>
  <hr style="border: 0; border-top: 1px solid #ddd; margin: 20px 0;">
  <p style="font-size: 0.85em; color: #7f8c8d;">{html.escape(contacto)}</p>
</body>
</html>"""

    # 9. DEVOLUCION_CRITICA: devolvió estando ya bloqueado
    elif tipo_norm in ("DEVOLUCION_CRITICA", "MULTA"):
        asunto_def = f"Biblioteca: Devolución Crítica Registrada ({titulo})"
        texto_plano = (
            f"Estimado/a {usuario}:\n\n"
            f"Se ha recibido y registrado el ejemplar que se encontraba con bloqueo activo:\n\n"
            f"Libro: {titulo}\n"
            f"Fecha de recepción: {fecha_devolucion}\n\n\n"
            f"DEVOLUCIÓN CRÍTICA EN ESTADO BLOQUEADO: El ejemplar ha sido recuperado e inventariado en el catálogo.\n\n"
            f"---\n"
            f"{contacto}\n"
        )
        html_content = f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
  <h2 style="color: #701a75;">Devolución Crítica Registrada</h2>
  <p>Estimado/a <strong>{html.escape(usuario)}</strong>:</p>
  <p>Se ha recibido y registrado el ejemplar que se encontraba con bloqueo activo:</p>
  <ul>
    <li><strong>Libro:</strong> {html.escape(titulo)}</li>
    <li><strong>Fecha de recepción:</strong> {html.escape(str(fecha_devolucion))}</li>
  </ul>
  <div style="background:#fdf4ff; border:1px solid #f5d0fe; border-radius:6px; padding:12px; margin:16px 0; color:#86198f;">
    <strong>DEVOLUCIÓN CRÍTICA EN ESTADO BLOQUEADO:</strong><br>
    El ejemplar ha sido recuperado e inventariado en el catálogo.
  </div>
  <hr style="border: 0; border-top: 1px solid #ddd; margin: 20px 0;">
  <p style="font-size: 0.85em; color: #7f8c8d;">{html.escape(contacto)}</p>
</body>
</html>"""

    else:
        asunto_def = f"Biblioteca: Notificación del sistema - {tipo_norm}"
        texto_plano = (
            f"Estimado/a {usuario}:\n\n"
            f"{mensaje if mensaje else 'Notificación de la Biblioteca.'}\n\n"
            f"---\n"
            f"{contacto}\n"
        )
        html_content = f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
  <h2 style="color: #2c3e50;">Notificación del Sistema</h2>
  <p>Estimado/a <strong>{html.escape(usuario)}</strong>:</p>
  <p>{html.escape(mensaje if mensaje else 'Notificación de la Biblioteca.')}</p>
  <hr style="border: 0; border-top: 1px solid #ddd; margin: 20px 0;">
  <p style="font-size: 0.85em; color: #7f8c8d;">{html.escape(contacto)}</p>
</body>
</html>"""

    asunto_base = (asunto or "").strip() or asunto_def
    asunto_final = re.sub(r'[\r\n]+', ' ', asunto_base).strip()

    return asunto_final, texto_plano.strip(), html_content

def enviar_correo(correo_destino: str, asunto: str, texto_plano: str, html_content: str):
    """Envía un correo electrónico multipart (texto plano + HTML) mediante smtplib."""
    if not correo_destino or "@" not in correo_destino:
        raise ValueError("Correo destino no válido")

    # Lectura segura con 'os.getenv(...) or valor_por_defecto' para tolerar variables vacías
    host = os.getenv("SMTP_HOST") or "mailpit"
    port = int(os.getenv("SMTP_PORT") or 1025)
    user = (os.getenv("SMTP_USER") or "").strip()
    password = (os.getenv("SMTP_PASSWORD") or "").strip()
    timeout = float(os.getenv("SMTP_TIMEOUT") or 10)
    mode = (os.getenv("SMTP_MODE") or "none").strip().lower()

    mail_from = os.getenv("MAIL_FROM") or "biblioteca@example.com"
    mail_from_name = os.getenv("MAIL_FROM_NAME") or "Sistema Biblioteca"

    msg = EmailMessage()
    msg['Subject'] = asunto
    if mail_from_name:
        msg['From'] = f"{mail_from_name} <{mail_from}>"
    else:
        msg['From'] = mail_from
    msg['To'] = correo_destino

    # Encabezados Date y Message-ID
    msg['Date'] = email.utils.formatdate(localtime=True)
    msg['Message-ID'] = email.utils.make_msgid()

    msg.set_content(texto_plano)
    msg.add_alternative(html_content, subtype='html')

    context = ssl.create_default_context()

    if mode == "ssl":
        with smtplib.SMTP_SSL(host, port, timeout=timeout, context=context) as server:
            if user and password:
                server.login(user, password)
            server.send_message(msg)
    elif mode == "starttls":
        with smtplib.SMTP(host, port, timeout=timeout) as server:
            server.starttls(context=context)
            if user and password:
                server.login(user, password)
            server.send_message(msg)
    else:  # "none"
        with smtplib.SMTP(host, port, timeout=timeout) as server:
            if user and password:
                server.login(user, password)
            server.send_message(msg)
