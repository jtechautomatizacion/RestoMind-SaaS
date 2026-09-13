# 🧪 Mapa de la suite de tests

**340 tests · `python -m pytest -q` · ~2,5 min**

Este archivo existe para responder una sola pregunta, la que importa antes
de salir a producción: **si alguien rompe X, ¿algún test lo dice?**

No es una lista de todo lo que hay. Es el mapa de lo que puede costar
dinero, una multa o un cliente, y dónde está el test que lo cubre.

---

## Cómo está organizada

```
tests/
├── conftest.py                  fixtures compartidas (BD aislada, cliente, mesas, platos)
├── unit/                        lógica pura, sin HTTP ni BD
│   ├── test_config.py           arranque y fail-fast de configuración
│   ├── test_models.py           invariantes del esquema
│   ├── test_sunat_cloud.py      la matemática del IGV y el armado del comprobante
│   └── test_nombre_archivo_sunat.py
└── integration/                 el endpoint real, con la cadena de permisos
    ├── test_endpoints.py        CRUD, permisos por rol, aislamiento multi-tenant
    ├── test_facturas.py         qué comprobante corresponde, correlativos, el switch
    ├── test_rol_asistente.py    el rol 'asistente' y quién ve "Todo en uno"
    ├── test_configuracion.py    activación de SUNAT, certificado, datos fiscales
    ├── test_ruc_padron.py       consulta de RUC/DNI, cuota, datos personales
    ├── test_caja_seguridad.py   los 3 bloqueadores de la auditoría de caja
    ├── test_push.py             notificaciones a cocina
    ├── test_email_seguridad.py
    ├── test_sunat_cloud_emisor.py
    └── test_seed_produccion.py
```

Dos convenciones que conviene no romper:

- **El nombre del test es la frase que tiene que seguir siendo verdad.**
  `test_un_mozo_no_puede_forzar_el_cierre_de_la_caja_del_admin` se lee sin
  abrir el archivo. Un `test_caja_3` no dice nada cuando falla en rojo a
  las once de la noche.
- **Cada test de seguridad tiene su contracara.** Blindar algo casi siempre
  puede romper el camino legítimo, y ese es el bug que nadie ve hasta que
  un restaurante no puede vender. Por eso van en pares: ver
  `test_con_la_facturacion_apagada_cobrar_no_emite_nada` junto a
  `test_el_cobro_en_si_NO_se_bloquea_con_la_facturacion_apagada`.

---

## Lo que protege plata o cumplimiento fiscal

Esta es la parte que hay que mirar antes de cada despliegue.

| Riesgo real | Qué pasaría | Test que lo agarra |
|---|---|---|
| Emitir con la facturación apagada | Comprobantes a SUNAT a nombre de un restaurante que decidió no emitir, y correlativos quemados | `test_facturas.py::test_con_la_facturacion_apagada_cobrar_no_emite_nada` |
| Apagar el switch bloquea la venta | El restaurante no puede cobrar | `test_facturas.py::test_el_cobro_en_si_NO_se_bloquea_con_la_facturacion_apagada` |
| Facturar en Nuevo RUS | **Infracción del emisor** y crédito fiscal indebido al comprador | `test_facturas.py::test_en_NUEVO_RUS_un_RUC_produce_BOLETA_no_factura` |
| Correlativo compartido entre series | Huecos permanentes en B001 y F001; SUNAT las exige consecutivas | `test_facturas.py` (bloque de correlativos) |
| Correlativo consumido por un intento fallido | Hueco permanente en la serie | `test_facturas.py::test_con_la_facturacion_apagada_cobrar_no_emite_nada` verifica que el contador quede intacto |
| Nombre del archivo ≠ `cbc:ID` | SUNAT rechaza **todas** las boletas (error 1036) | `test_nombre_archivo_sunat.py` |
| El IGV no cuadra | SUNAT rechaza si `subtotal + igv != total` | `test_sunat_cloud.py`, calibrado contra la boleta real EB01-1297 |
| Dos turnos de caja abiertos | Las mismas ventas se cuentan dos veces; la caja no cuadra nunca | `test_caja_seguridad.py::test_la_bd_impide_dos_turnos_abiertos_aunque_se_salte_la_validacion` |
| Un mozo fuerza el cierre de caja | Se pierde el conteo real del admin | `test_caja_seguridad.py::test_un_mozo_no_puede_forzar_el_cierre_de_la_caja_del_admin` |
| Cobrar comida que no se entregó | | `test_endpoints.py` (cobro con comanda en cocina → 400) |

