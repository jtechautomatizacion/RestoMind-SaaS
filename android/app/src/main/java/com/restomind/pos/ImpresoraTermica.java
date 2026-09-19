package com.restomind.pos;

import android.Manifest;
import android.bluetooth.BluetoothAdapter;
import android.bluetooth.BluetoothDevice;
import android.bluetooth.BluetoothManager;
import android.bluetooth.BluetoothSocket;
import android.content.Context;
import android.content.Intent;
import android.os.Build;
import android.util.Base64;

import com.getcapacitor.JSArray;
import com.getcapacitor.JSObject;
import com.getcapacitor.PermissionState;
import com.getcapacitor.Plugin;
import com.getcapacitor.PluginCall;
import com.getcapacitor.PluginMethod;
import com.getcapacitor.annotation.CapacitorPlugin;
import com.getcapacitor.annotation.Permission;
import com.getcapacitor.annotation.PermissionCallback;

import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.lang.reflect.Method;
import java.net.InetSocketAddress;
import java.net.Socket;
import java.net.SocketTimeoutException;
import java.util.Set;
import java.util.UUID;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

/**
 * Impresión ESC/POS sobre Bluetooth Clásico (SPP).
 *
 * POR QUÉ NO SE USA UN PLUGIN DE BLUETOOTH LE
 * -------------------------------------------
 * Las térmicas de 80 mm como la ADV-9026 hablan Bluetooth CLÁSICO por el
 * perfil SPP, no Bluetooth Low Energy. Los plugins de la comunidad
 * (bluetooth-le y compañía) solo manejan BLE: con esta impresora ni
 * siquiera la encuentran. De ahí que haya código nativo acá.
 *
 * POR QUÉ ESTÁ EN JAVA Y NO EN KOTLIN
 * -----------------------------------
 * Capacitor genera el proyecto Android solo con Java. Sumar Kotlin por un
 * archivo arrastra su runtime al APK (~1,5 MB) — más peso que todo el
 * frontend empaquetado.
 *
 * El contenido del ticket llega ya convertido a bytes ESC/POS desde
 * frontend/js/impresora-termica.js. Esta clase NO sabe qué imprime: recibe
 * bytes y los empuja por el socket. Armar el ticket acá obligaría a
 * mantener dos versiones del mismo documento, una en JS y otra en Java.
 */
@CapacitorPlugin(
    name = "ImpresoraTermica",
    permissions = {
        // Declarar el permiso en el manifest NO alcanza desde Android 12:
        // hay que PEDIRLO, y hasta que el usuario acepte, getBondedDevices()
        // devuelve una lista VACÍA en vez de fallar. El síntoma es "no
        // aparece ninguna impresora", que manda a revisar el Bluetooth del
        // celular en vez del permiso de la app.
        @Permission(alias = ImpresoraTermica.PERMISO_BT, strings = { Manifest.permission.BLUETOOTH_CONNECT }),
        // Buscar dispositivos nuevos es un permiso DISTINTO de conectarse a
        // los ya emparejados. Sin este, startDiscovery() no encuentra nada.
        @Permission(alias = ImpresoraTermica.PERMISO_SCAN, strings = { Manifest.permission.BLUETOOTH_SCAN })
    }
)
public class ImpresoraTermica extends Plugin {

    static final String PERMISO_BT = "bluetooth";
    static final String PERMISO_SCAN = "escaneo";

    // La búsqueda de Android dura ~12 s y avisa cuando termina. Este tope es
    // solo una red por si el evento de fin no llega (pasa en algunos
    // fabricantes): sin él, el botón "Buscar" quedaría girando para siempre.
    private static final long TOPE_BUSQUEDA_MS = 16000;

    // UUID estándar del perfil Serial Port. Es el mismo para todas las
    // térmicas de este tipo; no es un valor propio de la ADV-9026.
    private static final UUID SPP = UUID.fromString("00001101-0000-1000-8000-00805F9B34FB");

