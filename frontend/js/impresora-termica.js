/**
 * Impresión en térmica de 80 mm por Bluetooth (ESC/POS).
 *
 * POR QUÉ EXISTE
 * --------------
 * `window.print()` —lo que usa print.js— NO hace nada dentro de un WebView:
 * no existe el diálogo de impresión del navegador. Y aunque existiera, una
 * ADV-9026 por Bluetooth no aparece como impresora del sistema: habla
 * ESC/POS crudo sobre un socket SPP. Sin esto, la app instalada no imprime
 * absolutamente nada, que para un POS es no funcionar.
 *
 * DE DÓNDE SALE EL TICKET
 * -----------------------
 * Del MISMO HTML que ya genera print.js, convertido acá. No se escriben
 * versiones de texto paralelas de los cuatro tickets: dos generadores del
 * mismo documento se desincronizan sin falta, y el día que alguien agregue
 * una línea al ticket de cocina se acuerda de uno solo. Acá se recorre el
 * DOM que print.js ya produjo y se traduce.
 *
 * ACENTOS
 * -------
 * Se transliteran (CLÁSICO -> CLASICO) en vez de mandar una página de
 * códigos. Las térmicas chinas de 80 mm declaran CP850 y muchas no la
 * implementan igual: el resultado es "CL├üSICO" en el papel, que no se
 * entiende. Un ticket sin tildes se lee perfecto; uno con basura, no.
 */

