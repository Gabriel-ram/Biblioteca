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
    """Genera asunto, texto plano y HTML autosuficientes según el tipo de notificación."""
    # Comprobar que datos sea un dict
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

    titulo = datos.get("titulo") or datos.get("libro_titulo") or "Libro del catálogo"
    fecha_limite = datos.get("fecha_limite") or "Consultar en el sistema"
    monto = datos.get("monto") or datos.get("monto_multa")
    dias_retraso = datos.get("dias_retraso")

    contacto = os.getenv("BIBLIOTECA_CONTACTO") or "Biblioteca Central — contacto@biblioteca.example.com"
    tipo_norm = (tipo or "").strip().upper()

    if tipo_norm == "PRESTAMO":
        asunto_def = f"Biblioteca: Préstamo registrado - {titulo}"
        texto_plano = (
            f"Estimado/a {usuario}:\n\n"
            f"Confirmamos el registro de tu préstamo del libro:\n"
            f"- Título: {titulo}\n"
            f"- Fecha límite de devolución: {fecha_limite}\n\n"
            f"{mensaje if mensaje else ''}\n\n"
            f"---\n"
            f"{contacto}\n"
        )
        html_content = f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
  <h2 style="color: #2c3e50;">Confirmación de Préstamo</h2>
  <p>Estimado/a <strong>{html.escape(usuario)}</strong>:</p>
  <p>Confirmamos el registro de tu préstamo:</p>
  <ul>
    <li><strong>Libro:</strong> {html.escape(titulo)}</li>
    <li><strong>Fecha límite de devolución:</strong> {html.escape(fecha_limite)}</li>
  </ul>
  {f"<p>{html.escape(mensaje)}</p>" if mensaje else ""}
  <hr style="border: 0; border-top: 1px solid #ddd; margin: 20px 0;">
  <p style="font-size: 0.85em; color: #7f8c8d;">{html.escape(contacto)}</p>
</body>
</html>"""

    elif tipo_norm == "POR_VENCER":
        asunto_def = f"Biblioteca: Recordatorio de vencimiento - {titulo}"
        texto_plano = (
            f"Estimado/a {usuario}:\n\n"
            f"Te recordamos que tu préstamo está próximo a vencer:\n"
            f"- Título: {titulo}\n"
            f"- Fecha límite de devolución: {fecha_limite}\n\n"
            f"{mensaje if mensaje else 'Por favor realiza la devolución a tiempo para evitar multas.'}\n\n"
            f"---\n"
            f"{contacto}\n"
        )
        html_content = f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
  <h2 style="color: #d35400;">Recordatorio de Vencimiento</h2>
  <p>Estimado/a <strong>{html.escape(usuario)}</strong>:</p>
  <p>Te recordamos que tu préstamo está próximo a vencer:</p>
  <ul>
    <li><strong>Libro:</strong> {html.escape(titulo)}</li>
    <li><strong>Fecha límite de devolución:</strong> {html.escape(fecha_limite)}</li>
  </ul>
  {f"<p>{html.escape(mensaje)}</p>" if mensaje else "<p>Por favor realiza la devolución a tiempo para evitar multas.</p>"}
  <hr style="border: 0; border-top: 1px solid #ddd; margin: 20px 0;">
  <p style="font-size: 0.85em; color: #7f8c8d;">{html.escape(contacto)}</p>
</body>
</html>"""

    elif tipo_norm == "MULTA":
        asunto_def = "Biblioteca: Notificación de multa por devolución tardía"
        monto_str = f"${float(monto):.2f}" if monto is not None else "Consultar en el sistema"
        dias_str = f"- Días de retraso: {dias_retraso}\n" if dias_retraso else ""
        dias_html = f"<li><strong>Días de retraso:</strong> {html.escape(str(dias_retraso))}</li>" if dias_retraso else ""

        texto_plano = (
            f"Estimado/a {usuario}:\n\n"
            f"Se ha registrado una multa por retraso en la devolución de tu préstamo:\n"
            f"- Libro: {titulo}\n"
            f"- Monto de la multa: {monto_str}\n"
            f"{dias_str}\n"
            f"{mensaje if mensaje else 'Por favor acércate a la biblioteca para regularizar tu situación.'}\n\n"
            f"---\n"
            f"{contacto}\n"
        )
        html_content = f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
  <h2 style="color: #c0392b;">Notificación de Multa</h2>
  <p>Estimado/a <strong>{html.escape(usuario)}</strong>:</p>
  <p>Se ha registrado una multa por retraso en la devolución de tu préstamo:</p>
  <ul>
    <li><strong>Libro:</strong> {html.escape(titulo)}</li>
    <li><strong>Monto de la multa:</strong> {html.escape(monto_str)}</li>
    {dias_html}
  </ul>
  {f"<p>{html.escape(mensaje)}</p>" if mensaje else "<p>Por favor acércate a la biblioteca para regularizar tu situación.</p>"}
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
    # Reemplazar saltos de línea del asunto por espacios
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
