# ✅ ESTADO DEL PROYECTO - RestoMind MVP

## 🎯 Estado Actual: MVP FUNCIONAL

Los 5 casos de uso están implementados, probados y conectados de punta a punta:

- ✅ **CU-01** Gestión de la Carta (crear/editar/desactivar platos)
- ✅ **CU-02** Comandas Express desde el celular del mozo
- ✅ **CU-03** Monitor de Cocina en tiempo real
- ✅ **CU-04** Control de Compras / Caja Chica
- ✅ **CU-05** Dashboard Financiero (ventas, gastos, ganancia, top platos) — agregado durante el desarrollo, no estaba en el documento de requisitos original
- ✅ **Cobro de mesa** — flujo que no estaba en la especificación original y que hacía falta para cerrar el ciclo (ver "Bugs y huecos corregidos" abajo)
- ✅ **Fotos de platos** — subir/reemplazar/quitar foto por plato, con compresión en el navegador y validación de archivo real en el servidor (ver abajo)
- ✅ 26 tests automáticos (`pytest tests/ -v`), todos en verde
- ✅ Frontend PWA rediseñado: mobile-first, bottom nav, sin librerías externas (ni fuentes web ni Chart.js), pensado para gama media/baja
- ✅ Datos semilla automáticos al arrancar (`backend/seed.py`): 1 restaurante demo, 8 mesas, 12 platos de cebichería

## 🐛 Bugs y huecos corregidos durante la implementación

1. **No existía forma de cobrar una mesa.** La especificación original solo contemplaba `cocina → entregado`, así que las mesas quedaban "ocupadas" para siempre y nunca había dinero que mostrar en ningún reporte. Se agregó `POST /api/mesas/{id}/cobrar`, que cierra todas las comandas activas de la mesa y la libera — pero **rechaza el cobro si todavía hay platos en cocina** (no se puede cobrar algo que el cliente no recibió).
2. **Dashboard mostraba S/ 0 aunque hubiera ventas.** Se mezclaba `date.today()` (hora local) con timestamps guardados en UTC (`datetime.utcnow()`). En Perú (UTC-5), pasada cierta hora la fecha UTC ya es "el día siguiente" y la venta caía fuera del rango consultado. Se corrigió usando UTC de forma consistente en el cálculo del rango de fechas.
3. **El mismo bug de fecha UTC/local existía también en Compras**, pasó desapercibido en la primera corrección: `date.today()` en `backend/routes/compras.py` podía rechazar un gasto de "hoy" como "fecha futura" cuando la fecha local y la UTC del servidor caen en días distintos. Corregido para usar UTC en todo el módulo, igual que el dashboard.
4. **Bug de CSS que dejaba 3 de las 4 pestañas invisibles para siempre** ("solo veo Mesas, nada más responde" — reportado en producción por el usuario). Cocina, Dinero y Admin (más la sub-pestaña Gastos dentro de Admin) tenían la clase `hidden` (`display:none !important`) además de su clase de componente; el código de navegación solo alternaba la clase `active`, nunca quitaba `hidden`, así que el `!important` ganaba siempre sin importar qué se tocara en el menú. Se quitó la clase redundante de esos 4 elementos.
5. **SQLite en memoria "perdía" las tablas en los tests.** Cada conexión nueva del pool abría una base `:memory:` distinta y vacía. Se forzó `StaticPool` para que todas las conexiones de test compartan la misma base.
6. **Plato duplicado en una comanda rompía el total.** Si el payload llegaba con el mismo `plato_id` dos veces (por ejemplo, un doble-tap accidental), se creaban dos filas en vez de sumar cantidades. Ahora se fusionan por `plato_id` antes de calcular el total.
7. **Editar un plato desde el admin creaba uno nuevo en vez de actualizarlo** (el formulario del modal siempre hacía `POST`). Se agregó seguimiento de "modo edición" para que dispare `PATCH` cuando corresponde.
8. **`min_items` en Pydantic v2** — sintaxis deprecada que rompía la validación de listas; se reemplazó por `min_length`.

## 📸 Fotos de platos

