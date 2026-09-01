# Agente RestoMind — instalación en la PC del restaurante

Este agente baja las boletas que RestoMind genera en el servidor y las deja
en la carpeta que vigila el **Facturador SUNAT**.

Se instala **una vez por PC**, en la misma máquina donde está el Facturador.
No necesita instalar nada: usa PowerShell, que ya viene con Windows.

**No hay que abrir ningún puerto ni configurar el router.** El agente solo
hace conexiones salientes, igual que un navegador.

---

## Antes de empezar

- La PC donde está instalado el **Facturador SUNAT**, encendida y con internet.
- La **ruta de la carpeta DATA** del Facturador (donde deja los archivos a
  procesar). Normalmente algo como `C:\SFS\DATA`.
- El **token del agente**, que te entrega quien administra RestoMind.
  Se genera en el servidor con:
  ```bash
  python -m backend.scripts.crear_token_agente <cliente_id> "Caja principal"
  ```
  Se muestra **una sola vez**. Si se pierde, se genera otro y se revoca el viejo.

---

## 1. Copiar los archivos

Creá la carpeta `C:\RestoMindAgente` y copiá ahí:

- `RestoMindAgente.ps1`
- `config.example.json`

## 2. Configurar

Renombrá `config.example.json` a **`config.json`** y completalo:

```json
{
  "url": "https://app.tudominio.com.pe",
  "token": "el-token-que-te-entregaron",
  "carpetaFacturador": "C:\\SFS\\DATA"
}
```

> Las rutas de Windows van con **doble barra invertida** (`C:\\SFS\\DATA`).
> Es la forma de escribirlas dentro de un archivo JSON; con una sola barra
> el archivo no se puede leer.

## 3. Probar la conexión

Abrí PowerShell en `C:\RestoMindAgente` y corré:

```powershell
.\RestoMindAgente.ps1 -Probar
```

Tiene que responder algo así:

```
[INFO] Conexión OK. Restaurante: Cevichería El Puerto de Susy. Comprobantes pendientes: 0.
```

Este modo **no escribe nada**: solo valida el token y la carpeta. Si falla,
revisá la `url` (con `https://` adelante), el token, y que la carpeta exista.

> Si Windows bloquea la ejecución del script ("no se puede cargar porque la
> ejecución de scripts está deshabilitada"), habilitalo solo para tu usuario:
> ```powershell
> Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned
> ```

## 4. Dejarlo corriendo solo

Se programa como **Tarea Programada de Windows** — no como un script en un
bucle: así arranca sola cuando se prende la PC, y si el proceso se cae por
cualquier motivo, la siguiente ejecución lo levanta igual.

Abrí PowerShell **como administrador** y corré (en una sola línea):

```powershell
schtasks /Create /TN "RestoMind Agente" /SC MINUTE /MO 2 /RU "%USERNAME%" /RL LIMITED /F /TR "powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File C:\RestoMindAgente\RestoMindAgente.ps1"
```

Qué hace cada parte:

| | |
|---|---|
| `/SC MINUTE /MO 2` | Consulta cada 2 minutos. Es un buen equilibrio: la boleta llega al Facturador casi en el momento, sin castigar al servidor. |
| `/RL LIMITED` | Corre **sin privilegios de administrador**. Solo necesita escribir en una carpeta. |
| `-WindowStyle Hidden` | No abre una ventana negra cada 2 minutos delante del cajero. |

Para verificar que quedó registrada:

```powershell
schtasks /Query /TN "RestoMind Agente"
```

---

## Cómo saber que está funcionando

El agente escribe todo lo que hace en `C:\RestoMindAgente\agente.log`:

```powershell
Get-Content C:\RestoMindAgente\agente.log -Tail 20
```

Lo normal es ver `Sin comprobantes pendientes` la mayor parte del tiempo, y
un `Entregado: B001-00000042` cada vez que se emite una boleta.

Desde el servidor también se puede ver si un agente dejó de reportarse:

```bash
python -m backend.scripts.crear_token_agente --listar <cliente_id>
```

La columna **ÚLTIMO USO** dice cuándo fue la última vez que ese agente
consultó. Si dice varios días atrás, la PC está apagada, sin internet, o la
tarea programada se borró.

---

## Problemas comunes

**"No se pudo consultar el servidor"** — La PC no tiene internet, o la `url`
del config está mal. No es grave: los comprobantes quedan esperando en el
servidor y se entregan solos cuando vuelva la conexión.

**"Token de agente inválido"** — El token está mal copiado o fue revocado.
Pedí uno nuevo a quien administra RestoMind.

**"La carpeta del Facturador no existe"** — Revisá `carpetaFacturador` en el
`config.json`, con las dobles barras invertidas.

**Las boletas llegan pero el Facturador no las procesa** — Ya no es problema
del agente: los archivos están en la carpeta. Revisá que el Facturador esté
corriendo y que su certificado digital y credenciales SOL estén vigentes.

---

## Sobre `descargados.txt`

El agente crea ese archivo junto al script y anota cada comprobante que ya
dejó en la carpeta. **No lo borres.**

Es lo que impide que un mismo comprobante se escriba dos veces si se corta
la conexión justo después de entregarlo: sin ese registro, el agente lo
volvería a escribir, y si el Facturador ya lo había procesado, la boleta
podría emitirse **dos veces ante SUNAT**.

Si hay que reinstalar la PC, copiá ese archivo junto con el resto.