## Lo que protege datos

| Riesgo | Test |
|---|---|
| Un restaurante ve datos de otro | `test_endpoints.py` (aislamiento por `cliente_id`), `test_rol_asistente.py::test_el_asistente_de_OTRO_restaurante_no_ve_estas_mesas` |
| Staff accede a endpoints de admin | `test_endpoints.py::test_staff_no_puede_entrar_a_endpoints_de_admin` |
| El asistente ve el dinero del dueño | `test_rol_asistente.py::test_el_asistente_NO_ve_el_dinero_ni_la_administracion` |
| El padrón queda como API pública de datos personales | `test_ruc_padron.py` (exige sesión + cuota por IP) |
| La app arranca con un `SECRET_KEY` público | `test_config.py::test_settings_falla_sin_secret_key` |
| Un token sin `tipo` se cuela | `test_endpoints.py::test_token_sin_tipo_explicito_no_accede_a_rutas_de_restaurante` |

---

## Bugs reales que dejaron test

Cada uno de estos se rompió de verdad. El test es para que no vuelva.

- **SUNAT rechazaba todas las boletas (1036).** El nombre del archivo
  llevaba el correlativo rellenado con ceros (`00000028`) y el `cbc:ID` del
  XML no (`B001-28`). → `test_nombre_archivo_sunat.py`, 7 tests.
- **jefe_cocina no recibía ninguna notificación**, en silencio. El join se
  hacía contra `Usuario.email`, que para el staff es `NULL` (su `sub` es el
  código de acceso). El test original lo tapaba porque el fixture le
  inventaba un email que la app nunca pone. → `test_push.py` crea el staff
  por el camino real (`POST /usuarios/staff`).
- **El dashboard financiero estaba abierto a cualquier rol** durante meses.
  Lo destapó un test escrito para otra cosa. → la lección quedó: los tests
  de permisos se escriben **por rol real**, no por endpoint.
- **El switch de facturación vivía solo en JavaScript.** Un dispositivo
  logueado desde antes de apagarlo seguía emitiendo. → el bloque "EL SWITCH
  APAGADO" en `test_facturas.py`.
- **El tique imprimía `-` como cliente** aunque el RUC estuviera en el
  padrón, y como cajero a quien estaba logueado en el navegador en vez de a
  quien atendió. → bloque "Lo que el cliente recibe EN PAPEL".

---

## Lo que NO cubre la suite (y hay que probar a mano)

Decirlo explícitamente vale más que una cobertura del 80 % que no distingue
entre lo probado y lo supuesto.

1. **El envío real a SUNAT.** Se sustituye por un doble. Pegarle a SUNAT en
   un test sería lento, dependiente de la red y emitiría comprobantes
   reales. Lo que SUNAT acepta se prueba en BETA, a mano.
2. **El frontend.** No hay tests de JS. Las reglas que el frontend comparte
   con el backend (permisos por rol, quién ve "Todo en uno", roles
   exclusivos) están duplicadas a propósito en los dos lados, y el backend
   —que es el que manda— sí tiene test. Si cambia uno, cambia el otro.
3. **La impresión térmica de 58/80 mm.** Depende del driver y del papel.
4. **Firebase.** Se prueba que la comanda se cree igual aunque el envío
   falle; el envío en sí necesita un proyecto real.
5. **La carga del padrón** (18,4 M de filas, ~25 min). Se prueba la
   consulta, no la construcción.

---

## Comandos

```bash
python -m pytest -q                                  # todo
python -m pytest tests/integration/test_facturas.py -q
python -m pytest -q -k "asistente or switch"         # por nombre
python -m pytest -q -x --lf                          # solo lo que falló, y parar en el primero
```

> **Ojo con el rate limit en tests.** `TestClient` reporta siempre el mismo
> host falso, así que un test de credenciales inválidas puede chocar con el
> límite de otro test y ver un 429 que no tiene nada que ver. `conftest.py`
> lo resetea con un fixture `autouse`; no lo quites.
