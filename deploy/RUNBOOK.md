# Runbook — VPS OpenClaw, Ubuntu 24.04, Miami

Pasos concretos para este servidor específico. Para el checklist genérico
de qué necesita cualquier despliegue (independiente del hosting), ver
[`PRODUCTION_READINESS.md`](../PRODUCTION_READINESS.md).

---

## ⚠️ Antes de empezar: facturación SUNAT

Si vas a emitir boletas electrónicas desde este VPS, primero decidí esto —
no es un paso de infraestructura, es una decisión de negocio:

`emisor_facturacion=sfs_local` (el modo gratis) depende de que el
Facturador SUNAT corra en la **misma máquina** que RestoMind, vigilando una
carpeta local. Un VPS en la nube no tiene eso. Si vas a facturar en vivo
desde acá, tenés que cambiar `EMISOR_FACTURACION=facturacion_pe` en el
`.env` (integración por API, S/ 0.20/boleta, ya implementada). Si preferís
seguir con el modo gratis, el Facturador tiene que seguir corriendo en una
PC del restaurante — este VPS no reemplaza esa pieza.

---

## 0. Al aprovisionar el VPS: elegir Ubuntu Server 24.04 LTS

Esto se decide UNA vez y no se cambia después sin reinstalar, así que
conviene no equivocarse:

- **Python 3.12 de fábrica**, el mismo que se usa para desarrollar. Sin él
  habría que instalar el intérprete desde un PPA externo (deadsnakes), una
  dependencia más en el arranque de cada servidor.
- **Parches de seguridad hasta abril de 2029.** El soporte estándar de
  20.04 terminó en abril de 2025: un servidor con datos financieros de
  clientes no debería correr sin parches.
- Elegir la variante **"Server ... Minimal"**, no "Cloud Micro": menos
  paquetes instalados (menos superficie de ataque) pero conserva lo básico;
  las imágenes ultra-recortadas a veces vienen sin `curl` ni `sudo`.

Con 2 GB de RAM alcanza y sobra para esta app: RestoMind consume ~200 MB,
Nginx ~20 MB y el sistema ~400 MB.

## 1. Bootstrap del servidor (una sola vez)

```bash
# Desde tu máquina, subí el script:
scp deploy/setup_vps.sh root@TU_IP:~/

# Conectate y corré:
ssh root@TU_IP
REPO_URL="https://github.com/tu-usuario/RestoMind-SaaS.git" bash setup_vps.sh
```

Esto instala Python (el 3.12 nativo de 24.04, sin PPAs externos), Nginx,
certbot, configura el firewall (ufw),
crea el usuario `restomind` sin privilegios, clona el repo, arma el
entorno virtual e instala dependencias, y prepara `/home/restomind/app/.env`
con placeholders `TODO_*`.

## 2. Completar el `.env` de producción

```bash
sudo -u restomind nano /home/restomind/app/.env
```

Como mínimo:

```bash
ENVIRONMENT=production
DEBUG=false

# Generar UNO NUEVO, distinto al de desarrollo:
# python3 -c "import secrets; print(secrets.token_urlsafe(48))"
SECRET_KEY=<pegar acá>

# El dominio real donde va a vivir el frontend (con https://).
CORS_ORIGINS=["https://TU_DOMINIO"]

APP_URL=https://TU_DOMINIO
```

Y, si aplica en este momento: credenciales SMTP (para el correo de
bienvenida — ver `backend/email.py`, no envía nada si faltan), credenciales
de Firebase (notificaciones push a cocina — tampoco bloquea si faltan), y
`EMISOR_FACTURACION` según la decisión de la sección de arriba.

La app **se niega a arrancar** si `SECRET_KEY` falta, o si en producción
`DEBUG=true` o `CORS_ORIGINS` sigue en los valores de desarrollo — es a
propósito (`backend/config.py`), mejor que arranque insegura.

## 3. Arrancar el servicio

```bash
sudo systemctl start restomind
sudo systemctl status restomind      # tiene que decir "active (running)"
curl http://127.0.0.1:8000/health    # {"status":"ok",...}
```

Si algo falla: `journalctl -u restomind -n 100 --no-pager`.

## 4. DNS

En el panel de tu dominio (`jtechautomatizacion.com.pe` o el que hayas
elegido), un registro **A** apuntando el subdominio elegido a la IP del
VPS. Ejemplo:

```
Tipo: A
Nombre: app          (para app.jtechautomatizacion.com.pe)
Valor: <IP del VPS>
TTL: 300 (o el mínimo que permita tu proveedor)
```

Esperá a que propague (`dig app.jtechautomatizacion.com.pe` desde tu PC
tiene que devolver la IP del VPS) antes del paso siguiente — certbot no
puede emitir el certificado si el dominio todavía no resuelve a este
servidor.

## 5. Nginx + HTTPS

```bash
sudo cp deploy/nginx.conf.template /etc/nginx/sites-available/restomind
sudo sed -i 's/TU_DOMINIO/app.jtechautomatizacion.com.pe/g' /etc/nginx/sites-available/restomind
sudo ln -s /etc/nginx/sites-available/restomind /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default   # el sitio de bienvenida de Nginx, ya no hace falta
sudo nginx -t                                  # valida sintaxis antes de recargar
sudo systemctl reload nginx

sudo certbot --nginx -d app.jtechautomatizacion.com.pe
```

Certbot pide un email de contacto (avisos de renovación) y modifica el
archivo de Nginx solo para agregar el bloque HTTPS + el redirect desde
HTTP. La renovación queda automática (systemd timer que certbot instala
solo — `systemctl list-timers | grep certbot` para confirmarlo).

## 6. Verificación final

```bash
curl -I https://app.jtechautomatizacion.com.pe/health
```

Tiene que devolver `200` y, entre las cabeceras, `strict-transport-security`
— si no aparece, revisá que Nginx esté mandando `X-Forwarded-Proto`
(está en el template, pero confirmá que no se haya perdido en el `sed`).

Abrí `https://app.jtechautomatizacion.com.pe/static/index.html` en el
navegador y probá un login real.

## 7. Backups automáticos

```bash
sudo -u restomind crontab -e
```

Agregar:

```
0 3 * * * /home/restomind/app/deploy/backup_db.sh >> /home/restomind/backups/backup.log 2>&1
```

Corré `deploy/backup_db.sh` una vez a mano para confirmar que funciona
antes de dejarlo en cron.

---

## Actualizar producción (a partir de acá, cada vez)

```bash
ssh restomind@TU_IP
cd ~/app
bash deploy/deploy.sh
```

`git pull` + reinstala dependencias si cambiaron + reinicia el servicio +
confirma que `/health` responde.

## Comandos útiles

```bash
journalctl -u restomind -f              # logs en vivo
sudo systemctl restart restomind        # reiniciar manualmente
sudo systemctl status restomind         # estado actual
sudo nginx -t                           # validar config de Nginx antes de recargar
sudo certbot renew --dry-run            # probar la renovación sin gastar cuota real
```