    // El I/O de Bluetooth BLOQUEA. Hacerlo en el hilo principal congela la
    // interfaz y, si la impresora está apagada, Android muestra el diálogo
    // de "la aplicación no responde" justo cuando el cajero está cobrando.
    private final ExecutorService hilo = Executors.newSingleThreadExecutor();

    private BluetoothAdapter adaptador() {
        Context ctx = getContext();
        BluetoothManager manager = (BluetoothManager) ctx.getSystemService(Context.BLUETOOTH_SERVICE);
        return manager != null ? manager.getAdapter() : null;
    }

    /**
     * Android 12+ exige BLUETOOTH_CONNECT en tiempo de ejecución. Antes de
     * ese Android el permiso es "normal" (se concede al instalar) y no hay
     * nada que pedir.
     */
    private boolean faltaPermiso() {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.S) return false;
        return getPermissionState(PERMISO_BT) != PermissionState.GRANTED;
    }

    /**
     * Vuelve acá cuando el usuario contesta el diálogo del sistema, y
     * reanuda la llamada que lo disparó.
     *
     * Sin este rebote habría que pedirle al usuario que toque el botón otra
     * vez después de aceptar — una fricción que en una caja, con gente
     * esperando, se traduce en "no funciona".
     */
    @PermissionCallback
    private void trasPedirPermiso(PluginCall call) {
        if (faltaPermiso()) {
            call.reject("Sin el permiso de Bluetooth no se puede usar la impresora");
            return;
        }
        String metodo = call.getMethodName();
        if ("imprimir".equals(metodo)) imprimir(call);
        else if ("buscar".equals(metodo)) buscar(call);
        else if ("emparejar".equals(metodo)) emparejar(call);
        else listar(call);
    }

    @PluginMethod
    public void listar(PluginCall call) {
        if (faltaPermiso()) {
            requestPermissionForAlias(PERMISO_BT, call, "trasPedirPermiso");
            return;
        }

        BluetoothAdapter adapter = adaptador();
        if (adapter == null) { call.reject("Este dispositivo no tiene Bluetooth"); return; }
        if (!adapter.isEnabled()) { call.reject("El Bluetooth está apagado"); return; }

        JSArray lista = new JSArray();
        try {
            Set<BluetoothDevice> emparejados = adapter.getBondedDevices();
            for (BluetoothDevice d : emparejados) {
                JSObject item = new JSObject();
                String nombre = d.getName();
                item.put("nombre", nombre != null ? nombre : d.getAddress());
                item.put("mac", d.getAddress());
                lista.put(item);
            }
        } catch (SecurityException e) {
            call.reject("Falta el permiso de Bluetooth");
            return;
        }

        JSObject r = new JSObject();
        r.put("dispositivos", lista);
        call.resolve(r);
    }

    /**
     * Busca impresoras Bluetooth que NO estén emparejadas todavía.
     *
     * `listar()` solo devuelve las ya emparejadas, y emparejar es una
     * operación del sistema. El problema práctico: si la impresora se
     * desemparejó —pasa al reiniciarla, o al cambiarla de local— el usuario
     * abre la app, no ve nada, y no tiene forma de saber qué hacer. Esto le
     * permite encontrarla desde acá.
     *
     * Devuelve las encontradas junto con las ya emparejadas, marcadas, para
     * que la pantalla muestre una sola lista.
     */
    @PluginMethod
    public void buscar(final PluginCall call) {
        if (getPermissionState(PERMISO_SCAN) != PermissionState.GRANTED || faltaPermiso()) {
            requestPermissionForAlias(PERMISO_SCAN, call, "trasPedirPermiso");
            return;
        }

        final BluetoothAdapter adapter = adaptador();
        if (adapter == null) { call.reject("Este dispositivo no tiene Bluetooth"); return; }
        if (!adapter.isEnabled()) { call.reject("El Bluetooth está apagado"); return; }

        final JSArray encontrados = new JSArray();
        final java.util.Set<String> vistos = new java.util.HashSet<>();

        // Las ya emparejadas van primero: son las más probables, y así la
        // lista no "salta" mientras van apareciendo las nuevas.
        try {
            for (BluetoothDevice d : adapter.getBondedDevices()) {
                encontrados.put(dispositivoJSON(d, true));
                vistos.add(d.getAddress());
            }
        } catch (SecurityException ignored) { }

        // Un solo lugar que cierra la búsqueda, y una bandera para que no se
        // cierre dos veces: el fin puede llegar por el evento del sistema O
        // por el tope de tiempo, y resolver la misma PluginCall dos veces
        // rompe el puente de Capacitor.
        final boolean[] yaTermino = { false };
        final android.content.BroadcastReceiver[] ref = new android.content.BroadcastReceiver[1];

        final Runnable cerrar = new Runnable() {
            @Override
            public void run() {
                if (yaTermino[0]) return;
                yaTermino[0] = true;
                try { getContext().unregisterReceiver(ref[0]); } catch (Exception ignored) { }
                try { adapter.cancelDiscovery(); } catch (Exception ignored) { }
                JSObject r = new JSObject();
                r.put("dispositivos", encontrados);
                call.resolve(r);
            }
        };

        ref[0] = new android.content.BroadcastReceiver() {
            @Override
            public void onReceive(Context ctx, Intent intent) {
                String accion = intent.getAction();
                if (BluetoothDevice.ACTION_FOUND.equals(accion)) {
                    BluetoothDevice d = intent.getParcelableExtra(BluetoothDevice.EXTRA_DEVICE);
                    if (d != null && !vistos.contains(d.getAddress())) {
                        vistos.add(d.getAddress());
                        encontrados.put(dispositivoJSON(d, false));
                    }
                } else if (BluetoothAdapter.ACTION_DISCOVERY_FINISHED.equals(accion)) {
                    cerrar.run();
                }
            }
        };

        android.content.IntentFilter filtro = new android.content.IntentFilter();
        filtro.addAction(BluetoothDevice.ACTION_FOUND);
        filtro.addAction(BluetoothAdapter.ACTION_DISCOVERY_FINISHED);
        // RECEIVER_NOT_EXPORTED es obligatorio desde Android 13: sin la
        // bandera, registrar el receptor lanza SecurityException y la app se
        // cae justo al tocar "Buscar".
        if (Build.VERSION.SDK_INT >= 33) {
            getContext().registerReceiver(ref[0], filtro, Context.RECEIVER_NOT_EXPORTED);
        } else {
            getContext().registerReceiver(ref[0], filtro);
        }

        try {
            adapter.cancelDiscovery();
            if (!adapter.startDiscovery()) { cerrar.run(); return; }
        } catch (SecurityException e) {
            cerrar.run();
            return;
        }

        new android.os.Handler(android.os.Looper.getMainLooper())
                .postDelayed(cerrar, TOPE_BUSQUEDA_MS);
    }

    private JSObject dispositivoJSON(BluetoothDevice d, boolean emparejado) {
        JSObject o = new JSObject();
        String nombre = null;
        try { nombre = d.getName(); } catch (SecurityException ignored) { }
        o.put("nombre", nombre != null && !nombre.isEmpty() ? nombre : d.getAddress());
        o.put("mac", d.getAddress());
        o.put("emparejado", emparejado);
        return o;
    }

    /**
     * Dispara el emparejamiento del sistema. Android muestra su propio
     * diálogo (a veces pide un PIN, que en estas impresoras suele ser 0000 o
     * 1234 y está impreso en la etiqueta del equipo).
     */
    @PluginMethod
    public void emparejar(PluginCall call) {
        String mac = call.getString("mac");
        if (mac == null || mac.isEmpty()) { call.reject("Falta la impresora"); return; }
        if (faltaPermiso()) {
            requestPermissionForAlias(PERMISO_BT, call, "trasPedirPermiso");
            return;
        }
        try {
            BluetoothAdapter adapter = adaptador();
            if (adapter == null) { call.reject("Este dispositivo no tiene Bluetooth"); return; }
            adapter.cancelDiscovery();
            BluetoothDevice d = adapter.getRemoteDevice(mac);
            if (d.getBondState() == BluetoothDevice.BOND_BONDED) { call.resolve(); return; }
            if (!d.createBond()) { call.reject("No se pudo iniciar el emparejamiento"); return; }
            call.resolve();
        } catch (Exception e) {
            call.reject(mensajeUtil(e));
        }
    }

    /**
     * Abre los ajustes de Bluetooth del sistema.
     *
     * Este plugin solo ve dispositivos YA EMPAREJADOS — emparejar es una
     * operación del sistema operativo, no de la app. Sin esto, cuando la
     * lista sale vacía el usuario queda sin saber qué hacer; con esto llega
     * a la pantalla correcta de un toque y vuelve con la impresora
     * emparejada.
     */
    @PluginMethod
    public void abrirAjustesBluetooth(PluginCall call) {
        try {
            Intent i = new Intent(android.provider.Settings.ACTION_BLUETOOTH_SETTINGS);
            i.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
            getContext().startActivity(i);
            call.resolve();
        } catch (Exception e) {
            call.reject("No se pudieron abrir los ajustes de Bluetooth");
        }
    }

    @PluginMethod
    public void imprimir(final PluginCall call) {
        // "destino" es una MAC para bluetooth, o "ip" / "ip:puerto" para red.
        final String destino = call.getString("destino");
        final String tipo = call.getString("tipo", "bluetooth");
        final String datos = call.getString("datos");
        // Para leer el byte de estado hace falta saber en qué lenguaje
        // contesta. NO rompe la regla de la cabecera de este archivo: la
        // clase sigue sin saber QUÉ imprime (el documento lo arma el JS);
        // preguntar "¿estás lista?" es transporte, no formato.
        final String lenguaje = call.getString("lenguaje", "escpos");

        if (destino == null || destino.isEmpty() || datos == null || datos.isEmpty()) {
            call.reject("Faltan la impresora o el contenido");
            return;
        }
        // Una impresora de red no necesita Bluetooth; solo se pide el
        // permiso cuando de verdad hace falta.
        if (!"red".equals(tipo) && faltaPermiso()) {
            requestPermissionForAlias(PERMISO_BT, call, "trasPedirPermiso");
            return;
        }

        hilo.execute(new Runnable() {
            @Override
            public void run() {
                try {
                    byte[] bytes = Base64.decode(datos, Base64.DEFAULT);
                    Sondeo s = "red".equals(tipo)
                            ? enviarPorRed(destino, bytes, lenguaje)
                            : enviarPorBluetooth(destino, bytes, lenguaje);
                    JSObject r = new JSObject();
                    // Se devuelve lo que contestó la impresora para que la app
                    // pueda distinguir "imprimió" de "se enviaron los bytes y
                    // nadie confirmó nada" — que hasta ahora eran lo mismo.
                    r.put("confirmado", s.respondio);
                    r.put("estado", s.descripcion);
                    call.resolve(r);
                } catch (Exception e) {
                    call.reject(mensajeUtil(e));
                }
            }
        });
    }

    /**
     * Consulta el estado SIN imprimir nada.
     *
     * Existe para que el dueño pueda verificar la impresora sin cobrar una
     * mesa de prueba: hasta ahora la única forma de saber si respondía era
     * mandarle un ticket y mirar el papel.
     */
    @PluginMethod
    public void estado(final PluginCall call) {
        final String destino = call.getString("destino");
        final String tipo = call.getString("tipo", "bluetooth");
        final String lenguaje = call.getString("lenguaje", "escpos");

        if (destino == null || destino.isEmpty()) { call.reject("Falta la impresora"); return; }
        if (!"red".equals(tipo) && faltaPermiso()) {
            requestPermissionForAlias(PERMISO_BT, call, "trasPedirPermiso");
            return;
        }

        hilo.execute(new Runnable() {
            @Override
            public void run() {
                JSObject r = new JSObject();
                try {
                    Sondeo s = "red".equals(tipo)
                            ? enviarPorRed(destino, null, lenguaje)
                            : enviarPorBluetooth(destino, null, lenguaje);
                    r.put("conecto", true);
                    r.put("respondio", s.respondio);
                    r.put("codigo", s.codigo);
                    r.put("estado", s.descripcion);
                    r.put("motivo", s.motivo == null ? "" : s.motivo);
                } catch (Exception e) {
                    // Una consulta de diagnóstico NO se rechaza: "no pude ni
                    // conectarme" es justamente uno de los resultados que se
                    // quieren ver en pantalla.
                    r.put("conecto", false);
                    r.put("respondio", false);
                    r.put("codigo", -1);
                    r.put("estado", mensajeUtil(e));
                    r.put("motivo", mensajeUtil(e));
                }
                call.resolve(r);
            }
        });
    }

    /** Lo que contestó la impresora a la sonda de estado. */
    private static class Sondeo {
        boolean respondio = false;
        int codigo = -1;
        String descripcion = "sin respuesta";
        String motivo = null;     // != null => no se debe imprimir
    }

    /** `bytes == null` significa "solo sondear, no imprimir". */
    private Sondeo enviarPorBluetooth(String mac, byte[] bytes, String lenguaje) throws Exception {
        BluetoothSocket socket = null;
        try {
            BluetoothAdapter adapter = adaptador();
            if (adapter == null) throw new IOException("Sin Bluetooth");
            if (!adapter.isEnabled()) throw new IOException("El Bluetooth está apagado");

            BluetoothDevice device = adapter.getRemoteDevice(mac);

            // El descubrimiento y una conexión saliente compiten por la
            // radio: si quedó una búsqueda corriendo, connect() falla con un
            // error que no dice nada.
            try { adapter.cancelDiscovery(); } catch (SecurityException ignored) { }

            socket = conectar(device);
            return trabajar(socket.getOutputStream(), socket.getInputStream(), bytes, lenguaje);
        } finally {
            if (socket != null) {
                try { socket.close(); } catch (IOException ignored) { }
            }
        }
    }

    /**
     * Impresora de red (Ethernet o WiFi). Es lo habitual en las fijas de
     * mostrador: hablan el MISMO ESC/POS, pero por un socket TCP en el
     * puerto 9100 (RAW/JetDirect) en vez de Bluetooth. Soportarlas cuesta
     * este método y cubre todo un tipo de impresora que por Bluetooth no
     * aparecería nunca.
     */
    private Sondeo enviarPorRed(String destino, byte[] bytes, String lenguaje) throws Exception {
        String host = destino;
        int puerto = 9100;
        int sep = destino.lastIndexOf(':');
        if (sep > 0) {
            host = destino.substring(0, sep);
            try { puerto = Integer.parseInt(destino.substring(sep + 1)); } catch (NumberFormatException ignored) { }
        }

        Socket socket = new Socket();
        try {
            // Timeout corto y explícito: sin él, una IP equivocada deja al
            // cajero mirando la pantalla ~2 minutos antes de que el sistema
            // se dé por vencido.
            socket.connect(new InetSocketAddress(host, puerto), 6000);
            return trabajar(socket.getOutputStream(), socket.getInputStream(), bytes, lenguaje);
        } finally {
            try { socket.close(); } catch (IOException ignored) { }
        }
    }

    /**
     * Sondea el estado y, si se puede, imprime.
     *
     * POR QUÉ SE SONDEA ANTES Y NO DESPUÉS
     * ------------------------------------
     * Un write() sobre un socket SPP tiene éxito mientras el enlace RFCOMM
     * esté vivo, y eso NO significa que el firmware procesó nada: una
     * impresora trabada mantiene el enlace abierto y descarta los bytes en
     * silencio. Medido en este proyecto: cuatro trabajos seguidos registraron
     * "enviados 888/888 bytes" sin un solo error y no salió ni un papel; los
     * mismos trabajos, después de apagar y prender la impresora, salieron
     * bien — con logs IDÉNTICOS. Preguntarle a la impresora antes de mandarle
     * el trabajo es la única forma de separar los dos casos.
     */
    /**
     * IMPRIMIR Y CONSULTAR NO COMPARTEN BYTES EN EL CABLE. A PROPÓSITO.
     *
     * Antes esta función sondeaba el estado ANTES de cada impresión, y eso fue
     * un error de diseño con consecuencias medidas en el local: la sonda
     * inyecta bytes ajenos al documento en el mismo canal, justo delante de
     * él. `<ESC>!?` son `1B 21 3F`, y en ESC/POS `ESC !` es "seleccionar modo
     * de impresión" — en un firmware que entiende los dos lenguajes (estas
     * térmicas suelen), la "consulta" se lee como un comando de modo y el TSPL
     * que viene atrás se ignora. El síntoma fue el peor posible: imprimía,
     * dejó de imprimir, y apagar y prender no servía porque la sonda se
     * mandaba de nuevo en el ticket siguiente.
     *
     * Lo que la sonda aportaba al imprimir era abortar con "sin papel" — útil,
     * pero no vale poner en riesgo el documento de un cobro real. Ahora:
     *
     *   imprimir  ->  se escribe el documento Y NADA MÁS
     *   estado    ->  se sondea, sin escribir ningún documento
     *
     * La consulta sigue existiendo entera, donde no puede arruinar un ticket:
     * detrás del botón "Estado", que el dueño toca a propósito cuando algo
     * anda mal.
     */
    private Sondeo trabajar(OutputStream salida, InputStream entrada, byte[] bytes, String lenguaje)
            throws Exception {
        // El socket queda listo ANTES que la impresora: escribir de inmediato
        // pierde los primeros bytes (ver escribir()).
        Thread.sleep(PAUSA_TRAS_CONECTAR_MS);

        // Sin documento, esto es una CONSULTA y solo se sondea.
        if (bytes == null) return sondear(salida, entrada, lenguaje);

        // Con documento, se imprime y no se pregunta nada.
        escribir(salida, bytes);
        return new Sondeo();
    }

    /** Falla con un motivo que la impresora misma reportó. */
    private static class EstadoImpresoraException extends IOException {
        EstadoImpresoraException(String m) { super(m); }
    }

    // Sondas de estado en TIEMPO REAL: las dos se contestan aunque la
    // impresora tenga trabajo encolado, que es justo el caso que interesa.
    //   TSPL:    <ESC> ! ?      -> 1 byte de banderas
    //   ESC/POS: DLE EOT 1      -> 1 byte de estado
    private static final byte[] SONDA_TSPL = { 0x1B, 0x21, 0x3F };
    private static final byte[] SONDA_ESCPOS = { 0x10, 0x04, 0x01 };
    private static final long PLAZO_SONDEO_MS = 1500;

    // CRLF. Cierra la linea que deja la sonda en el parser de TSPL — ver el
    // final de sondear(), que explica por que sin esto no imprime NADA.
    private static final byte[] FIN_LINEA_TSPL = { 0x0D, 0x0A };

    private Sondeo sondear(OutputStream salida, InputStream entrada, String lenguaje) throws Exception {
        boolean tspl = "tspl".equals(lenguaje);
        Sondeo s = new Sondeo();

        // Se descarta lo que haya quedado de una sesión anterior: mezclado
        // con la respuesta, el primer byte que se lea no sería el estado.
        try {
            while (entrada.available() > 0) {
                if (entrada.skip(entrada.available()) <= 0) break;
            }
        } catch (IOException ignored) { }

        // Si ni la sonda se puede escribir, el enlace está roto de verdad:
        // eso sí es un error que vale propagar.
        salida.write(tspl ? SONDA_TSPL : SONDA_ESCPOS);
        salida.flush();

        long limite = System.currentTimeMillis() + PLAZO_SONDEO_MS;
        int primero = -1;
        while (System.currentTimeMillis() < limite) {
            int hay;
            try { hay = entrada.available(); } catch (IOException e) { break; }
            if (hay > 0) {
                byte[] buf = new byte[hay];
                int leidos = entrada.read(buf, 0, hay);
                if (leidos > 0) primero = buf[0] & 0xFF;
                break;
            }
            Thread.sleep(50);
        }

        // LA SONDA TIENE QUE DEJAR EL PARSER LIMPIO.
        //
        // TSPL es un protocolo de LINEAS terminadas en CRLF, y la sonda va sin
        // terminador. La HiLabel contesta la consulta —se lee el 0x00— pero
        // IGUAL deja esos tres bytes en su buffer de lineas, asi que el primer
        // comando del trabajo le llega como "\x1B!?SIZE 72 mm,87 mm": comando
        // invalido, se descarta, la etiqueta nunca recibe su tamaño y no sale
        // NADA. Sin un solo error en ninguna parte — el mismo sintoma que esta
        // sonda vino a eliminar.
        //
        // Medido con un experimento de dos etiquetas identicas: la normal no
        // imprimio, la que llevaba un CRLF adelante salio perfecta.
        //
        // En ESC/POS NO se manda: ahi 0x0D/0x0A son retorno de carro y avance
        // de linea, o sea que moverian el papel en cada impresion.
        if (tspl) {
            try {
                salida.write(FIN_LINEA_TSPL);
                salida.flush();
            } catch (IOException ignored) {
                // Si el enlace se cayo justo aca, escribir() lo va a reportar.
            }
        }

        if (primero < 0) {
            android.util.Log.d("ImpresoraTermica", "sonda " + lenguaje + ": sin respuesta");
            return s;   // respondio=false, motivo=null -> se imprime igual
        }

        s.respondio = true;
        s.codigo = primero;
        s.motivo = motivoParaNoImprimir(primero, tspl);
        s.descripcion = s.motivo != null ? s.motivo : "lista";
        android.util.Log.d("ImpresoraTermica",
                "sonda " + lenguaje + ": 0x" + Integer.toHexString(primero) + " -> " + s.descripcion);
        return s;
    }

    /**
     * Traduce el byte de estado a un motivo para NO imprimir, o null si se
     * puede seguir.
     *
     * Solo se bloquea por banderas que el estándar define sin ambigüedad. Un
     * valor desconocido se deja pasar a propósito: estas impresoras son
     * baratas y algunas devuelven cualquier cosa, así que interpretar de más
     * terminaría bloqueando impresoras sanas. El código crudo queda en el log
     * y en la pantalla de Estado para poder diagnosticarlo.
     */
    private String motivoParaNoImprimir(int estado, boolean tspl) {
        if (tspl) {
            if (estado == 0x00) return null;                 // lista
            if ((estado & 0x20) != 0) return null;           // imprimiendo: viva, encola
            if ((estado & 0x04) != 0) return "La impresora no tiene papel.";
            if ((estado & 0x01) != 0) return "El cabezal de la impresora está abierto.";
            if ((estado & 0x02) != 0) return "Hay papel atascado en la impresora.";
            if ((estado & 0x08) != 0) return "La impresora no tiene cinta (ribbon).";
            if ((estado & 0x10) != 0) return "La impresora está en pausa. Soltá la pausa y volvé a intentar.";
            if ((estado & 0x80) != 0) {
                // El estado del que se sale apagando y prendiendo: el firmware
                // se declara en error y descarta todo lo que le llega.
                return "La impresora está trabada. Apagala y prendela de nuevo.";
            }
            return null;
        }
        // ESC/POS, respuesta de DLE EOT 1: el bit 3 es "offline".
        if ((estado & 0x08) != 0) return "La impresora está fuera de línea. ¿Tiene papel y la tapa cerrada?";
        return null;
    }

    // Tamaño de trozo y pausas. NO son números arbitrarios: casi todas las
    // térmicas Bluetooth económicas tienen un buffer chico —256 bytes es lo
    // habitual— y descartan EN SILENCIO lo que llega de más. El síntoma es
    // exactamente el que se observó: la impresora despierta al conectarse,
    // recibe los datos y no imprime nada.
    private static final int TROZO = 180;
    private static final long PAUSA_TRAS_CONECTAR_MS = 350;
    private static final long PAUSA_ENTRE_TROZOS_MS = 45;
    private static final long PAUSA_ANTES_DE_CERRAR_MS = 800;

    private void escribir(OutputStream salida, byte[] bytes) throws Exception {
        // El socket queda listo ANTES que la impresora. Escribir de
        // inmediato hace que se pierdan los primeros bytes —justo el ESC @
        // que la inicializa— y sin inicializar ignora todo lo que sigue.
        Thread.sleep(PAUSA_TRAS_CONECTAR_MS);

        int enviados = 0;
        for (int i = 0; i < bytes.length; i += TROZO) {
            int largo = Math.min(TROZO, bytes.length - i);
            salida.write(bytes, i, largo);
            salida.flush();
            enviados += largo;
            Thread.sleep(PAUSA_ENTRE_TROZOS_MS);
        }

        android.util.Log.d("ImpresoraTermica",
                "enviados " + enviados + "/" + bytes.length + " bytes en trozos de " + TROZO);

        // Cerrar el socket con el buffer todavía vaciándose corta el ticket
        // por la mitad.
        Thread.sleep(PAUSA_ANTES_DE_CERRAR_MS);
    }

    /**
     * Conecta, con el plan B que estas impresoras suelen necesitar.
     *
     * createRfcommSocketToServiceRecord es la vía documentada, pero muchas
     * térmicas económicas no publican bien su registro SDP y devuelven
     * "read failed, socket might closed". El método oculto
     * createRfcommSocket va directo al canal 1 y con esas sí funciona. Es
     * reflexión sobre una API no pública: por eso va como respaldo y no
     * como camino principal.
     */
    private BluetoothSocket conectar(BluetoothDevice device) throws IOException {
        try {
            BluetoothSocket s = device.createRfcommSocketToServiceRecord(SPP);
            s.connect();
            return s;
        } catch (Exception primero) {
            try {
                Method metodo = device.getClass().getMethod("createRfcommSocket", int.class);
                BluetoothSocket s = (BluetoothSocket) metodo.invoke(device, 1);
                s.connect();
                return s;
            } catch (Exception segundo) {
                throw new IOException("No se pudo conectar con la impresora");
            }
        }
    }

    /**
     * Traduce las excepciones a algo que un cajero pueda accionar. El
     * mensaje crudo de Android ("read failed, socket might closed...") no le
     * dice a nadie que la impresora está apagada.
     */
    private String mensajeUtil(Exception e) {
        String texto = e.getMessage() != null ? e.getMessage() : "";
        // Lo que reportó la impresora ya viene accionable y en castellano: se
        // devuelve tal cual. Pasarlo por las reglas de abajo lo reescribiría
        // con una causa inventada — "sin papel" no es "la impresora no
        // responde".
        if (e instanceof EstadoImpresoraException) return texto;
        String bajo = texto.toLowerCase();
        if (e instanceof SocketTimeoutException || bajo.contains("timed out")) {
            return "La impresora de red no contesta. ¿La IP es correcta y está en la misma WiFi?";
        }
        if (bajo.contains("econnrefused") || bajo.contains("refused")) {
            return "La impresora rechazó la conexión. ¿El puerto es el 9100?";
        }
        if (bajo.contains("socket") || bajo.contains("closed")) {
            return "La impresora no responde. ¿Está encendida y con papel?";
        }
        if (bajo.contains("permiso") || e instanceof SecurityException) {
            return "Falta el permiso de Bluetooth";
        }
        return texto.isEmpty() ? "No se pudo imprimir" : texto;
    }
}
