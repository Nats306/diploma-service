# Imagen liviana para el servicio de generacion de diplomas (PDF).
# Pensada para correr en OpenShift: no asume un UID fijo (OpenShift le
# asigna uno arbitrario al arrancar el pod bajo la SCC "restricted"),
# no escribe nada a disco fuera de /tmp, y no necesita puertos < 1024.

FROM python:3.11-slim

WORKDIR /app

# Dependencias del sistema para 'cryptography' (PyJWT las usa para RS256)
RUN apt-get update \
    && apt-get install -y --no-install-recommends gcc libffi-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py cognito_auth.py db.py diploma_render.py ./
COPY fonts ./fonts

# Directorio home escribible por el grupo (OpenShift corre con GID 0)
RUN mkdir -p /app/.cache && chgrp -R 0 /app && chmod -R g=u /app

ENV PORT=8080
EXPOSE 8080

# UID no-root explicito para docker/K8s normales; en OpenShift esto se
# ignora y se reemplaza por un UID aleatorio del rango del namespace,
# lo cual esta bien porque nada aqui depende de un UID especifico.
USER 1001

CMD ["gunicorn", "app:app", "--bind", "0.0.0.0:8080", "--workers", "2", "--threads", "2", "--timeout", "30"]