(function () {
    'use strict';

    // Columnas por ancho de papel, con la fuente A (12x24). Es EL dato de
    // compatibilidad entre marcas: casi todas las térmicas entienden el
    // mismo ESC/POS, pero vienen en 58 mm o en 80 mm. Con el ancho
    // equivocado no falla nada — simplemente los importes salen cortados o
    // flotando en el medio, que es peor que un error.
    const COLUMNAS = { '58': 32, '80': 48 };

    const CLAVE_CONFIG = 'restomind_impresora';

    // Copia en memoria. Es la unica fuente que NO depende de que el WebView
    // haya conservado su almacenamiento: tras reinstalar la app, localStorage
    // arranca vacio y la restauracion desde el nativo es ASINCRONA. Sin esta
    // cache habia una ventana en la que configuracion() devolvia null y la
    // impresion salia con el lenguaje equivocado.
    let enMemoria = null;
    let restauracionEnCurso = null;

    /** { tipo: 'bluetooth'|'red', destino: 'MAC'|'ip:puerto', ancho: '58'|'80' } */
    function configuracion() {
        if (enMemoria) return enMemoria;
        try {
            const crudo = localStorage.getItem(CLAVE_CONFIG);
            if (crudo) {
                const c = JSON.parse(crudo);
                if (c && c.destino) {
                    enMemoria = {
                        tipo: c.tipo || 'bluetooth',
                        destino: c.destino,
                        ancho: COLUMNAS[c.ancho] ? c.ancho : '80',
                        // 'escpos' = impresora de tickets, 'tspl' = de
                        // etiquetas. Por defecto tickets, que es el caso
                        // de un restaurante.
                        lenguaje: c.lenguaje === 'tspl' ? 'tspl' : 'escpos',
                    };
                    return enMemoria;
                }
            }
        } catch (_) { /* almacenamiento bloqueado o JSON viejo */ }
        return null;
    }

    /** Acceso a cualquier plugin de Capacitor, o null en el navegador. */
    function pluginDe(nombre) {
        const P = window.Capacitor && window.Capacitor.Plugins;
        return (P && P[nombre]) || null;
    }

    /**
     * Guarda la impresora en DOS lugares, y no es redundancia.
     *
     * localStorage vive dentro del WebView: es rapido y sincrono (lo necesita
     * configuracion(), que se consulta al imprimir), pero Android puede
     * vaciarlo al liberar espacio, y el boton "limpiar cache" de la app lo
     * borra a proposito. Cuando eso pasa, el local se queda sin impresora
     * configurada justo cuando va a cobrar.
     *
     * Preferences es almacenamiento NATIVO de Android: sobrevive a todo eso.
     * Es asincrono, asi que no sirve para leer en el momento de imprimir —
     * por eso se usa como respaldo y se vuelca a localStorage al arrancar.
     */
    function guardarConfiguracion(cfg) {
        enMemoria = cfg;
        const texto = JSON.stringify(cfg);
        try { localStorage.setItem(CLAVE_CONFIG, texto); } catch (_) { }

        const P = pluginDe('Preferences');
        if (P) {
            P.set({ key: CLAVE_CONFIG, value: texto })
             .catch(err => console.warn('[Termica] no se pudo guardar en nativo:', err));
        }
    }

    /** Al arrancar, recupera la configuracion del almacenamiento nativo si
     *  el WebView perdio la suya. */
    async function restaurarConfiguracion() {
        const P = pluginDe('Preferences');
        if (!P) return;
        try {
            const r = await P.get({ key: CLAVE_CONFIG });
            if (!r || !r.value) return;
            // Si el usuario ya cambio algo en ESTA sesion, su eleccion manda:
            // el respaldo solo cubre el caso de que no haya nada.
            if (!localStorage.getItem(CLAVE_CONFIG)) {
                localStorage.setItem(CLAVE_CONFIG, r.value);
            }
            // Se limpia la cache para que el proximo configuracion() relea y
            // normalice lo recien restaurado.
            enMemoria = null;
            configuracion();
        } catch (err) {
            console.warn('[Termica] no se pudo restaurar del nativo:', err);
        }
    }

    /** Garantiza que la configuracion nativa ya se haya intentado leer.
     *  Se comparte una sola promesa: si se llama diez veces, se restaura una. */
    function asegurarConfiguracion() {
        // Solo se memoriza si el puente de Capacitor YA existe. Al arrancar
        // puede no estar todavia, y ahi restaurarConfiguracion() sale sin
        // hacer nada: guardar esa promesa vacia dejaria la restauracion
        // cancelada para toda la sesion.
        if (restauracionEnCurso) return restauracionEnCurso;
        const intento = restaurarConfiguracion();
        if (pluginDe('Preferences')) restauracionEnCurso = intento;
        return intento;
    }

    function anchoActual() {
        const c = configuracion();
        return COLUMNAS[(c && c.ancho) || '80'] || 48;
    }

    // --- ESC/POS ---------------------------------------------------------
    const ESC = 0x1B, GS = 0x1D, LF = 0x0A;
    const INIT = [ESC, 0x40];
    const ALINEAR = { left: [ESC, 0x61, 0], center: [ESC, 0x61, 1], right: [ESC, 0x61, 2] };
    const NEGRITA = (on) => [ESC, 0x45, on ? 1 : 0];
    const TAMANO = (n) => [GS, 0x21, n];   // 0x00 normal, 0x11 doble alto+ancho
    const CORTAR = [GS, 0x56, 0x42, 0x00]; // corte parcial
    const AVANZAR = (n) => [ESC, 0x64, n]; // n líneas, para que el papel salga del cabezal

    function sinTildes(texto) {
        return (texto || '')
            .normalize('NFD')
            .replace(/[̀-ͯ]/g, '')   // marcas diacríticas
            .replace(/[^\x20-\x7E]/g, '');      // cualquier otra cosa fuera de ASCII
    }

    function bytesDeTexto(texto) {
        const limpio = sinTildes(texto);
        const out = [];
        for (let i = 0; i < limpio.length; i++) out.push(limpio.charCodeAt(i) & 0xFF);
        return out;
    }

    /** Una línea con algo a la izquierda y algo pegado a la derecha, que es
     *  como se leen los importes en un ticket. Si no entran juntos, el
     *  precio manda: cortar el nombre es molesto, cortar el monto es un
     *  problema. */
    function lineaDosColumnas(izq, der, ancho) {
        const a = sinTildes(izq), b = sinTildes(der);
        const relleno = ancho - a.length - b.length;
        if (relleno >= 1) return a + ' '.repeat(relleno) + b;
        // No entran juntos: se recorta el NOMBRE, nunca el importe. Un plato
        // con el nombre cortado se entiende; un monto cortado es un
        // problema. Pasa seguido en papel de 58 mm.
        return a.slice(0, Math.max(0, ancho - b.length - 1)) + ' ' + b;
    }

    // --- HTML -> ESC/POS -------------------------------------------------

    function textoDe(nodo) {
        return (nodo.textContent || '').replace(/\s+/g, ' ').trim();
    }

    /**
     * Recorre el ticket ya renderizado y lo traduce. Se apoya en las clases
     * que print.js usa (.ticket-header, .ticket-mesa, .ticket-total, las
     * tablas de detalle), no en la posición de los elementos: agregarle un
     * <div> al ticket no rompe esto.
     */
    /**
     * PASO 1 — Del HTML del ticket a una lista de líneas con su formato.
     *
     * Se separó del armado de bytes porque ahora hay DOS lenguajes de
     * impresora (ESC/POS para las de tickets, TSPL para las de etiquetas) y
     * los dos imprimen el MISMO ticket. Con la extracción compartida, el día
     * que se agregue una línea al comprobante aparece en los dos sin tocar
     * nada más.
     */
    function extraerLineas(html, ancho) {
        const doc = new DOMParser().parseFromString(html, 'text/html');
        const out = [];
        // `texto` para una linea simple; `izq`/`der` para las de dos
        // columnas, que cada lenguaje resuelve a su manera.
        const agregar = (texto, opciones) => {
            out.push(Object.assign(
                {
                    texto: texto, izq: null, der: null,
                    centrado: false, derecha: false,
                    negrita: false, doble: false,
                    // `destacado` = el numero que manda en el ticket. Va en
                    // la fuente mas grande que tenga la impresora.
                    destacado: false,
                    grueso: false,
                },
                opciones || {}
            ));
        };

        const cuerpo = doc.body;
        if (!cuerpo) return out;

        const visitar = (el) => {
            for (const hijo of Array.from(el.children)) {
                const clases = ' ' + (hijo.className || '') + ' ';
                const tiene = (c) => clases.indexOf(' ' + c + ' ') >= 0 || clases.indexOf(c) >= 0;
                const etiqueta = hijo.tagName;

                if (etiqueta === 'TABLE') {
                    // El encabezado (Articulo / Cant / Importe) se OMITE: en
                    // un ticket de 32-48 columnas ocupa una linea entera para
                    // decir algo que ya es obvio por el contenido, y el papel
                    // se paga por metro.
                    for (const fila of Array.from(hijo.querySelectorAll('tbody tr, tr'))) {
                        if (fila.closest('thead')) continue;
                        const celdas = Array.from(fila.children);
                        const cant = celdas.find(c => (c.className || '').includes('cant'));
                        const nombre = celdas.find(c => (c.className || '').includes('nombre'));
                        const precio = celdas.find(c => (c.className || '').includes('precio'));

                        // La cantidad va ADELANTE del nombre aunque en el HTML
                        // esté después: en el papel se lee "2x Ceviche", que es
                        // como lo canta el mozo.
                        let izquierda = '';
                        if (cant && nombre) {
                            // El ticket de cocina ya escribe "2x" en la celda;
                            // el de pre-venta pone solo "2". Se agrega la "x"
                            // únicamente si falta, para no terminar con "2xx".
                            const c = textoDe(cant);
                            izquierda = (/x$/i.test(c) ? c : c + 'x') + ' ' + textoDe(nombre);
                        } else {
                            izquierda = [cant, nombre].filter(Boolean).map(textoDe).join(' ');
                        }

                        if (precio) agregar(null, { izq: izquierda, der: textoDe(precio) });
                        else if (izquierda) agregar(izquierda);
                    }
                    continue;
                }

                // Separadores: una linea de guiones, no un div vacio.
                if (tiene('linea')) { agregar('-'.repeat(ancho)); continue; }

                // Pares etiqueta/valor (MESA: 1 ... N 13) en dos columnas.
                if (tiene('campos')) {
                    const partes = Array.from(hijo.children).map(textoDe).filter(Boolean);
                    if (partes.length >= 2) agregar(null, { izq: partes[0], der: partes[partes.length - 1] });
                    else if (partes.length) agregar(partes[0]);
                    continue;
                }

                // TOTAL: el numero que dos personas van a comparar en el
                // mostrador. Va separado y destacado.
                if (tiene('total-caja') || tiene('ticket-total') || tiene('total-grande')) {
                    // Barra gruesa: separa el detalle de la cifra que se
                    // paga. Es el corte visual que hace que el ojo salte
                    // directo al total sin leer el resto.
                    agregar('-'.repeat(ancho), { grueso: true });
                    const partes = Array.from(hijo.children).map(textoDe).filter(Boolean);
                    if (partes.length >= 2) {
                        agregar(partes[0], { negrita: true });
                        agregar(partes[partes.length - 1], { destacado: true, derecha: true });
                    } else {
                        agregar(textoDe(hijo), { negrita: true, doble: true });
                    }
                    continue;
                }

                if (tiene('ticket-mesa')) {
                    agregar(textoDe(hijo), { centrado: true, negrita: true, doble: true });
                    continue;
                }

                // "PRE-VENTA" y "NO ES COMPROBANTE DE PAGO": lo que impide que
                // alguien confunda esta hoja con una boleta. Centrado y en
                // negrita a proposito.
                if (tiene('tipo')) {
                    // "PRE-VENTA": lo que impide que alguien confunda esta
                    // hoja con un comprobante. Destacado a proposito.
                    agregar(textoDe(hijo), { centrado: true, negrita: true, doble: true });
                    continue;
                }

                if (tiene('aviso') || tiene('instruccion')) {
                    agregar(textoDe(hijo), { centrado: true, negrita: true });
                    continue;
                }

                if (tiene('comercial')) {
                    // El nombre del negocio es lo primero que identifica la
                    // hoja: va un escalon por encima del resto del
                    // encabezado.
                    agregar(textoDe(hijo), { centrado: true, negrita: true, doble: true });
                    continue;
                }

                // Contenedores: se baja a los hijos para que cada uno reciba
                // su formato, en vez de aplastar todo en una linea.
                if (tiene('ticket-header') || tiene('datos-negocio')) {
                    if (hijo.children.length) { visitar(hijo); continue; }
                    const t = textoDe(hijo);
                    if (t) agregar(t, { centrado: true });
                    continue;
                }

                if (etiqueta === 'H1' || etiqueta === 'H2') {
                    agregar(textoDe(hijo), { centrado: true, negrita: true });
                    continue;
                }

                if (tiene('ticket-meta') || tiene('centro') || tiene('centrado') || tiene('pie')) {
                    if (hijo.children.length) { visitar(hijo); continue; }
                    const t = textoDe(hijo);
                    if (t) agregar(t, { centrado: true });
                    continue;
                }

                if (hijo.children.length) { visitar(hijo); continue; }

                const t = textoDe(hijo);
                if (t) agregar(t);
            }
        };

        visitar(cuerpo);
        return out;
    }

    /** PASO 2a — ESC/POS, para las impresoras de TICKETS. */
    function aEscPos(lineas, ancho) {
        const out = [];
        const push = (arr) => { for (const b of arr) out.push(b); };
        const escribirLinea = (txt) => { push(bytesDeTexto(txt)); out.push(LF); };

        push(INIT);
        for (const l of lineas) {
            const texto = l.izq !== null ? lineaDosColumnas(l.izq, l.der, ancho) : l.texto;
            if (l.centrado) push(ALINEAR.center);
            if (l.negrita) push(NEGRITA(true));
            if (l.doble) push(TAMANO(0x11));
            escribirLinea(texto);
            if (l.doble) push(TAMANO(0x00));
            if (l.negrita) push(NEGRITA(false));
            if (l.centrado) push(ALINEAR.left);
        }
        // Sin este avance el corte cae DENTRO del texto: el cabezal está unos
        // milímetros por encima de la cuchilla.
        push(AVANZAR(4));
        push(CORTAR);
        return out;
    }

    // --- TSPL: impresoras de ETIQUETAS ------------------------------------
    //
    // 203 dpi = 8 puntos por milimetro, que es lo estandar en estas
    // impresoras. La fuente "2" mide ~12x20 puntos.
    const PUNTOS_POR_MM = 8;
    const ANCHO_CARACTER = 12;
    const MARGEN = 24;

    // La barra se arma con su codigo para no depender de como interprete
    // los escapes ninguna herramienta que toque este archivo.
    const BARRA = String.fromCharCode(92);

    /** En TSPL el texto va entre comillas dobles: una comilla sin escapar
     *  dentro del nombre de un plato corta el comando y la etiqueta sale
     *  vacia. */
    function escaparTspl(t) {
        return String(t)
            .split(BARRA).join(BARRA + BARRA)
            .split('"').join(BARRA + '"');
    }

    /**
     * PASO 2b — TSPL, para las impresoras de ETIQUETAS.
     *
     * POR QUE "GAP 0,0" Y NO UN GAP REAL
     * ----------------------------------
     * Con un GAP configurado, la impresora sale a BUSCAR la separacion entre
     * etiquetas antes de imprimir. Si el papel no la tiene —o no coincide con
     * la medida declarada— alimenta papel hasta rendirse y queda trabada con
     * "err: no seam!", que solo se limpia reiniciandola.
     *
     * "GAP 0,0" declara papel CONTINUO: no busca nada y no puede trabarse.
     * Es lo correcto para un ticket, que no son etiquetas troqueladas sino
     * una tira continua.
     *
     * El ALTO se calcula del contenido: en papel continuo la impresora
     * avanza exactamente lo que se le diga, asi que un alto fijo desperdicia
     * papel en los tickets cortos y corta los largos.
     */
    // Fuentes internas de TSPL, con su tamaño real en puntos. Usar fuentes
    // DISTINTAS —y no una sola estirada con multiplicadores— es lo que
    // permite que el importe sea grande sin empujar al texto de al lado, y
    // es lo que le da a la hoja la jerarquía de un comprobante bien hecho.
    const FUENTES = {
        normal: { id: '2', ancho: 12, alto: 20 },
        media:  { id: '3', ancho: 16, alto: 24 },
        grande: { id: '4', ancho: 24, alto: 32 },
    };

    function fuenteDe(l) {
        if (l.destacado) return FUENTES.grande;
        if (l.doble) return FUENTES.media;
        return FUENTES.normal;
    }

    /**
     * LA PLANTILLA — todas las medidas del ticket, en un solo lugar.
     *
     * Antes estos numeros estaban sueltos entre el codigo que arma la hoja, y
     * eso tenia un costo concreto: tocar el aire entre renglones obligaba a
     * encontrar cuatro `y +=` distintos y acordarse de los cuatro. Al cuarto
     * cambio, uno quedaba atras y el ticket salia descuadrado sin que nada lo
     * avisara. Aca se cambia un numero y toda la hoja se reacomoda sola.
     *
     * No hay libreria que hacer esto por nosotros: las que existen en JS
     * (esc-pos-encoder y parecidas) hablan ESC/POS y ninguna emite TSPL, que
     * es lo que necesita una impresora de etiquetas. Sumar uno de esos
     * paquetes agregaria peso al APK sin resolver este caso.
     *
     * Las unidades son PUNTOS de impresora (8 por milimetro).
     */
    const PLANTILLA = {
        // Aire vertical DESPUES de cada renglon, segun su tamano. Que sea
        // proporcional es lo que arregla el "se pega todo": con un valor fijo,
        // una linea en fuente grande recibia el mismo aire que una chica, asi
        // que cuanto mas importante el renglon, mas apretado se veia.
        interlinea: { normal: 14, media: 18, grande: 24 },

        // Hueco entre el concepto y el importe, medido en anchos de caracter.
        // Sin el, aunque no se encimen, las dos columnas se leen como un solo
        // renglon corrido y el ojo no encuentra donde termina el plato.
        huecoColumnas: 3,

        // Una linea divisoria necesita aire de los DOS lados. Con aire solo
        // arriba queda pegada al bloque de abajo y parece subrayarlo.
        separador: { antes: 14, despues: 20, grosorFino: 2, grosorGrueso: 5 },

        // Cuando el importe no entra al lado del plato y baja a su propia
        // linea, va indentado: alineado a la izquierda se confunde con el
        // nombre del siguiente item.
        aireImporteAbajo: 8,

        // Papel en blanco que se saca DESPUES de imprimir, para poder romper
        // la hoja sin llevarse la ultima linea.
        //
        // Va como comando FEED y NO sumado al alto de la etiqueta, y esa
        // diferencia es justamente lo que fallaba antes: agrandar SIZE hace
        // la etiqueta mas larga, pero la barra de corte esta ~12 mm MAS ALLA
        // del cabezal. El papel quedaba dentro de la impresora y la hoja se
        // rompia igual sobre el texto. FEED si mueve el papel de verdad.
        colaCorteMm: 14,

        // Tope de seguridad. Una etiqueta mas larga que el maximo del firmware
        // hace que la impresora alimente papel buscando un final que no llega
        // y termine trabada. Preferimos un ticket recortado a una impresora
        // que hay que apagar en medio del servicio.
        altoMaximoMm: 200,
    };

    function aireDe(f) {
        if (f === FUENTES.grande) return PLANTILLA.interlinea.grande;
        if (f === FUENTES.media) return PLANTILLA.interlinea.media;
        return PLANTILLA.interlinea.normal;
    }

    function aTspl(lineas, ancho) {
        const anchoMm = ancho >= 48 ? 80 : 58;
        const anchoPuntos = anchoMm * PUNTOS_POR_MM;
        const util = anchoPuntos - MARGEN * 2;

        let y = MARGEN;
        const cuerpo = [];

        // El ancho nominal de las fuentes TSPL es una referencia, no una
        // garantia: cada fabricante las dibuja un poco distinto, y algunas
        // agregan espaciado entre caracteres. Si la medida real es mayor que
        // la calculada, el texto de la izquierda se estira y PISA al importe.
        //
        // Como no hay forma de medir la fuente de una impresora concreta
        // desde aca, se mide con un 15% de mas. Sobra un poco de aire cuando
        // la fuente es la nominal, y NO se encima cuando es mas ancha. De los
        // dos errores posibles, ese es el barato.
        const HOLGURA = 1.15;
        const mide = (t, f) => Math.ceil(t.length * f.ancho * HOLGURA);

        const escribir = (x, yy, t, f) =>
            'TEXT ' + x + ',' + yy + ',"' + f.id + '",0,1,1,"' + escaparTspl(t) + '"';

        const recortar = (t, f, disponible) => {
            const cabe = Math.floor(disponible / (f.ancho * HOLGURA));
            return t.length <= cabe ? t : t.slice(0, Math.max(0, cabe - 1));
        };

        for (const l of lineas) {
            const esSeparador = l.izq === null && /^-+$/.test((l.texto || '').trim());
            if (esSeparador) {
                const grosor = l.grueso
                    ? PLANTILLA.separador.grosorGrueso
                    : PLANTILLA.separador.grosorFino;
                y += PLANTILLA.separador.antes;
                cuerpo.push('BAR ' + MARGEN + ',' + y + ',' + util + ',' + grosor);
                y += grosor + PLANTILLA.separador.despues;
                continue;
            }

            // --- Dos columnas: concepto a la izquierda, importe a la derecha.
            if (l.izq !== null) {
                const f = fuenteDe(l);
                const der = sinTildes(l.der || '');
                const izqCompleto = sinTildes(l.izq || '');
                const anchoDer = mide(der, f);
                const xDer = anchoPuntos - MARGEN - anchoDer;

                const HUECO = f.ancho * PLANTILLA.huecoColumnas;
                const disponibleIzq = xDer - MARGEN - HUECO;

                if (mide(izqCompleto, f) <= disponibleIzq) {
                    // Entran en la misma linea, que es lo deseable.
                    if (izqCompleto) cuerpo.push(escribir(MARGEN, y, izqCompleto, f));
                    if (der) cuerpo.push(escribir(xDer, y, der, f));
                    y += f.alto + aireDe(f);
                } else {
                    // No entran: el importe BAJA a su propia linea en vez de
                    // recortar el nombre del plato. Asi el comensal lee que
                    // pidio y cuanto cuesta, completo, y es IMPOSIBLE que se
                    // solapen aunque la fuente real sea mas ancha de lo
                    // calculado.
                    cuerpo.push(escribir(MARGEN, y, recortar(izqCompleto, f, util), f));
                    y += f.alto + PLANTILLA.aireImporteAbajo;
                    if (der) cuerpo.push(escribir(xDer, y, der, f));
                    y += f.alto + aireDe(f);
                }
                continue;
            }

            const t = sinTildes(l.texto);
            if (!t) { y += PLANTILLA.interlinea.normal; continue; }

            // Si no entra, se BAJA de tamaño antes que recortar: el texto
            // completo vale mas que el tamaño con el que se imprime.
            let f = fuenteDe(l);
            if (mide(t, f) > util && f === FUENTES.grande) f = FUENTES.media;
            if (mide(t, f) > util && f === FUENTES.media) f = FUENTES.normal;
            const texto = recortar(t, f, util);

            let x = MARGEN;
            if (l.centrado) x = Math.max(MARGEN, Math.floor((anchoPuntos - mide(texto, f)) / 2));
            else if (l.derecha) x = Math.max(MARGEN, anchoPuntos - MARGEN - mide(texto, f));

            cuerpo.push(escribir(x, y, texto, f));
            y += f.alto + aireDe(f);
        }

        // El alto de la ETIQUETA es exactamente el del contenido. El papel
        // para romper la hoja NO se suma aca — ver PLANTILLA.colaCorteMm: se
        // saca despues con FEED, que es lo unico que mueve el papel mas alla
        // del cabezal hasta la barra de corte.
        let altoMm = Math.ceil((y + MARGEN) / PUNTOS_POR_MM);
        if (altoMm > PLANTILLA.altoMaximoMm) {
            console.warn('[Termica] ticket de', altoMm, 'mm recortado a',
                         PLANTILLA.altoMaximoMm, 'mm');
            altoMm = PLANTILLA.altoMaximoMm;
        }

        const comandos = [
            'SIZE ' + anchoMm + ' mm,' + altoMm + ' mm',
            'GAP 0,0',
            // DIRECTION 0 = de ARRIBA hacia abajo, en el sentido en que sale
            // el papel. Con DIRECTION 1 el contenido va rotado 180 grados: el
            // ticket sale invertido y la impresora avanza toda la etiqueta
            // antes de escribir, tirando papel de mas.
            'DIRECTION 0',
            'REFERENCE 0,0',
            'CLS',
        ].concat(cuerpo).concat([
            'PRINT 1,1',
            // Saca la ultima linea de adentro de la impresora. FEED es una
            // orden de MOTOR pura: no consulta ningun sensor, asi que no
            // puede disparar el "err: no seam!" que si provoca cualquier
            // comando de calibracion o de busqueda de separacion.
            'FEED ' + (PLANTILLA.colaCorteMm * PUNTOS_POR_MM),
        ]);

        // En TSPL cada comando TERMINA en CRLF. Con LF suelto, varias
        // impresoras ignoran la linea entera y no imprimen nada.
        const bytes = [];
        for (const c of comandos) {
            for (let i = 0; i < c.length; i++) bytes.push(c.charCodeAt(i) & 0xFF);
            bytes.push(0x0D);
            bytes.push(0x0A);
        }
        return bytes;
    }

    function convertir(html, ancho, lenguaje) {
        ancho = ancho || anchoActual();
        const lineas = extraerLineas(html, ancho);
        const cfg = configuracion();
        const idioma = lenguaje || (cfg && cfg.lenguaje) || 'escpos';
        return idioma === 'tspl' ? aTspl(lineas, ancho) : aEscPos(lineas, ancho);
    }

    // --- Puente con el plugin nativo -------------------------------------

    function plugin() {
        const P = window.Capacitor && window.Capacitor.Plugins;
        return (P && P.ImpresoraTermica) || null;
    }

    function disponible() {
        return Boolean(plugin());
    }

    async function listarImpresoras() {
        const p = plugin();
        if (!p) return [];
        try {
            const r = await p.listar();
            return (r && r.dispositivos) || [];
        } catch (err) {
            console.warn('[Térmica] No se pudieron listar:', err);
            return [];
        }
    }

    function aBase64(bytes) {
        let s = '';
        for (let i = 0; i < bytes.length; i++) s += String.fromCharCode(bytes[i]);
        return btoa(s);
    }

    async function enviar(cfg, bytes) {
        const p = plugin();
        if (!p) throw new Error('La impresión nativa no está disponible');
        await p.imprimir({
            tipo: cfg.tipo || 'bluetooth',
            destino: cfg.destino,
            datos: aBase64(bytes),
        });
    }

    /**
     * Devuelve true si el ticket salió por la térmica. False significa "acá
     * no se pudo", y print.js cae al camino HTML de siempre — nunca se queda
     * sin imprimir por culpa de esta ruta.
     */
    async function imprimirHTMLenTermica(html) {
        if (!plugin()) return false;

        // Sin esto hay una carrera que se ve como "la impresora imprime
        // basura": tras reinstalar el APK, localStorage arranca vacio y la
        // configuracion vive solo en el almacenamiento NATIVO, que se lee de
        // forma asincrona. Si el mozo cobra antes de que esa lectura termine,
        // configuracion() devuelve null, se cae a la autodeteccion de abajo y
        // se imprime con el lenguaje equivocado. Esperar la restauracion
        // cuesta milisegundos la primera vez y cero las siguientes.
        await asegurarConfiguracion();

        let cfg = configuracion();
        if (!cfg) {
            // Sin configurar: si hay UNA sola emparejada se asume esa, que
            // es el caso del 90% de los locales. Con varias NO se adivina —
            // mandar la comanda a la impresora equivocada es peor que no
            // imprimir.
            const lista = await listarImpresoras();
            if (lista.length === 1) {
                // `lenguaje` va SIEMPRE, aunque sea el default. Omitirlo
                // dejaba cfg.lenguaje en undefined y convertir() caia a
                // ESC/POS: en una impresora de etiquetas eso sale como
                // garabatos, sin ningun error que lo explique.
                cfg = { tipo: 'bluetooth', destino: lista[0].mac, ancho: '80', lenguaje: 'escpos' };
                guardarConfiguracion(cfg);
            } else {
                if (typeof showToast === 'function') {
                    showToast(
                        lista.length > 1
                            ? 'Elegí la impresora en Admin → Impresora'
                            : 'No hay impresora configurada',
                        'warning'
                    );
                }
                return false;
            }
        }

        try {
            // Queda en logcat a proposito: cuando el papel sale con
            // garabatos, lo primero que hay que saber es en que lenguaje se
            // emitio, y eso no se puede deducir mirando la impresora.
            console.log('[Termica] imprimiendo en', cfg.lenguaje, 'ancho', cfg.ancho, 'destino', cfg.destino);
            await enviar(cfg, convertir(html, COLUMNAS[cfg.ancho] || 48, cfg.lenguaje));
            return true;
        } catch (err) {
            console.error('[Térmica] Falló la impresión:', err);
            if (typeof showToast === 'function') {
                showToast('No se pudo imprimir: ' + (err && err.message ? err.message : 'sin respuesta de la impresora'), 'error');
            }
            return false;
        }
    }

    /** Página de prueba, para ajustar el ancho sin tener que cobrar una mesa
     *  de verdad. La regla de columnas es lo que hace obvio si el papel
     *  elegido es el correcto: si se corta o sobra mucho, está mal. */
    async function imprimirPrueba(cfg) {
        const cols = COLUMNAS[cfg.ancho] || 48;
        const regla = Array.from({ length: cols }, (_, i) => String((i + 1) % 10)).join('');
        const html = `<!DOCTYPE html><html><body>
            <div class="ticket-header"><h1>RESTOMIND</h1>
              <div class="ticket-mesa">PRUEBA</div></div>
            <div class="ticket-meta">Papel de ${cfg.ancho} mm · ${cols} columnas</div>
            <table>
              <tr><td class="cant">1x</td><td class="nombre">Si esta regla entra justa,</td><td class="precio">OK</td></tr>
              <tr><td class="cant">2x</td><td class="nombre">el ancho es el correcto</td><td class="precio">OK</td></tr>
            </table>
            <div class="ticket-meta">${regla}</div>
            <div class="ticket-total"><span>TOTAL</span><span>S/ 0.00</span></div>
        </body></html>`;
        await enviar(cfg, convertir(html, cols, cfg.lenguaje));
    }

    /**
     * Prueba de diagnóstico: manda SOLO texto, sin un solo comando ESC/POS.
     *
     * Sirve para separar dos causas que se ven igual (la impresora despierta
     * y no imprime):
     *
     *   - Si ESTO imprime y la prueba normal no, la impresora recibe bien
     *     pero no entiende los comandos ESC/POS — pasa con las impresoras de
     *     ETIQUETAS, que usan otro lenguaje (TSPL/CPCL).
     *   - Si esto tampoco imprime, el problema está antes: en la conexión o
     *     en cómo se le entregan los datos.
     */
    async function imprimirPruebaCruda(cfg) {
        // Se arma byte por byte y el salto de linea se agrega como 0x0A,
        // sin literales de escape: asi el contenido no depende de como
        // interprete los backslash ninguna herramienta intermedia.
        const lineas = [
            'PRUEBA SIMPLE',
            'Sin comandos ESC/POS',
            'Si esto sale impreso,',
            'la impresora recibe bien.',
            '', '', '',
        ];
        const bytes = [];
        for (const l of lineas) {
            for (let i = 0; i < l.length; i++) bytes.push(l.charCodeAt(i) & 0xFF);
            bytes.push(0x0A);
        }
        await enviar(cfg, bytes);
    }

    /**
     * Prueba en TSPL, el lenguaje de las impresoras de ETIQUETAS.
     *
     * Las HiLabel, Niimbot, TSC y parecidas NO entienden ESC/POS: reciben
     * los bytes, no reconocen ningun comando y no hacen nada — exactamente
     * el sintoma de 'despierta pero no imprime'. Si ESTA prueba sale y las
     * otras no, la impresora habla TSPL y hay que emitir en ese lenguaje.
     *
     * En TSPL cada linea TERMINA en CRLF (no solo LF): con LF suelto varias
     * impresoras ignoran el comando entero.
     */
    async function imprimirPruebaEtiqueta(cfg) {
        const comandos = [
            'SIZE 50 mm,30 mm',
            // 0,0 = papel CONTINUO. Con un GAP real la impresora sale a
            // buscar la separacion entre etiquetas, y si el papel no la tiene
            // alimenta hasta trabarse con "err: no seam!", que solo se limpia
            // reiniciandola. Esta prueba lo provoco una vez; no vuelve a
            // declarar un GAP nunca mas.
            'GAP 0,0',
            'DIRECTION 1',
            'CLS',
            'TEXT 20,20,"3",0,1,1,"RESTOMIND"',
            'TEXT 20,70,"2",0,1,1,"PRUEBA TSPL"',
            'TEXT 20,110,"2",0,1,1,"Si esto sale, es TSPL"',
            'PRINT 1,1',
        ];
        const bytes = [];
        for (const c of comandos) {
            for (let i = 0; i < c.length; i++) bytes.push(c.charCodeAt(i) & 0xFF);
            bytes.push(0x0D);
            bytes.push(0x0A);
        }
        await enviar(cfg, bytes);
    }

    window.ImpresoraTermica = {
        disponible: disponible,
        listar: listarImpresoras,
        configuracion: configuracion,
        guardar: guardarConfiguracion,
        anchosPosibles: Object.keys(COLUMNAS),
        imprimirHTML: imprimirHTMLenTermica,
        prueba: imprimirPrueba,
        pruebaCruda: imprimirPruebaCruda,
        pruebaEtiqueta: imprimirPruebaEtiqueta,
        // Se exporta para poder probar la conversión sin impresora.
        _convertir: convertir,
    };

    // --- Pantalla de configuración (Admin → Personal) ---------------------
    // Las funciones van en window porque el HTML las llama por onclick, igual
    // que el resto de la app.

    const OPCION_RED = '__red__';

    function elemento(id) { return document.getElementById(id); }

    /** Rellena el desplegable. Marca las NO emparejadas para que se note
     *  cuáles van a necesitar el paso de emparejamiento antes de imprimir. */
    function pintarLista(lista) {
        const sel = elemento('impresora-destino');
        if (!sel) return;
        const previo = sel.value;
        sel.innerHTML = '';

        for (const d of lista) {
            const o = document.createElement('option');
            o.value = d.mac;
            o.textContent = d.emparejado ? d.nombre : d.nombre + '  (sin emparejar)';
            o.dataset.emparejado = d.emparejado ? 'si' : 'no';
            sel.appendChild(o);
        }

        const oRed = document.createElement('option');
        oRed.value = OPCION_RED;
        oRed.textContent = 'Impresora de red (WiFi / Ethernet)';
        sel.appendChild(oRed);

        if (previo && Array.from(sel.options).some(o => o.value === previo)) sel.value = previo;
        alternarCampoIP();
    }

    async function pintarPantallaImpresora() {
        const tarjeta = elemento('card-impresora');
        if (!tarjeta) return;

        // En el navegador esto no aplica: imprime el diálogo del sistema.
        if (!disponible()) { tarjeta.classList.add('hidden'); return; }
        tarjeta.classList.remove('hidden');

        const selDestino = elemento('impresora-destino');
        const selAncho = elemento('impresora-ancho');
        const hint = elemento('impresora-hint');
        const cfg = configuracion();

        const emparejadas = await listarImpresoras();
        pintarLista(emparejadas.map(d => ({ nombre: d.nombre, mac: d.mac, emparejado: true })));

        if (cfg) {
            selDestino.value = cfg.tipo === 'red' ? OPCION_RED : cfg.destino;
            selAncho.value = cfg.ancho;
            const selLeng = elemento('impresora-lenguaje');
            if (selLeng) selLeng.value = cfg.lenguaje || 'escpos';
            if (cfg.tipo === 'red') elemento('impresora-ip').value = cfg.destino;
        }

        hint.textContent = emparejadas.length
            ? emparejadas.length + ' impresora(s) emparejada(s) en este equipo'
            : 'Ninguna emparejada. Emparejala en Ajustes → Bluetooth del celular.';

        alternarCampoIP();
        selDestino.onchange = alternarCampoIP;
    }

    function alternarCampoIP() {
        const sel = elemento('impresora-destino');
        const grupo = elemento('grupo-impresora-ip');
        if (!sel || !grupo) return;
        grupo.classList.toggle('hidden', sel.value !== OPCION_RED);
    }

    function leerFormulario() {
        const sel = elemento('impresora-destino');
        const porRed = sel.value === OPCION_RED;
        const destino = porRed ? (elemento('impresora-ip').value || '').trim() : sel.value;
        if (!destino) return null;
        const selLeng = elemento('impresora-lenguaje');
        return {
            tipo: porRed ? 'red' : 'bluetooth',
            destino: destino,
            ancho: elemento('impresora-ancho').value,
            lenguaje: selLeng ? selLeng.value : 'escpos',
        };
    }

    window.initPantallaImpresora = pintarPantallaImpresora;

    /**
     * Busca impresoras que todavía NO estén emparejadas.
     *
     * Hace falta porque una impresora se desemparejar sola más seguido de lo
     * que parece: al reiniciarla, al cambiarla de local, o al reinstalar el
     * celular. Cuando eso pasa, `listar()` devuelve vacío y el usuario no
     * tiene forma de saber qué hacer — buscar desde acá lo resuelve sin
     * salir de la app.
     */
    window.buscarImpresoras = async function () {
        const p = plugin();
        if (!p || !p.buscar) return;

        const hint = elemento('impresora-hint');
        const original = hint ? hint.textContent : '';
        if (hint) hint.textContent = 'Buscando… (tarda unos 15 segundos, dejá la impresora encendida)';

        try {
            const r = await p.buscar();
            const lista = (r && r.dispositivos) || [];
            pintarLista(lista);
            if (hint) {
                const nuevas = lista.filter(d => !d.emparejado).length;
                hint.textContent = nuevas
                    ? lista.length + ' encontrada(s), ' + nuevas + ' sin emparejar (elegila y tocá Guardar)'
                    : lista.length + ' impresora(s), todas ya emparejadas';
            }
        } catch (err) {
            if (hint) hint.textContent = original;
            if (typeof showToast === 'function') {
                showToast((err && err.message) || 'No se pudo buscar', 'error');
            }
        }
    };

    /** Empareja si hace falta. Devuelve true si se puede seguir. */
    async function asegurarEmparejada(mac) {
        const sel = elemento('impresora-destino');
        const opcion = sel && Array.from(sel.options).find(o => o.value === mac);
        if (!opcion || opcion.dataset.emparejado !== 'no') return true;

        const p = plugin();
        if (!p || !p.emparejar) return true;
        try {
            if (typeof showToast === 'function') {
                showToast('Emparejando… si pide PIN suele ser 0000 o 1234', 'info');
            }
            await p.emparejar({ mac: mac });
            // createBond es asíncrono del lado del sistema: se le da tiempo
            // al diálogo de Android antes de intentar imprimir.
            await new Promise(r => setTimeout(r, 2500));
            return true;
        } catch (err) {
            if (typeof showToast === 'function') {
                showToast((err && err.message) || 'No se pudo emparejar', 'error');
            }
            return false;
        }
    }

    window.guardarImpresora = async function () {
        const cfg = leerFormulario();
        if (!cfg) {
            if (typeof showToast === 'function') showToast('Elegí una impresora o escribí la IP', 'warning');
            return;
        }
        if (cfg.tipo === 'bluetooth' && !(await asegurarEmparejada(cfg.destino))) return;
        guardarConfiguracion(cfg);
        if (typeof showToast === 'function') showToast('Impresora guardada', 'success');
    };

    window.probarImpresoraEtiqueta = async function () {
        const cfg = leerFormulario();
        if (!cfg) {
            if (typeof showToast === 'function') showToast('Elegi una impresora primero', 'warning');
            return;
        }
        if (cfg.tipo === 'bluetooth' && !(await asegurarEmparejada(cfg.destino))) return;
        try {
            await imprimirPruebaEtiqueta(cfg);
            if (typeof showToast === 'function') showToast('Prueba TSPL enviada', 'success');
        } catch (err) {
            if (typeof showToast === 'function') {
                showToast((err && err.message) || 'No se pudo imprimir', 'error');
            }
        }
    };

    window.probarImpresoraSimple = async function () {
        const cfg = leerFormulario();
        if (!cfg) {
            if (typeof showToast === 'function') showToast('Elegí una impresora primero', 'warning');
            return;
        }
        if (cfg.tipo === 'bluetooth' && !(await asegurarEmparejada(cfg.destino))) return;
        try {
            await imprimirPruebaCruda(cfg);
            if (typeof showToast === 'function') showToast('Prueba simple enviada', 'success');
        } catch (err) {
            if (typeof showToast === 'function') {
                showToast((err && err.message) || 'No se pudo imprimir', 'error');
            }
        }
    };

    window.probarImpresora = async function () {
        const cfg = leerFormulario();
        if (!cfg) {
            if (typeof showToast === 'function') showToast('Elegí una impresora o escribí la IP', 'warning');
            return;
        }
        if (cfg.tipo === 'bluetooth' && !(await asegurarEmparejada(cfg.destino))) return;
        try {
            // Se imprime con lo que hay en el formulario, SIN guardar: así se
            // puede probar un ancho antes de dejarlo fijo.
            await imprimirPrueba(cfg);
            if (typeof showToast === 'function') showToast('Prueba enviada', 'success');
        } catch (err) {
            if (typeof showToast === 'function') {
                showToast(err && err.message ? err.message : 'No se pudo imprimir', 'error');
            }
        }
    };

    document.addEventListener('DOMContentLoaded', function () {
        // Un intento en diferido: el puente de Capacitor puede no estar listo
        // en el mismo tick que el DOM.
        setTimeout(async function () {
            await asegurarConfiguracion();
            pintarPantallaImpresora();
        }, 800);
    });
})();
