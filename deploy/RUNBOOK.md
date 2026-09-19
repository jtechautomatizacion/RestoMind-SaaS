# Runbook — VPS OpenClaw, Ubuntu 24.04, Miami

Pasos concretos para este servidor específico. Para el checklist genérico
de qué necesita cualquier despliegue (independiente del hosting), ver
[`PRODUCTION_READINESS.md`](../PRODUCTION_READINESS.md).

---

## ⚠️ Antes de empezar: esto NO se despliega por FTP

El código llega al servidor con `git clone`, no arrastrando carpetas con
FileZilla. No es preferencia de estilo — arrastrar el proyecto **no
funciona**:

- `venv/` son ~12.400 archivos con rutas absolutas de Windows adentro. En
  Linux no ejecuta; hay que recrearlo con `python3 -m venv` en el servidor.
- `.env` de desarrollo tiene el `SECRET_KEY` de desarrollo. Subirlo firma
  los JWT de producción con un secreto que ya circuló.
- `restomind.db` local trae las ventas de prueba. En producción, mentira
  contable.
- `data/sunat_padron.db` pesa 1,5 GB. Subirlo por SFTP tarda horas; se
  reconstruye en el VPS en ~25 minutos desde la fuente de SUNAT.

Con `git clone` el servidor sabe **exactamente** qué versión corre
(`git log -1`), se actualiza con un `git pull`, y se vuelve atrás con un
`git checkout` si algo sale mal. Arrastrando archivos, nada de eso existe.

**Dónde SÍ sirve FileZilla**, y es imprescindible: subir el **certificado
digital** (`.pfx`) y las credenciales SOL de cada restaurante a
`certs/<cliente_id>/`. Esos archivos están en `.gitignore` a propósito —
quien los tiene puede facturar a nombre del negocio— así que git nunca los
va a llevar. También sirve para bajarte los backups fuera del VPS.

## ⚠️ Facturación SUNAT desde v4.0

Ya no hay decisión que tomar acá: `sunat_cloud` es el único emisor. El
comprobante se arma como XML UBL 2.1, se firma con el certificado del
restaurante y se envía por SOAP **desde el servidor**. No hace falta
ninguna PC con Windows en el local.

Eso sí, agrega una pieza al despliegue: el contenedor `sunat-service`
(paso 3b). Sin él el backend arranca igual, pero el primer cobro con
boleta falla con `SunatCloudError`.

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

