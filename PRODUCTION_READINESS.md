# 🚀 Checklist de Producción — RestoMind

Este documento es independiente del proveedor de hosting: sirve igual si
terminás en un VPS con Nginx, Railway, Render, o cualquier otro. Repásalo
antes de apuntar un dominio real a esta app con datos de clientes reales.

**¿Desplegando en un VPS Ubuntu con Nginx?** → los pasos concretos, con
scripts listos, están en [`deploy/RUNBOOK.md`](deploy/RUNBOOK.md). Este
documento es el checklist de fondo (qué necesita la app, sea cual sea el
hosting); el runbook es la receta paso a paso para ese caso específico.

**Contraseña mínima:** queda intencionalmente en 6 caracteres por ahora
(decisión explícita del dueño del proyecto para acelerar su propio QA).
Subir ese mínimo es la única pieza de seguridad de login pendiente — el
resto de este documento sí está aplicado en el código.

---

## ✅ Ya resuelto en el código (no requiere acción)

Estos puntos hacen que la app **directamente no arranque** si falta algo:

- [x] `SECRET_KEY` obligatorio — sin valor por defecto inseguro (`backend/config.py`)
- [x] En `ENVIRONMENT=production`, la app rechaza arrancar si:
  - `DEBUG=true` (expondría stack traces con detalles internos)
  - `CORS_ORIGINS` sigue en los valores de desarrollo (`localhost`) o es `"*"`
- [x] Tokens JWT con tipo explícito (`tipo: "usuario"` / `"superadmin"`)
- [x] Rate limiting en los 3 endpoints de login (5 fallos / 15 min → 429)
- [x] Auditoría persistente de login y acciones sensibles (tabla `audit_log`)
- [x] Contraseñas con bcrypt, nunca plaintext
- [x] Cabeceras de seguridad en toda respuesta (`backend/middleware.py`):
  `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`,
  `Content-Security-Policy`, y `Strict-Transport-Security` cuando detecta HTTPS
- [x] `requirements.txt` verificado contra un venv limpio (no solo el de
  desarrollo) — corría fastapi/starlette años desactualizados con dos CVEs
  de denegación de servicio conocidas en `python-multipart`. Ver commit
  `89c7ef8`. **Repetir esta verificación cada vez que se actualice una
  dependencia**: `python -m venv /tmp/venv_check && /tmp/venv_check/bin/pip
  install -r requirements.txt && /tmp/venv_check/bin/pytest -q` — que pasen
  los tests en el venv de desarrollo no prueba que `requirements.txt` esté
  al día.
- [x] La app no siembra el restaurante/admin de prueba (`admin@lamarisqueria.pe`
  / `admin123`, contraseña pública en `backend/seed.py`) cuando
  `ENVIRONMENT=production`
- [x] SQLite en modo WAL (`backend/database.py`) — lectores y escritor no se
  bloquean entre sí; se activa solo, sin configuración

## ⚙️ Variables de entorno que SÍ tenés que cambiar

Copiá `.env.example` a `.env` en el servidor de producción y ajustá:

```bash
ENVIRONMENT=production
DEBUG=false

# Generar uno nuevo, distinto al de desarrollo:
# python -c "import secrets; print(secrets.token_urlsafe(48))"
SECRET_KEY=<valor generado, secreto, no compartido con desarrollo>

# El dominio REAL donde va a vivir el frontend. Sin esto la app no arranca.
CORS_ORIGINS=["https://app.turestaurante.com"]

DATABASE_URL=sqlite:///./restomind.db   # o Postgres si migras de SQLite
```

**Nunca subas `.env` a git.** Verificá que esté en `.gitignore` (ya lo está)
y que el `SECRET_KEY` de producción no sea el mismo que usás en tu máquina
para desarrollar.

## 🔒 Lo que tiene que resolver el servidor/proxy, no el código

Esta app corre en Uvicorn plano (HTTP). El certificado TLS y el redirect a
HTTPS los pone lo que esté delante — Nginx, Caddy, o el balanceador del
proveedor de hosting que elijas. Sea cual sea:

1. **HTTPS obligatorio.** Sin esto, el JWT viaja en texto plano por la red
   (cualquiera en el mismo WiFi puede leerlo) y ningún header de seguridad
   de esta app importa.
2. **Redirect HTTP → HTTPS** (puerto 80 solo redirige, no sirve contenido).
3. **Reenviar el header `X-Forwarded-Proto`** al backend — el middleware de
   seguridad (`backend/middleware.py`) lo usa para saber si activar
   `Strict-Transport-Security`; sin ese header, esa cabecera nunca se manda
   aunque el sitio ya esté en HTTPS.

Ejemplo mínimo de proxy con Nginx (ajustar rutas/dominio):

```nginx
server {
    listen 80;
    server_name app.turestaurante.com;
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl;
    server_name app.turestaurante.com;

    ssl_certificate     /etc/letsencrypt/live/app.turestaurante.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/app.turestaurante.com/privkey.pem;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header Host $host;
    }
}
```

Certificado gratis con [Let's Encrypt](https://letsencrypt.org/) / certbot.
Si el hosting es Railway/Render/Fly.io, el HTTPS ya viene incluido por
defecto — solo hay que confirmar que reenvían `X-Forwarded-Proto` (casi
todos lo hacen de forma automática).

## ⚠️ Limitaciones conocidas que quedan para más adelante

No bloquean un primer despliegue en producción con tráfico moderado, pero
hay que tenerlas presentes:

- **Rate limiting en memoria** (`backend/utils/rate_limit.py`): vive en el
  proceso de un solo worker Uvicorn. Si el día de mañana el servidor corre
  con varios workers o varias instancias detrás de un balanceador, cada uno
  lleva su propio contador — el límite efectivo de "5 fallos" se vuelve
  "5 fallos × cantidad de workers". Migrar a algo compartido (Redis) si se
  escala a más de un proceso.
- **Sin revocación de tokens.** Un logout borra el token del navegador, pero
  el JWT sigue siendo válido en el servidor hasta que expira (12 horas). Si
  se necesita invalidar sesiones activas antes de eso (empleado despedido a
  mitad de turno, sospecha de token robado), hoy no hay forma — requeriría
  una lista de tokens revocados o pasar a sesiones con estado.
- **Contraseña mínima de 6 caracteres** — deferido a propósito, ver arriba.

## 📋 Checklist final antes de apuntar el dominio real

- [ ] `.env` de producción con `SECRET_KEY` propio (no el de dev), `ENVIRONMENT=production`, `DEBUG=false`
- [ ] `CORS_ORIGINS` apuntando al dominio real del frontend
- [ ] Proxy/hosting con HTTPS activo y redirect desde HTTP
- [ ] Proxy reenviando `X-Forwarded-Proto`
- [ ] Backup de la base de datos configurado (SQLite: copiar el archivo `.db`; si migras a Postgres, backup automático del proveedor)
- [ ] Confirmar que `.env` y `restomind.db` no están en el repo git público