- `POST /api/platos/{id}/imagen` (multipart) y `DELETE /api/platos/{id}/imagen`.
- El servidor **no confía en el Content-Type ni en la extensión del archivo** que manda el cliente (ambos se falsean trivialmente); valida la firma binaria real (JPEG/PNG/WEBP) antes de guardar nada en disco.
- El nombre del archivo en disco es siempre `{plato_id}.{ext}` — nunca se usa `cliente_id` para construir la ruta, porque ese valor viene de un header sin autenticar y podría usarse para un path traversal (`../../../etc`) si se usara para armar una carpeta.
- El frontend comprime la foto en el navegador (canvas, máx. 800px, JPEG 0.8) antes de subirla — clave para el objetivo de celulares de gama baja con datos limitados.
- Se ve como miniatura en la carta del Mozo y en la lista de Admin; sin foto, se muestra un ícono placeholder (nunca un hueco vacío).

## 📁 Estructura relevante

```
backend/
├── app.py              # FastAPI + routers + seed automático al arrancar
├── config.py           # Settings (pydantic-settings)
├── database.py         # SQLAlchemy engine/session
├── dependencies.py     # get_cliente_id (header X-Cliente-Id), get_usuario_actual
├── models.py           # 7 tablas
├── schemas.py           # Pydantic: validación + respuestas
├── seed.py             # Datos demo idempotentes
├── services.py         # Reglas de negocio: transiciones de estado, cobro de mesa
└── routes/
    ├── platos.py        # CU-01
    ├── mesas.py         # Soporte + cobro de mesa
    ├── comandas.py      # CU-02 + CU-03 (monitor de cocina)
    ├── compras.py       # CU-04
    └── dashboard.py     # CU-05

frontend/
├── index.html           # Bottom nav: Mesas / Cocina / Dinero / Admin
├── css/style.css         # Design system mobile-first (light + dark)
├── assets/platos/        # Fotos subidas (gitignored, la crea el backend)
└── js/
    ├── app.js            # API client, navegación, toasts
    ├── charts.js         # Gráficos SVG a mano (sin librerías)
    ├── mozo.js           # Mesas, nuevo pedido, cuenta y cobro
    ├── cocina.js         # Monitor en tiempo real (polling 4s)
    ├── dashboard.js       # CU-05
    └── admin.js          # Carta (con fotos) + Gastos

tests/
├── conftest.py           # Fixtures (BD en memoria con StaticPool)
├── unit/test_models.py
└── integration/test_endpoints.py   # 26 tests, cubren el ciclo completo
```

## 📋 Cómo correrlo

```bash
cd "d:\Cartera de proyectos\RestoMind-SaaS"
./venv/Scripts/activate            # Windows
pip install -r requirements.txt    # si falta algo
uvicorn backend.app:app --reload --host 0.0.0.0 --port 8000
```

- App (PWA): `http://localhost:8000/static/index.html`
- Docs (Swagger): `http://localhost:8000/docs`
- Tests: `pytest tests/ -v`

El primer arranque crea `restomind.db` con datos de demo (restaurante "La Marisquería del Chef", 8 mesas, 12 platos). Es idempotente: si borras el archivo `restomind.db`, se vuelve a sembrar solo.

## 🔑 Decisiones de diseño a tener en cuenta

- **Multi-tenant sin login todavía:** `cliente_id` se resuelve en `backend/dependencies.py` desde el header `X-Cliente-Id`; si no llega, usa `settings.default_cliente_id` (`rest-001`). Cuando se agregue autenticación, ese es el único archivo a tocar.
- **El dinero solo cuenta cuando se cobra**, no cuando se crea la comanda. El dashboard filtra por `estado == 'cobrado'`.
- **Charts sin librerías**: se generan como SVG puro en `charts.js` a propósito, para no depender de un CDN (rompería el modo offline de la PWA) y para mantener el bundle liviano en celulares de gama baja.

## 📞 Próximos pasos sugeridos (post-MVP)

1. **Autenticación real** (JWT) para reemplazar el header `X-Cliente-Id` de desarrollo.
2. **Multi-restaurante**: pantalla de registro para que un nuevo cliente se dé de alta solo.
3. **IA + Claude API**: reportes inteligentes sobre los datos que ya arroja el Dashboard (ver guía de negocio de JTech).
4. **Pagos**: integración Stripe/Culqi para cobro con QR.
5. **Zona horaria por cliente**: hoy el corte de "día" del dashboard usa UTC; con clientes en distintos países convendría guardar el timezone del restaurante.

---

**Última actualización:** 2026-08-29
**Estado:** ✅ MVP funcional, probado y listo para demo comercial
