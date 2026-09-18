"""
Genera el ícono y la pantalla de carga de la app a partir del logo.

    .venv/Scripts/python.exe tools/generar-iconos.py

Entrada:  marca/icono.jpeg  (el cuadrado azul con la R)
Salida:   los 20+ PNG que Android necesita, en sus carpetas, más los íconos
          de la PWA.

POR QUÉ NO SE USA EL JPEG TAL CUAL
----------------------------------
Tres razones, y las tres se ven en el teléfono:

1. Android recorta el ícono con la forma que elija el fabricante (círculo,
   cuadrado redondeado, gota). El JPEG ya trae SUS PROPIAS esquinas
   redondeadas dibujadas, así que recortar sobre recortado deja un borde
   blanco irregular alrededor del ícono.
2. El JPEG tiene un margen blanco desparejo (0 px a la izquierda, 33 abajo).
   Escalado a 48x48 eso descentra el logo de forma visible.
3. La compresión JPEG deja manchas alrededor de los bordes blancos. A tamaño
   de ícono se ven como suciedad.

Entonces se RECONSTRUYE: se extrae la marca blanca del logo, y se vuelve a
dibujar sobre el azul en cada tamaño. Queda nítido y centrado siempre.

CÓMO SE SEPARA LA MARCA DEL FONDO
---------------------------------
La marca es blanca; el margen del JPEG y las esquinas redondeadas también.
Un umbral de brillo por sí solo se lleva las tres cosas.

Lo que las distingue es la TOPOLOGÍA: el blanco de afuera toca el borde de
la imagen, y el de la marca no —está rodeado de azul por todos lados—. Así
que se inunda desde los bordes: lo claro que se alcanza desde afuera es
fondo, lo claro que queda aislado es la marca.

NO usa `sharp` ni ninguna dependencia nueva: Pillow ya es dependencia del
backend (comprime las fotos de los platos).
"""

from collections import deque
from pathlib import Path

from PIL import Image, ImageDraw

RAIZ = Path(__file__).resolve().parent.parent
ORIGEN = RAIZ / "marca" / "icono.jpeg"
RES = RAIZ / "android" / "app" / "src" / "main" / "res"

# Muestreado del propio logo (el azul más repetido de la imagen).
AZUL = (0x13, 0x43, 0x81)

# Umbral de brillo para decidir qué es "claro". 150 sobre 255 deja afuera el
# azul (brillo ~70) con mucho margen, y adentro el blanco de la marca aunque
# el JPEG lo haya ensuciado.
UMBRAL = 150


def extraer_marca(ruta: Path) -> Image.Image:
    """Devuelve la marca blanca sobre transparencia, ya recortada."""
    im = Image.open(ruta).convert("RGB")
    w, h = im.size
    px = im.load()

    def brillo(p):
        return 0.299 * p[0] + 0.587 * p[1] + 0.114 * p[2]

    claro = [[brillo(px[x, y]) > UMBRAL for x in range(w)] for y in range(h)]

    # Inundación desde el borde: marca todo lo claro que se alcanza desde
    # afuera. Eso es el margen y las esquinas redondeadas, nunca la marca.
    fuera = [[False] * w for _ in range(h)]
    cola = deque()
    for x in range(w):
        for y in (0, h - 1):
            if claro[y][x] and not fuera[y][x]:
                fuera[y][x] = True
                cola.append((x, y))
    for y in range(h):
        for x in (0, w - 1):
            if claro[y][x] and not fuera[y][x]:
                fuera[y][x] = True
                cola.append((x, y))
    while cola:
        x, y = cola.popleft()
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nx, ny = x + dx, y + dy
            if 0 <= nx < w and 0 <= ny < h and claro[ny][nx] and not fuera[ny][nx]:
                fuera[ny][nx] = True
                cola.append((nx, ny))

    # El alfa sale del brillo, no de un sí/no: así los bordes de la marca
    # quedan suaves en vez de dentados al escalar.
    marca = Image.new("RGBA", (w, h), (255, 255, 255, 0))
    mpx = marca.load()
    for y in range(h):
        for x in range(w):
            if fuera[y][x]:
                continue
            b = brillo(px[x, y])
            if b <= UMBRAL:
                continue
            alfa = int(255 * min(1.0, (b - UMBRAL) / (255 - UMBRAL) * 1.6))
            mpx[x, y] = (255, 255, 255, alfa)

    return marca.crop(marca.getbbox())


