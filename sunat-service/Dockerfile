# Micro-servicio de emisión SUNAT.
#
# Imagen aparte de RestoMind para que su cryptography<45 no toque la del
# backend (ver requirements.txt de esta misma carpeta).

FROM python:3.12-slim

# lxml y cryptography traen ruedas precompiladas para linux/amd64, así que no
# hace falta compilador. Si el VPS fuera ARM habría que agregar build-essential
# y libxml2-dev aquí.
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py .

# No corre como root: si alguien logra ejecutar algo dentro del contenedor,
# que no sea con todos los permisos sobre el volumen de certificados.
RUN useradd --create-home --uid 10001 sunat && chown -R sunat:sunat /app
USER sunat

EXPOSE 8000

# Un solo worker a propósito: emitir es una llamada bloqueante a SUNAT y el
# cuello de botella es su tiempo de respuesta, no la CPU. Más workers en un
# VPS de 2 GB solo consumen memoria.
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