# Token compartido entre RestoMind y el contenedor sunat-service.
# Generar OTRO NUEVO, distinto al de desarrollo:
# python3 -c "import secrets; print(secrets.token_urlsafe(32))"
SUNAT_SERVICE_TOKEN=<pegar acá>
SUNAT_SERVICE_URL=http://127.0.0.1:8100
```

`SUNAT_SERVICE_TOKEN` vacío no impide arrancar: el error aparece recién en
el primer cobro con boleta. Completalo ahora y no dentro de tres semanas
con un comensal esperando el comprobante.

### Correo de bienvenida (opcional, pero falla en silencio)

**Primero averiguá dónde vive la casilla.** La dirección no lo dice — lo
dice el MX del dominio:

```bash
dig +short MX tuempresa.com
```

| El MX apunta a… | `SMTP_HOST` | La contraseña es… |
|---|---|---|
| `google.com` | `smtp.gmail.com` | una *Contraseña de aplicación* de 16 caracteres |
| el propio dominio | `mail.tuempresa.com` | la de la casilla, la de cPanel > Cuentas de correo |

Esto ya costó un rato en producción: una dirección del dominio propio
(`facturacion@tuempresa.com`) apuntando a `smtp.gmail.com` devuelve
`535 Username and Password not accepted`, que **parece** una contraseña mal
escrita. No lo es: Gmail se niega a autenticar un usuario que no es suyo.
Una contraseña de aplicación de Gmail tampoco sirve contra un cPanel — son
sistemas distintos.

```bash
SMTP_HOST=mail.tuempresa.com      # o smtp.gmail.com, según la tabla
SMTP_PORT=587
SMTP_USER=micasilla@tuempresa.com
SMTP_PASSWORD=<la que corresponda según la tabla>
SMTP_FROM_EMAIL=micasilla@tuempresa.com
```

Probá la combinación **antes** de dar de alta un restaurante real:

```bash
cd /home/restomind/app
sudo -u restomind venv/bin/python -c "
import smtplib, ssl
s = smtplib.SMTP('TU_HOST', 587, timeout=15)
s.starttls(context=ssl.create_default_context())
s.login('TU_USUARIO', 'TU_CLAVE')
print('LOGIN OK'); s.quit()"
```

Sin esto, dar de alta un restaurante funciona igual pero el admin **nunca
recibe su correo de acceso**, y el envío corre en segundo plano con el
resultado descartado — así que no hay error en pantalla. En producción
queda un `WARNING` en `journalctl -u restomind` para que se note.

Firebase (push a cocina) es igual de opcional: sin credenciales la app
funciona idéntica, solo que el cocinero no recibe el aviso al celular.

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

## 3b. Contenedor de emisión SUNAT

El token es **el mismo** que pusiste en `SUNAT_SERVICE_TOKEN` del `.env`:
RestoMind lo manda en cada pedido y el contenedor lo verifica. Los dos leen
el mismo archivo, así que no hay que repetirlo en ningún lado.

```bash
cd /home/restomind/app
docker compose up -d --build          # tarda unos minutos la primera vez
docker compose ps                     # "healthy"
curl -sf http://127.0.0.1:8100/health && echo OK
```

Arranca en **beta** (el ambiente de pruebas de SUNAT: no emite comprobantes
reales). Recién cuando hayas emitido una boleta de prueba de punta a punta,
pasalo a producción:

```bash
SUNAT_MODE=prod docker compose up -d
```

`SUNAT_MODE` **nunca** va en el `.env` — la lee el contenedor, no el
backend, y `Settings` rechaza toda variable que no declara: una sola línea
`SUNAT_MODE=` en ese archivo deja la app sin arrancar con
`extra_forbidden`.

### El certificado: la ruta y los permisos

Va en `certs/<cliente_id>/` — el `cliente_id` **exacto** de la tabla
`clientes`, porque el contenedor arma esa ruta con él. Si el id de
producción no es el mismo que el de tu entorno local, la carpeta copiada
tal cual no la encuentra nadie. Es el archivo que **sí** se sube con
FileZilla (ver `docs/SUNAT_SETUP.md`).

**Y los permisos importan más de lo que parece.** El contenedor corre como
`uid=10001` (fijo en `sunat-service/Dockerfile`), no como `restomind`. Un
`chmod 600` bien intencionado lo deja sin poder leer el certificado, y eso
**no falla al desplegar**: falla en el primer cobro con boleta, con un
comensal esperando.

La combinación correcta le da acceso **por grupo**, sin abrir el
certificado al resto del servidor:

```bash
chown -R restomind:10001 /home/restomind/app/certs
find /home/restomind/app/certs -type d -exec chmod 750 {} \;
find /home/restomind/app/certs -type f -exec chmod 640 {} \;
```

Verificá las dos mitades — que el contenedor lea, y que nadie más pueda:

```bash
docker exec restomind-sunat head -c 4 /app/certs/<cliente_id>/certificado.pfx \
  >/dev/null && echo "el contenedor puede leerlo"
```

`chmod 644` también haría funcionar el contenedor, pero dejaría el
certificado y la clave SOL legibles por cualquier usuario del servidor —
quien los tenga puede emitir comprobantes a nombre del restaurante.

## 3c. Padrón de RUC

Sin esto, cobrar con RUC no autocompleta la razón social. No bloquea la
venta, pero el cajero tiene que tipear el nombre a mano cada vez.

```bash
sudo -u restomind /home/restomind/app/venv/bin/python \
     -m backend.scripts.cargar_padron_sunat
```

Descarga ~374 MB de SUNAT y construye 18,4 millones de filas en ~25
minutos. Usa `temp_store=FILE`, así que no le pide RAM al servidor: podés
dejarlo corriendo mientras seguís con el resto (mejor dentro de `tmux` o
`screen`, para que no muera si se corta el SSH).

## 3d. Dejar la base limpia para producción

Si la base del VPS arrancó vacía, saltealo. Si migraste una base con la
carta ya cargada **y las ventas de prueba encima**, este paso conserva el
catálogo y borra la historia:

```bash
cd /home/restomind/app
sudo -u restomind venv/bin/python -m backend.scripts.preparar_produccion --revisar
sudo -u restomind venv/bin/python -m backend.scripts.preparar_produccion --ejecutar
```

Hace un respaldo antes de tocar nada y pide escribir `PRODUCCION` para
confirmar. Deja los correlativos en 0: sin eso la primera boleta real
saldría como B001-31 y la serie arrancaría con un hueco que SUNAT exige
que no exista.

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

Primero a mano, para confirmar que funciona antes de confiarle el respaldo
a una tarea que nadie mira:

```bash
mkdir -p /home/restomind/backups
chown restomind:restomind /home/restomind/backups
sudo -u restomind bash /home/restomind/app/deploy/backup_db.sh
```

Después, la tarea diaria. Va en `/etc/cron.d/` y **no** con `crontab -e`:
ese comando abre un editor interactivo, así que no se puede automatizar ni
correr desde un script (falla en silencio dejando el crontab vacío — pasó
en un despliegue real). Un archivo plano se escribe, se lee y se versiona:

```bash
cat > /etc/cron.d/restomind-backup <<'EOF'
# Backup diario de la base de RestoMind (3:00 AM). Ver deploy/backup_db.sh
SHELL=/bin/bash
PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
0 3 * * * restomind /home/restomind/app/deploy/backup_db.sh >> /home/restomind/backups/backup.log 2>&1
EOF

