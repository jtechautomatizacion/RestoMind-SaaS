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

    /**
     * Interruptor general de impresión, POR APARATO.
     *
     * Separado de `CLAVE_CONFIG` a propósito: son dos preguntas distintas.
     * "¿Este local imprime?" viene ANTES de "¿con cuál impresora?", y apagar
     * la impresión no tiene por qué borrar la impresora ya elegida — el día
     * que se vuelva a prender tiene que seguir andando sin reconfigurar nada.
     *
     * Por aparato y no por cuenta, igual que la impresora: en modo "En
     * equipo" el celular del mozo puede imprimir la comanda y el de caja no,
     * o al revés.
     */
    const CLAVE_IMPRESION = 'restomind_impresion_activa';

    /**
     * Encendido salvo que alguien lo haya apagado a mano.
     *
     * El default NO es una preferencia estética: hoy todos los locales que
     * usan la app imprimen, así que arrancar en apagado los dejaría sin
     * tickets sin que nadie haya tocado nada — el peor tipo de cambio, uno
     * que rompe en silencio algo que funcionaba. El local que no imprime lo
     * apaga una vez y queda apagado para siempre en ese aparato.
     */
    function impresionActiva() {
        try {
            return localStorage.getItem(CLAVE_IMPRESION) !== '0';
        } catch (_) {
            // Sin localStorage (navegación privada, datos bloqueados) se
            // asume que sí: no imprimir es la falla que se nota tarde.
            return true;
        }
    }

    function guardarImpresionActiva(activa) {
        try { localStorage.setItem(CLAVE_IMPRESION, activa ? '1' : '0'); } catch (_) { }
    }

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

                    // --- Estructura que SOLO TSPL sabe dibujar -------------
                    // ESC/POS no tiene recuadros ni columnas posicionadas: es
                    // una maquina de escribir. TSPL si, y el diseno del
                    // ticket en pantalla usa las dos cosas. En vez de tener
                    // dos extractores, el mismo recorrido anota la estructura
                    // y cada emisor toma lo que puede dibujar.
                    c1: null, c2: null, c3: null,   // fila de tres columnas
                    cabeceraTabla: false,
                    cajaInicio: false, cajaFin: false, grosorCaja: 0,

                    // Un renglon que solo tiene sentido en uno de los dos
                    // lenguajes. La regla gruesa antes del total, por ejemplo:
                    // en ESC/POS separa el detalle del importe, pero en TSPL
                    // el recuadro ya hace ese trabajo y la regla quedaria
                    // pegada al borde de la caja.
                    soloGrafico: false, soloTexto: false,
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
                    // El encabezado (Articulo / Cant / Importe) va SOLO en
                    // TSPL. Ahi las columnas estan posicionadas, asi que los
                    // rotulos caen justo encima de sus cifras y la tabla se
                    // lee como la de pantalla. En ESC/POS, que escribe corrido,
                    // gastaria una linea entera para decir algo que ya es
                    // obvio por el contenido — y el papel se paga por metro.
                    const encabezados = Array.from(hijo.querySelectorAll('thead th')).map(textoDe);
                    if (encabezados.length === 3) {
                        agregar(null, {
                            soloGrafico: true, cabeceraTabla: true,
                            c1: encabezados[0], c2: encabezados[1], c3: encabezados[2],
                        });
                    }

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

                        // `izq`/`der` es lo que lee ESC/POS ("2x Ceviche" a la
                        // izquierda, importe a la derecha). `c1/c2/c3` es la
                        // MISMA fila sin aplastar, para que TSPL la ponga en
                        // tres columnas como en pantalla.
                        if (precio) {
                            const extra = { izq: izquierda, der: textoDe(precio) };
                            if (cant && nombre) {
                                extra.c1 = textoDe(nombre);
                                extra.c2 = textoDe(cant).replace(/x$/i, '');
                                extra.c3 = textoDe(precio);
                            }
                            agregar(null, extra);
                        } else if (izquierda) agregar(izquierda);
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

                // Bloque de totales (Sub-Total / IGV / Total Venta).
                //
                // En pantalla cada fila es un flex con space-between: la
                // etiqueta a la izquierda y el importe a la DERECHA, en la
                // MISMA linea. Sin esta regla el bloque caia al caso genarico
                // de "tiene hijos, baja a los hijos" y cada <span> terminaba
                // en su propio renglon, asi:
                //
                //     Sub-Total:
                //     S/ 10.17
                //
                // que es exactamente como salio impreso. En TSPL no se notaba
                // porque ahi los importes van posicionados por coordenadas;
                // aparecio recien al pasar esta impresora a ESC/POS, que
                // escribe corrido.
                if (tiene('totales')) {
                    // Regla que despega el detalle de los importes. Va
                    // `soloTexto` porque en TSPL el recuadro del total ya
                    // cumple esa funcion y la regla quedaria pegada al borde
                    // de la caja — mismo criterio que la barra gruesa de
                    // `ticket-total` mas abajo.
                    agregar('-'.repeat(ancho), { soloTexto: true });
                    for (const fila of Array.from(hijo.children)) {
                        const clasesFila = ' ' + (fila.className || '') + ' ';
                        // La fila del total lleva negrita, pero NO `destacado`:
                        // ese activa el doble ancho, que parte el ancho util a
                        // la mitad y desalinea justo la columna que se quiere
                        // leer de un golpe.
                        const esTotal = clasesFila.indexOf(' total ') >= 0;
                        const partes = Array.from(fila.children).map(textoDe).filter(Boolean);
                        if (partes.length >= 2) {
                            agregar(null, {
                                izq: partes[0],
                                der: partes[partes.length - 1],
                                negrita: esTotal,
                            });
                        } else {
                            const t = textoDe(fila);
                            if (t) agregar(t, { negrita: esTotal });
                        }
                    }
                    continue;
                }

                // TOTAL: el numero que dos personas van a comparar en el
                // mostrador. Va separado y destacado.
                if (tiene('total-caja') || tiene('ticket-total') || tiene('total-grande')) {
                    // Barra gruesa: en ESC/POS es el corte visual que hace que
                    // el ojo salte directo al total. En TSPL no va, porque ahi
                    // el recuadro ya cumple esa funcion y la barra quedaria
                    // pegada contra el borde de la caja.
                    agregar('-'.repeat(ancho), { grueso: true, soloTexto: true });

                    agregar(null, { soloGrafico: true, cajaInicio: true, grosorCaja: 4 });
                    const partes = Array.from(hijo.children).map(textoDe).filter(Boolean);
                    if (partes.length >= 2) {
                        agregar(partes[0], { negrita: true, centrado: true });
                        // Centrado, no a la derecha: es como se ve en pantalla
                        // y es lo que corresponde adentro de un recuadro.
                        agregar(partes[partes.length - 1], { destacado: true, centrado: true });
                    } else {
                        agregar(textoDe(hijo), { negrita: true, doble: true, centrado: true });
                    }
                    agregar(null, { soloGrafico: true, cajaFin: true });
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

                // "ENTREGUE ESTA HOJA EN CAJA" es una ORDEN para el comensal,
                // no un renglon mas del ticket: en pantalla va recuadrada y
                // por eso se ve. Se reproduce igual en el papel.
                if (tiene('instruccion')) {
                    agregar(null, { soloGrafico: true, cajaInicio: true, grosorCaja: 2 });
                    agregar(textoDe(hijo), { centrado: true, negrita: true });
                    agregar(null, { soloGrafico: true, cajaFin: true });
                    continue;
                }

                if (tiene('aviso')) {
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
            // Recuadros y cabeceras de tabla: ESC/POS no sabe posicionar nada,
            // asi que se saltean enteros en vez de salir como una linea suelta
            // y descolgada.
            if (l.soloGrafico) continue;

            const texto = l.izq !== null ? lineaDosColumnas(l.izq, l.der, ancho) : l.texto;
            const agranda = l.doble || l.destacado;
            if (l.centrado) push(ALINEAR.center);
            if (l.negrita) push(NEGRITA(true));
            if (agranda) push(TAMANO(0x11));
            escribirLinea(texto);
            if (agranda) push(TAMANO(0x00));
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

        // Papel en blanco al final del ticket, para poder romper la hoja sin
        // llevarse la ultima linea (la barra de corte esta ~12 mm MAS ALLA
        // del cabezal, asi que sin esta cola la hoja se rompe sobre el texto).
        //
        // VA SUMADO AL ALTO DE LA ETIQUETA, Y NO COMO UN "FEED" DESPUES DEL
        // PRINT. Esto ya se hizo al reves y es la causa del "err: no seam!"
        // que trababa la impresora. Medido en el celular, con la impresora
        // recien reiniciada y dos tickets seguidos:
        //
        //   SIZE = contenido, + FEED despues  -> el 1 sale bien, el 2 se
        //       traba con "no seam" y sale truncado
        //   SIZE = contenido + cola, sin FEED -> 3 seguidos completos, sin
        //       un solo error
        //
        // El motivo: FEED mueve el papel DESPUES de que la etiqueta termino,
        // asi que la impresora queda parada a 14 mm del borde — a mitad de
        // etiqueta. El trabajo siguiente manda SIZE/PRINT y ella, que ya no
        // sabe donde empieza la etiqueta, sale a BUSCAR la separacion; con
        // papel continuo no hay ninguna, alimenta hasta rendirse y se traba.
        // Con la cola adentro del SIZE el papel avanza exactamente lo mismo
        // (se rompe igual), pero termina parada EN el borde de la etiqueta,
        // que es una posicion que si conoce, y no tiene nada que buscar.
        //
        // Por eso un ticket suelto siempre salio perfecto —incluso de 123 mm—
        // y se rompia el segundo de cualquier tanda: el modo "en equipo", que
        // manda comanda + pre-cuenta, era el que lo mostraba siempre.
        //
        // 16 y no 14: la barra de corte esta ~12 mm mas alla del cabezal, asi
        // que con 14 quedaban 2 mm de papel asomando — no alcanza para
        // agarrarlo. Se nota sobre todo en la comanda de cocina, que es el
        // ticket mas corto: la tira entera queda del tamano de un dedo.
        colaCorteMm: 16,

        // Los recuadros: el del TOTAL y el de "ENTREGUE ESTA HOJA EN CAJA".
        // El `padding` es lo que evita que el texto toque el borde, que es
        // exactamente lo que lo hace ver barato.
        caja: { aireAntes: 18, padding: 16, aireDespues: 18 },

        // La tabla de tres columnas, en ANCHOS DE CARACTER de la fuente
        // normal. En caracteres y no en puntos a proposito: asi el mismo
        // numero sirve para 58 y para 80 mm sin recalcular nada.
        // `aireCabecera` es lo que separa el rotulo de su regla; `aireTrasRegla`
        // lo que separa esa regla de la primera fila. Son DISTINTOS a proposito:
        // la regla pertenece a la cabecera, asi que va pegada a ella y despegada
        // de los items. Con un solo valor, la regla queda flotando en el medio y
        // no se entiende a que grupo pertenece.
        tabla: { anchoImporte: 9, anchoCant: 5, aireCabecera: 8, aireTrasRegla: 20 },

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
        // OJO: 80 mm de PAPEL no son 80 mm IMPRIMIBLES.
        //
        // El cabezal de estas termicas cubre 72 mm (576 puntos) en rollo de
        // 80, y 48 mm (384) en rollo de 58; el resto es margen mecanico que
        // el cabezal no alcanza. Posicionar contra los 80 mm del papel no da
        // un error: la impresora ENVUELVE al renglon siguiente lo que cae
        // afuera, asi que "Importe" sale "Impo/rte" y "12.00" sale "12/.0/0".
        //
        // Se midio sobre el papel: cuatro textos distintos cortaron todos
        // entre el punto 574 y el 575. En ESC/POS esto nunca se noto porque
        // ahi la impresora administra su propio ancho — el problema aparece
        // recien cuando uno posiciona por coordenadas, como hace TSPL.
        const anchoMm = ancho >= 48 ? 72 : 48;
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

        // --- La tabla de tres columnas, como en pantalla ------------------
        // Se calculan UNA vez: las tres columnas tienen que quedar alineadas
        // entre la cabecera y todas las filas, y eso no pasa si cada renglon
        // decide su propia posicion.
        const anchoChar = FUENTES.normal.ancho * HOLGURA;
        const xImporteDer = anchoPuntos - MARGEN;
        const xCantDer = xImporteDer - Math.ceil(PLANTILLA.tabla.anchoImporte * anchoChar);
        const finNombre = xCantDer - Math.ceil(PLANTILLA.tabla.anchoCant * anchoChar);
        const anchoNombre = finNombre - MARGEN;
        const aDerecha = (der, t, f) => Math.max(MARGEN, der - mide(t, f));

        // Pila porque los recuadros podrian anidarse algun dia; hoy no lo
        // hacen, pero una variable suelta se rompe en silencio si alguna vez
        // pasa, y una pila no.
        const cajasAbiertas = [];

        // Aire que dejo el ultimo renglon escrito. Se descuenta al cerrar un
        // recuadro: ese aire es separacion HACIA EL SIGUIENTE renglon, y si
        // se deja adentro de la caja el padding de abajo queda casi el doble
        // que el de arriba. Se nota enseguida — la cifra parece apoyada sobre
        // el borde de arriba.
        let aireUltima = 0;

        for (const l of lineas) {
            // Lo que solo tiene sentido en ESC/POS (la regla gruesa que aca
            // reemplaza el recuadro) no se dibuja.
            if (l.soloTexto) continue;

            if (l.cajaInicio) {
                y += PLANTILLA.caja.aireAntes;
                const grosor = l.grosorCaja || 2;
                cajasAbiertas.push({ y: y, grosor: grosor });
                // El grosor se suma al padding: BOX dibuja el marco hacia
                // ADENTRO, asi que sin esto el texto arranca sobre la linea
                // del borde en vez de despues de ella — y cuanto mas grueso
                // el marco, mas encima queda.
                y += grosor + PLANTILLA.caja.padding;
                aireUltima = 0;
                continue;
            }

            if (l.cajaFin) {
                const caja = cajasAbiertas.pop();
                if (caja) {
                    y -= aireUltima;
                    y += PLANTILLA.caja.padding + caja.grosor;
                    cuerpo.push('BOX ' + MARGEN + ',' + caja.y + ','
                                + (anchoPuntos - MARGEN) + ',' + y + ',' + caja.grosor);
                    y += PLANTILLA.caja.aireDespues;
                }
                continue;
            }

            // Adentro de un recuadro el texto se centra contra los bordes de
            // la CAJA, que aca coinciden con los margenes de la hoja.
            if (l.c1 !== null) {
                const f = FUENTES.normal;
                const nombre = recortar(sinTildes(l.c1), f, anchoNombre);
                const cant = sinTildes(l.c2 || '');
                const imp = sinTildes(l.c3 || '');

                cuerpo.push(escribir(MARGEN, y, nombre, f));
                if (cant) cuerpo.push(escribir(aDerecha(xCantDer, cant, f), y, cant, f));
                if (imp) cuerpo.push(escribir(aDerecha(xImporteDer, imp, f), y, imp, f));
                y += f.alto + aireDe(f);
                aireUltima = aireDe(f);

                // La cabecera lleva su regla debajo, como el <th> con
                // border-bottom del ticket en pantalla.
                if (l.cabeceraTabla) {
                    y -= aireDe(f) - PLANTILLA.tabla.aireCabecera;
                    cuerpo.push('BAR ' + MARGEN + ',' + y + ',' + util + ',2');
                    y += 2 + PLANTILLA.tabla.aireTrasRegla;
                }
                continue;
            }

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
                    aireUltima = aireDe(f);
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
                    aireUltima = aireDe(f);
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
            aireUltima = aireDe(f);
        }

        // El alto de la ETIQUETA es el del contenido MAS la cola para romper
        // la hoja. Esos 14 mm van ADENTRO del SIZE, y no despues con un FEED
        // — ver PLANTILLA.colaCorteMm, que explica por que medido en papel.
        let altoMm = Math.ceil((y + MARGEN) / PUNTOS_POR_MM) + PLANTILLA.colaCorteMm;
        if (altoMm > PLANTILLA.altoMaximoMm) {
            console.warn('[Termica] ticket de', altoMm, 'mm recortado a',
                         PLANTILLA.altoMaximoMm, 'mm');
            altoMm = PLANTILLA.altoMaximoMm;
        }

        const comandos = [
            'SIZE ' + anchoMm + ' mm,' + altoMm + ' mm',
            'GAP 0,0',
            // El modo "tear" viene ENCENDIDO de fabrica, y es para etiquetas:
            // al terminar de imprimir adelanta el papel hasta la barra de
            // corte, y antes de la etiqueta siguiente RETROCEDE para alinear
            // el cabezal. Ese retroceso la obliga a verificar donde esta, y
            // verificar —en papel continuo— es buscar una separacion que no
            // existe: alimenta hasta rendirse y queda trabada con
            // "err: no seam!".
            //
            // Encaja con el sintoma que no explicaba nada mas: no falla por
            // el contenido (un ticket suelto siempre sale perfecto, incluso
            // de 123 mm) sino por ACUMULACION de reposicionamientos, y por
            // eso el numero de tickets que aguanta varia entre 2 y 4.
            //
            // Apagarlo es seguro: un firmware que no conozca este SET ignora
            // la linea, y va CRLF-terminada como todas, asi que no puede
            // desincronizar el parser (ver la leccion de la sonda TSPL).
            'SET TEAR OFF',
            // DIRECTION 0 = de ARRIBA hacia abajo, en el sentido en que sale
            // el papel. Con DIRECTION 1 el contenido va rotado 180 grados: el
            // ticket sale invertido y la impresora avanza toda la etiqueta
            // antes de escribir, tirando papel de mas.
            'DIRECTION 0',
            'REFERENCE 0,0',
            'CLS',
        ].concat(cuerpo).concat([
            // PRINT es lo ULTIMO que se manda. Despues no va ningun comando
            // que mueva el papel — ver PLANTILLA.colaCorteMm.
            'PRINT 1,1',
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
        // `lenguaje` viaja al nativo para poder LEER el byte de estado: la
        // sonda y la respuesta son distintas en TSPL y en ESC/POS. Sin esto
        // no hay forma de saber si la impresora está trabada.
        return await p.imprimir({
            tipo: cfg.tipo || 'bluetooth',
            destino: cfg.destino,
            datos: aBase64(bytes),
            lenguaje: cfg.lenguaje || 'escpos',
        });
    }

    /**
     * Pregunta el estado SIN imprimir.
     *
     * Devuelve siempre un objeto (nunca lanza): esta consulta es para
     * DIAGNOSTICAR, así que "no pude ni conectarme" es una respuesta válida y
     * no un error que haya que atrapar en cada llamador.
     */
    async function consultarEstado(cfg) {
        const p = plugin();
        if (!p || !p.estado) {
            return { conecto: false, respondio: false, codigo: -1, estado: 'La app no soporta esta consulta' };
        }
        try {
            return await p.estado({
                tipo: cfg.tipo || 'bluetooth',
                destino: cfg.destino,
                lenguaje: cfg.lenguaje || 'escpos',
            });
        } catch (err) {
            return {
                conecto: false, respondio: false, codigo: -1,
                estado: (err && err.message) || 'No se pudo consultar',
            };
        }
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
            const r = await enviar(cfg, convertir(html, COLUMNAS[cfg.ancho] || 48, cfg.lenguaje));
            // Al imprimir YA NO se sondea el estado (ver trabajar() en el
            // plugin: la sonda metia bytes ajenos delante del documento y en
            // este firmware eso dejaba de imprimir). Queda el registro de que
            // los bytes salieron; el estado se consulta aparte, con el boton.
            console.log('[Termica] documento enviado a la impresora');
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

    window.ImpresoraTermica = {
        disponible: disponible,
        listar: listarImpresoras,
        configuracion: configuracion,
        guardar: guardarConfiguracion,
        anchosPosibles: Object.keys(COLUMNAS),
        imprimirHTML: imprimirHTMLenTermica,
        prueba: imprimirPrueba,
        estado: consultarEstado,
        impresionActiva: impresionActiva,
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

        // NADA PRESELECCIONADO. ESTA LÍNEA ES EL ARREGLO DE UN BUG REAL.
        //
        // Sin este placeholder, el <select> arranca con el PRIMER dispositivo
        // que devuelve Android — que no tiene por qué ser una impresora. En el
        // celular donde se encontró, la lista empezaba con unos auriculares
        // ("KUZLER") y traía también un parlante ("SRS-XB100"): tocar
        // "Imprimir prueba" mandaba los bytes al parlante, no salía papel, y
        // no había ningún error. El síntoma era "la impresora no responde para
        // nada", que manda a revisar la impresora en vez de la selección.
        //
        // Con el placeholder, si nadie eligió, leerFormulario() devuelve null
        // y el usuario recibe "Elegí una impresora" — que es la verdad.
        const oVacia = document.createElement('option');
        oVacia.value = '';
        oVacia.textContent = '— Elegí la impresora —';
        sel.appendChild(oVacia);

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
        selDestino.onchange = function () {
            alternarCampoIP();
            sugerirLenguaje(selDestino, Boolean(cfg));
        };
        // También al abrir la pantalla: si todavía no hay nada guardado, el
        // desplegable ya aparece con el lenguaje que le corresponde a la
        // impresora elegida, en vez de con el que venía por defecto.
        sugerirLenguaje(selDestino, Boolean(cfg));
    }

    // Marcas cuyas impresoras son de ETIQUETAS y hablan TSPL, no ESC/POS.
    const MARCAS_ETIQUETA = /hilebel|hi-?label|niimbot|phomemo|tsc|zebra|godex|argox|brother\s*ql|xprinter\s*d/i;

    /**
     * Preselecciona el lenguaje según la impresora elegida.
     *
     * POR QUÉ HACE FALTA
     * ------------------
     * Una de etiquetas NO entiende ESC/POS: recibe los bytes, no reconoce
     * ningún comando y no hace nada. El síntoma es el peor posible — "la
     * impresora despierta y no imprime" — porque no hay error en ninguna
     * parte: ni en la app, ni en el papel.
     *
     * Ya pasó dos veces en este proyecto. La segunda fue al instalar la app
     * de pruebas, que por tener otro applicationId arranca con almacenamiento
     * propio: la impresora quedó guardada como ESC/POS y no imprimía nada, sin
     * ninguna pista de por qué.
     *
     * OJO — EL NOMBRE NO ALCANZA PARA DECIDIR, Y ACÁ ESTÁ EL POR QUÉ
     * -------------------------------------------------------------
     * Varias de estas tienen un MODO en su propio menú, y el modo —no la
     * marca— es lo que define el lenguaje:
     *
     *   Label Mode   -> ejecuta TSPL; en ESC/POS no imprime nada
     *   Receipt Mode -> ejecuta ESC/POS; el TSPL lo saca IMPRESO COMO TEXTO
     *                   ("SIZE 72 mm,103 mm", "BOX 24,254,...", renglón por
     *                   renglón), que es su síntoma característico
     *
     * Una HiLabel en Receipt Mode necesita ESC/POS, justo lo contrario de lo
     * que sugiere su nombre. Esto se descubrió peleando un "err: no seam!"
     * (ver CLAUDE.md): en Label Mode el TSPL funcionaba pero la impresora se
     * trababa buscando la separación entre etiquetas en un rollo continuo, y
     * al pasarla a Receipt Mode dejó de trabarse pero empezó a imprimir el
     * código en crudo. Estuvimos horas con el modo y el lenguaje cruzados.
     *
     * Es una SUGERENCIA, no una imposición: solo actúa cuando el usuario
     * todavía no eligió nada, y el desplegable queda disponible para
     * corregirla. Acertar la mayoría de las veces sin quitarle la decisión a
     * nadie — y si el papel sale con comandos impresos, el arreglo es cambiar
     * ese desplegable, no tocar código.
     */
    function sugerirLenguaje(selDestino, yaHayConfiguracion) {
        // Si ya guardó una configuración, su elección manda: no se le cambia
        // el lenguaje por debajo a alguien que ya lo dejó andando.
        if (yaHayConfiguracion) return;
        const selLeng = elemento('impresora-lenguaje');
        if (!selLeng || !selDestino) return;

        const opcion = selDestino.options[selDestino.selectedIndex];
        const nombre = opcion ? opcion.textContent : '';
        if (MARCAS_ETIQUETA.test(nombre)) selLeng.value = 'tspl';
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
     * El modal de impresora, que se abre desde el header con CUALQUIER rol.
     *
     * POR QUÉ NO ESTÁ EN UNA PESTAÑA
     * ------------------------------
     * Las pestañas se reparten por rol (ROLES_PERMITIDOS en app.js) y esta
     * tarjeta vivía dentro de Admin, que solo ve el dueño. Pero la impresora
     * es del DISPOSITIVO, no de la cuenta: se guarda en este celular. En modo
     * "En equipo" el mozo trabaja desde su propio teléfono y mozo.js le manda
     * la comanda a imprimir al enviar el pedido — así que necesitaba elegir
     * impresora y no tenía ninguna pantalla donde hacerlo. Quedaba sin poder
     * imprimir, y sin forma de arreglarlo desde su cuenta.
     */
    window.abrirModalImpresora = function () {
        const modal = elemento('modal-impresora');
        if (!modal) return;
        modal.classList.remove('hidden');
        // Se repinta CADA VEZ que se abre, no una sola al arrancar: la lista de
        // impresoras emparejadas cambia desde los ajustes del sistema, fuera de
        // esta app, y con una lista vieja el usuario elige algo que ya no está.
        sincronizarSwitchImpresion();
        // Qué estaciones atiende este aparato (cola-impresion.js). Mismo
        // motivo que el switch: la configuración vive en el aparato y pudo
        // cambiarse antes de abrir esta pantalla.
        if (typeof sincronizarEstaciones === 'function') sincronizarEstaciones();
        pintarPantallaImpresora();
    };

    /**
     * El interruptor general de impresión de ESTE aparato.
     *
     * No toca la impresora elegida: apagar y volver a prender tiene que dejar
     * todo como estaba, sin reconfigurar nada (ver CLAVE_IMPRESION).
     */
    window.onToggleImprimir = function (evento) {
        const activa = Boolean(evento && evento.target && evento.target.checked);
        guardarImpresionActiva(activa);
        sincronizarSwitchImpresion();
        if (typeof showToast === 'function') {
            showToast(
                activa
                    ? 'Este equipo va a imprimir los tickets'
                    : 'Impresión apagada en este equipo',
                activa ? 'success' : 'warning',
            );
        }
    };

    /** Deja el switch y su texto de ayuda acordes con lo guardado. Se llama al
     *  abrir el modal y al togglear: el estado vive en el aparato, así que dos
     *  pestañas abiertas no pueden desincronizarse, pero sí puede haberse
     *  cambiado antes de abrir esta pantalla. */
    function sincronizarSwitchImpresion() {
        const activa = impresionActiva();
        const sw = elemento('switch-imprimir');
        if (sw) sw.checked = activa;

        const hint = elemento('impresion-switch-hint');
        if (hint) {
            hint.textContent = activa
                ? 'Encendido. Elegí abajo con qué impresora.'
                : 'Apagado: este equipo no imprime nada y no avisa nada.';
        }
        // Con la impresión apagada, elegir impresora no hace nada. Se atenúa
        // en vez de ocultarse: escondido, el usuario no entiende adónde se
        // fue la configuración que acaba de dejar hecha.
        const card = elemento('card-impresora');
        if (card) card.classList.toggle('apagado', !activa);
    }

    window.cerrarModalImpresora = function () {
        const modal = elemento('modal-impresora');
        if (modal) modal.classList.add('hidden');
    };

    /** Muestra el botón del header solo en la app instalada. */
    function mostrarBotonImpresora() {
        const btn = elemento('btn-impresora');
        if (btn) btn.classList.toggle('hidden', !disponible());
    }
    window.mostrarBotonImpresora = mostrarBotonImpresora;

    /**
     * Busca impresoras que todavía NO estén emparejadas.
     *
     * Hace falta porque una impresora se desemparejar sola más seguido de lo
     * que parece: al reiniciarla, al cambiarla de local, o al reinstalar el
     * celular. Cuando eso pasa, `listar()` devuelve vacío y el usuario no
     * tiene forma de saber qué hacer — buscar desde acá lo resuelve sin
     * salir de la app.
     */
    /**
     * Abre y cierra el panel de configuración de la impresora.
     *
     * Existe porque abierto empujaba "Nueva cuenta" fuera de la pantalla en un
     * celular, y el admin no encontraba dónde dar de alta a su mozo. La
     * impresora se configura una vez; las cuentas se crean seguido.
     *
     * El estado va en aria-expanded y no en una clase propia: el CSS gira la
     * flecha leyendo ese mismo atributo, así que no hay dos fuentes de verdad
     * que puedan quedar desincronizadas — y de paso un lector de pantalla
     * anuncia bien si está abierto o cerrado.
     */
    window.togglePanelImpresora = function () {
        const cabecera = document.querySelector('.plegable-cabecera[aria-controls="panel-impresora"]');
        const panel = document.getElementById('panel-impresora');
        if (!cabecera || !panel) return;
        const abierto = panel.classList.toggle('hidden') === false;
        cabecera.setAttribute('aria-expanded', abierto ? 'true' : 'false');
    };

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



    /**
     * "Estado de la impresora" — verifica sin gastar papel.
     *
     * POR QUÉ EXISTE
     * --------------
     * Antes, la única forma de saber si la impresora estaba respondiendo era
     * mandarle un ticket y mirar si salía papel. Y cuando no salía, no había
     * ninguna pista: la app registraba "enviados 888/888 bytes" tanto con la
     * impresora sana como trabada. Este botón pregunta y muestra la respuesta
     * cruda, así "no imprime" deja de ser un callejón sin salida.
     */
    window.verEstadoImpresora = async function () {
        const cfg = leerFormulario();
        const hint = elemento('impresora-hint');
        if (!cfg) {
            if (typeof showToast === 'function') showToast('Elegí una impresora o escribí la IP', 'warning');
            return;
        }

        if (hint) hint.textContent = 'Consultando a la impresora…';

        const r = await consultarEstado(cfg);

        // NADA de codigos en pantalla. El que lee esto es el dueño del
        // restaurante: "codigo 0x0" no le dice nada y le hace dudar de si
        // algo anda mal justo cuando el mensaje dice que esta todo bien. El
        // valor crudo igual queda en el log de abajo, que es donde sirve.
        let texto;
        let tono;
        if (!r.conecto) {
            texto = 'No se pudo conectar con la impresora. ¿Esta encendida y cerca?';
            tono = 'error';
        } else if (!r.respondio) {
            texto = 'Conectada, pero este modelo no informa su estado. Si no sale papel, apagala y prendela.';
            tono = 'warning';
        } else if (r.motivo) {
            // Ya viene accionable y en castellano desde el plugin
            // ("El cabezal de la impresora esta abierto.").
            texto = r.motivo;
            tono = 'error';
        } else {
            texto = 'Lista para imprimir';
            tono = 'success';
        }

        // El texto queda FIJO en la pantalla, no solo en un toast: un toast se
        // va en tres segundos y esto es justo lo que el dueño va a querer
        // releer mientras revisa la impresora.
        if (hint) hint.textContent = texto;
        if (typeof showToast === 'function') showToast(texto, tono);

        // Acá SÍ va el codigo crudo. Es lo que permite diagnosticar un modelo
        // que contesta algo fuera del estandar, y en logcat no le ensucia la
        // pantalla a nadie.
        console.log('[Termica] estado: codigo=0x'
            + (r.codigo >= 0 ? Number(r.codigo).toString(16) : '?'),
            'conecto=' + r.conecto, 'respondio=' + r.respondio, r.estado);
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
            // El aviso NOMBRA el lenguaje que se usó, y eso es lo importante.
            //
            // "Prueba enviada" a secas es inútil justo cuando más se necesita:
            // si no sale papel, el usuario se queda sin saber qué probar. Una
            // de etiquetas alimentada con ESC/POS no imprime NADA y tampoco da
            // error — ni en la app ni en el papel. Nombrando el lenguaje, un
            // callejón sin salida se convierte en una decisión de dos opciones.
            if (typeof showToast === 'function') {
                const comoSe = cfg.lenguaje === 'tspl' ? 'etiquetas (TSPL)' : 'tickets (ESC/POS)';
                showToast(`Prueba enviada como ${comoSe}. Si no salió nada, cambiá el tipo de impresora.`, 'success');
            }
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
            mostrarBotonImpresora();
            sincronizarSwitchImpresion();
            pintarPantallaImpresora();
        }, 800);
    });
})();
