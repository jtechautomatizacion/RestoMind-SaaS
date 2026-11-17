# RestoMind en local

Cómo levantar el sistema completo en la PC de desarrollo para revisarlo antes de
mandarlo a producción. Corre igual que el VPS: uvicorn sirve la API y la app web
(Flutter) desde el mismo origen, y la firma SUNAT va en su contenedor Docker.

## Una vez

1. **Docker Desktop** instalado.
2. **Python**: `python -m venv .venv` y `.venv/Scripts/pip install -r requirements.txt`.
3. **Node** (para los scripts de `tools/`): `npm install`.
4. **Flutter 3.47.7** en `C:\src\flutter` (solo hace falta para recompilar la app).
5. **`.env`** en la raíz, copiado de `.env.example`, con `SECRET_KEY`,
   `SUNAT_SERVICE_URL=http://127.0.0.1:8100` y `SUNAT_SERVICE_TOKEN`
   (`python -c "import secrets; print(secrets.token_urlsafe(32))"`).
   **No** van `SUNAT_MODE` ni `SUNAT_SOAP_TIMEOUT` (ver CLAUDE.md, "Caída de
   entorno v4.0", punto c).

## Cada vez

```bash
npm run local
```

Prende Docker Desktop si está apagado, levanta el contenedor SUNAT (modo beta),
recompila la app web si quedó atrás del código y arranca el backend **en esa
misma terminal**, con sus logs a la vista. Cuando responde, muestra:

| Qué | Dónde |
|---|---|
| App web (PWA) | http://localhost:8000 |
| Panel del superadmin | http://localhost:8000/static/superadmin.html |
| Documentación de la API | http://localhost:8000/docs |
`Ctrl+C` apaga el backend; `npm run local:parar` apaga también el contenedor
SUNAT. Después de cambiar código del backend: `Ctrl+C` y `npm run local` otra
vez (en esta máquina `--reload` no recarga, ver CLAUDE.md).

> Use **`localhost`**, no `127.0.0.1`. La cookie de sesión es `Secure`, y los
> navegadores la aceptan sin HTTPS solo en `localhost`.

## Qué revisar antes de mandar a producción

1. `npm run verificar` en verde: formato, analyze y pruebas de Flutter, que
   `web/` esté al día, pruebas del APK y la suite de pytest.
2. En el navegador, con la cuenta del dueño:
   - Admin > Caja: abrir el turno (sin caja abierta, Mesas y Cocina se bloquean).
   - Mesas: tomar un pedido → aparece en Cocina → marcarlo listo → cobrar.
   - Con la facturación activa: cobrar con DNI y con RUC (sale la boleta de
     pruebas de SUNAT BETA).
   - Dinero: la venta aparece en el día. Exportar el Excel.
   - Admin > Caja: cerrar el turno y revisar el reporte imprimible.
3. Con una cuenta de personal (código de 6 dígitos, se crea en Admin > Personal):
   que vea solo sus pestañas.
4. **Sesión:** recargar la página (F5) no pide la contraseña de nuevo; "Cerrar
   sesión" sí la pide al volver. Cambiar la contraseña cierra la sesión en todos
   los aparatos.
5. **Instalar como app:** en Chrome, el ícono de instalar en la barra de
   direcciones (o menú ⋮ → "Instalar RestoMind").

## Mandarlo a producción

```bash
npm run verificar                 # tiene que terminar en "✓ Todo en verde"
git add -A && git commit          # incluye web/ (la compilación publicada)
git push
```

Y en el VPS, como siempre (deploy/RUNBOOK.md):

```bash
ssh -i ~/.ssh/restomind_vps root@167.148.33.5
# git y pip como el usuario dueño del checkout; systemctl como root
sudo -u restomind git -C /home/restomind/app pull
sudo -u restomind /home/restomind/app/venv/bin/pip install -r /home/restomind/app/requirements.txt
systemctl restart restomind
curl -s http://127.0.0.1:8000/health      # "codigo_desactualizado": false
```

La tabla nueva de sesiones (`sesiones_refresh`) se crea sola al arrancar.
Conviene sacar antes un backup con `VACUUM INTO` (RUNBOOK §7): la base está en
modo WAL y un `cp` del `.db` no alcanza.

**El nginx del VPS no hace falta cambiarlo para que funcione**: ya manda todo a
uvicorn. Pero `deploy/nginx.conf.template` trae ahora las reglas de borde de
Sac-Geo (límite en los logins, `X-Forwarded-For` sobrescrito, `/docs` cerrado);
aplicarlas es el paso del RUNBOOK §5 (copiar la plantilla, `nginx -t`, recargar).

**El APK instalado en los celulares no cambia** con este despliegue: sigue con su
frontend empaquetado y su login de siempre. Pasa a Flutter en la próxima etapa,
junto con la impresora Bluetooth.