chmod 644 /etc/cron.d/restomind-backup
systemctl restart cron
```

> Ojo: en `/etc/cron.d` el **sexto campo es el usuario** (`restomind`), a
> diferencia de un crontab de usuario donde ese lugar ya es el comando.

**Esto NO es todavía un backup.** Los archivos quedan en el mismo disco que
la base: si el VPS se pierde, se pierden los dos. Bajate una copia fuera del
servidor periódicamente (FileZilla sirve) o mandala a otro lado.

---

## 8. Repartir el APK

El APK se sirve **desde el propio dominio**, no desde Google Drive. Drive
funciona, pero avisa que "no pudo analizar el archivo" y obliga a elegirlo
dentro de una carpeta: en un celular eso se lee como que la app no es
confiable, justo en el momento más delicado.

```
https://app.jtechsolutiones.com/descargas/RestoMind.apk
```

La carpeta vive en `/home/restomind/descargas/`, **fuera del checkout de
git**: así un `git pull` no la pisa y no hay un binario de 3 MB en el repo.
La `location /descargas/` de nginx tiene tres cosas que no son adorno:

- `application/vnd.android.package-archive` — sin ese tipo MIME Android baja
  el archivo pero no ofrece instalarlo: lo trata como un binario cualquiera.
- `Cache-Control: no-cache` — el nombre del archivo no cambia entre
  versiones, así que sin esto un celular que ya lo bajó se queda con el viejo.
- `autoindex off` — la carpeta no se lista.

Para publicar una versión nueva:

```bash
# En la PC de desarrollo
# Subir versionCode (solo sube, de a uno) y versionName en version.json.
# Es la fuente unica: la leen android/app/build.gradle y el backend.
nano version.json
npm run apk                # compila y FIRMA (necesita android/restomind.jks)
scp RestoMind.apk root@TU_IP:/home/restomind/descargas/RestoMind.apk

# En el VPS: que APK_VERSION_CODE coincida con el del APK, o la app no
# avisa de la actualización (ver backend/routes/app_version.py).
sudo -u restomind nano /home/restomind/app/.env   # APK_VERSION_CODE / APK_VERSION_NAME
systemctl restart restomind
curl -s https://app.jtechsolutiones.com/api/app/version   # hay_publicada: true
```

## 9. Endurecimiento de seguridad

Revisado el 2026-09-19 contra el VPS. Lo que está puesto y por qué:

| | Estado |
|---|---|
| `/docs`, `/redoc`, `/openapi.json` | **cerrados** con `ENVIRONMENT=production` — publicaban el mapa completo de la API sin pedir nada. Test: `tests/integration/test_docs_produccion.py` |
| Cabeceras | CSP, HSTS 1 año + includeSubDomains, X-Frame-Options DENY, nosniff, referrer-policy |
| CORS | un origen ajeno recibe 400 y **ningún** `access-control-allow-origin` |
| Puertos | 8000, 8100, 8010 y los de base de datos, **cerrados** desde internet (ufw: solo 22/80/443) |
| Rate limit | 5 fallos de login → 429 al sexto |
| Secretos | `.env` en 600, `certs/` en 750 |
| `fail2ban` | activo, jail `sshd`: 5 fallos en 10 min → ban de 1 h |
| `unattended-upgrades` | activo (parches de seguridad automáticos) |

**Pendiente, y es el mayor riesgo que queda:** el SSH acepta
`PermitRootLogin yes` + `PasswordAuthentication yes` con el puerto 22 abierto.
`fail2ban` lo mitiga —al instalarlo ya había **204 intentos fallidos**
acumulados y baneó 2 IPs en el primer minuto— pero la solución de fondo es
`PasswordAuthentication no` y entrar solo por clave. No se aplicó porque deja
sin acceso a quien no tenga la clave respaldada: hacerlo **solo** con
`~/.ssh/restomind_vps` guardada fuera de la PC, o con la consola web del
proveedor a mano.

**Conocido y no resuelto:** `npm audit` marca 1 crítica + 1 alta en
`node-tar`, vía `@capacitor/cli`. Es una herramienta de **compilación**: no
viaja dentro del APK ni corre en el servidor. El único arreglo no-breaking
(forzar `tar` a 7.5.21+ con `overrides`) se probó y **rompe `cap sync`**
—`Cannot read properties of undefined (reading 'extract')`, la API cambió
entre tar 6 y 7—. La alternativa es subir Capacitor 6 → 8, una migración
mayor que pondría en riesgo el plugin nativo de impresora.

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