def centrar(marca: Image.Image, lienzo: int, ocupacion: float) -> Image.Image:
    """La marca, escalada a `ocupacion` del lienzo y centrada, sobre transparencia."""
    objetivo = lienzo * ocupacion
    escala = min(objetivo / marca.width, objetivo / marca.height)
    nueva = marca.resize(
        (max(1, round(marca.width * escala)), max(1, round(marca.height * escala))),
        Image.LANCZOS,
    )
    fondo = Image.new("RGBA", (lienzo, lienzo), (255, 255, 255, 0))
    fondo.paste(nueva, ((lienzo - nueva.width) // 2, (lienzo - nueva.height) // 2), nueva)
    return fondo


def cuadrado_redondeado(lado: int, marca: Image.Image) -> Image.Image:
    """Ícono clásico: azul con esquinas redondeadas y la marca encima.

    Solo lo usan los Android viejos (anteriores al 8.0). Del 8.0 en adelante
    manda el ícono adaptativo, que recorta con la forma del fabricante.
    """
    img = Image.new("RGBA", (lado, lado), (255, 255, 255, 0))
    mascara = Image.new("L", (lado * 4, lado * 4), 0)
    ImageDraw.Draw(mascara).rounded_rectangle(
        (0, 0, lado * 4 - 1, lado * 4 - 1), radius=lado * 4 * 22 // 100, fill=255
    )
    img.paste(Image.new("RGBA", (lado, lado), AZUL + (255,)), (0, 0),
              mascara.resize((lado, lado), Image.LANCZOS))
    encima = centrar(marca, lado, 0.72)
    img.paste(encima, (0, 0), encima)
    return img


def guardar(img: Image.Image, ruta: Path) -> None:
    ruta.parent.mkdir(parents=True, exist_ok=True)
    img.save(ruta, "PNG", optimize=True)
    print(f"  {ruta.relative_to(RAIZ).as_posix():58} {img.width}x{img.height}")


def main() -> None:
    if not ORIGEN.exists():
        raise SystemExit(f"No encuentro {ORIGEN}")

    print(f"\nLeyendo {ORIGEN.relative_to(RAIZ).as_posix()}")
    marca = extraer_marca(ORIGEN)
    print(f"  marca extraida: {marca.width}x{marca.height}\n")

    # --- Ícono adaptativo (Android 8+) -------------------------------------
    # El lienzo es de 108dp pero solo se VE el centro de 72dp: el resto lo
    # recorta la forma del fabricante. Por eso la marca ocupa 58% y no más —
    # en un teléfono que recorta en círculo, algo más grande pierde las puntas
    # del gorro y del tenedor.
    print("Icono adaptativo (Android 8+):")
    for carpeta, lado in (("mdpi", 108), ("hdpi", 162), ("xhdpi", 216),
                          ("xxhdpi", 324), ("xxxhdpi", 432)):
        guardar(centrar(marca, lado, 0.58),
                RES / f"mipmap-{carpeta}" / "ic_launcher_foreground.png")

    (RES / "values" / "ic_launcher_background.xml").write_text(
        '<?xml version="1.0" encoding="utf-8"?>\n'
        "<!-- GENERADO por tools/generar-iconos.py - muestreado del logo -->\n"
        "<resources>\n"
        f'    <color name="ic_launcher_background">#{AZUL[0]:02X}{AZUL[1]:02X}{AZUL[2]:02X}</color>\n'
        "</resources>\n",
        encoding="utf-8",
    )
    print(f"  values/ic_launcher_background.xml -> #{AZUL[0]:02X}{AZUL[1]:02X}{AZUL[2]:02X}")

    # --- Ícono clásico (Android 7 y anteriores) ----------------------------
    print("\nIcono clasico (Android 7 y anteriores):")
    for carpeta, lado in (("mdpi", 48), ("hdpi", 72), ("xhdpi", 96),
                          ("xxhdpi", 144), ("xxxhdpi", 192)):
        icono = cuadrado_redondeado(lado, marca)
        guardar(icono, RES / f"mipmap-{carpeta}" / "ic_launcher.png")
        guardar(icono, RES / f"mipmap-{carpeta}" / "ic_launcher_round.png")

    # --- Pantalla de carga -------------------------------------------------
    #
    # NO se generan imágenes de pantalla completa, y es a propósito. El fondo
    # de ventana ESTIRA el bitmap para llenar la pantalla, así que una imagen
    # ya compuesta se deforma en cualquier proporción distinta de aquella para
    # la que se generó — y hay tantas proporciones como modelos de teléfono.
    #
    # Android arma la pantalla solo: color de fondo + ícono centrado. Ver
    # values/styles.xml (Android 12+) y drawable/splash_fondo.xml (anteriores).
    # Los dos reusan el ícono adaptativo que ya se generó arriba.
    #
    # Lo único que hace falta es la marca suelta para el "Cargando..." que
    # dibuja la propia app en HTML, después del splash del sistema.
    print("\nMarca para el 'Cargando...' de la app:")
    guardar(centrar(marca, 512, 0.86), RAIZ / "frontend" / "assets" / "marca-blanca.png")

    # --- PWA ---------------------------------------------------------------
    # Hasta ahora el manifest traía un SVG genérico embebido en base64 — un
    # dibujo de cubiertos que no era este logo. Se reemplaza por el de verdad.
    print("\nPWA (instalar desde el navegador):")
    for lado in (192, 512):
        guardar(cuadrado_redondeado(lado, marca),
                RAIZ / "frontend" / "assets" / f"icono-{lado}.png")

    print("\nListo.\n")


if __name__ == "__main__":
    main()
