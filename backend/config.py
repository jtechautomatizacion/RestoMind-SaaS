from pydantic import model_validator
from pydantic_settings import BaseSettings
from typing import List

_CORS_ORIGINS_DEFAULT = ["http://localhost:3000", "http://localhost:8000"]


class Settings(BaseSettings):
    # Environment
    environment: str = "development"
    debug: bool = True

    # Sin default a propósito: si SECRET_KEY no está en el entorno/.env, la
    # app debe fallar al arrancar, no firmar tokens JWT con un valor público
    # que cualquiera puede leer en el código fuente. Un despliegue nuevo sin
    # este valor configurado emitiría tokens de admin/superadmin forjables.
    secret_key: str

    # Database
    database_url: str = "sqlite:///./restomind.db"
    database_echo: bool = False

    # Multi-tenant (MVP: sin login todavía, cliente por defecto)
    default_cliente_id: str = "rest-001"

    # CORS
    cors_origins: List[str] = list(_CORS_ORIGINS_DEFAULT)

    # Server
    host: str = "0.0.0.0"
    port: int = 8000

    # Claude API (futuro)
    anthropic_api_key: str = ""

    # Facturación electrónica SUNAT — 100% en la nube.
    #
    # "sunat_cloud" (default): RestoMind firma y envía el comprobante a
    # SUNAT desde el servidor, vía el micro-servicio de sunat-service/. No
    # necesita ninguna PC con Windows en el restaurante.
    #
    # El emisor "sfs_local" (Facturador de escritorio + archivos planos
    # .cab/.det/.tri/.ley + agente de PowerShell) SE ELIMINÓ: ataba cada
    # restaurante a una computadora prendida y no servía para un local que
    # trabaja solo con tablets. Los comprobantes emitidos así siguen
    # visibles en el historial, con estado 'generado_localmente'.
    #
    # "facturacion_pe" (de pago, S/ 0.20/boleta) se conserva como
    # alternativa para quien prefiera no administrar su propio certificado.
    emisor_facturacion: str = "sunat_cloud"

    # OBSOLETAS — no se leen en ningún lado. Se declaran solo para que un
    # .env que todavía las tenga no impida ARRANCAR la app.
    #
    # pydantic-settings rechaza variables desconocidas (extra_forbidden), así
    # que borrarlas de acá haría que cualquier servidor ya desplegado —con
    # SFS_EXPORT_DIR/SFS_EXPORT_ENCODING en su .env— muriera al actualizar,
    # con un error de validación que no dice "sacá esta línea del .env".
    # Se pueden eliminar cuando ningún .env en producción las tenga.
    sfs_export_dir: str = ""
    sfs_export_encoding: str = "latin-1"

    # Carpeta donde vive el certificado de CADA restaurante, un
    # subdirectorio por cliente_id. Es el mismo volumen que sunat-service
    # monta de solo lectura (ver docker-compose.yml): RestoMind escribe,
    # el contenedor de firma lee.
    #
    # Ruta relativa a propósito: en el VPS el proceso corre desde
    # /opt/restomind, así que resuelve a /opt/restomind/certs — la misma que
    # el compose monta. Se puede apuntar a otro lado con CERTS_DIR.
    certs_dir: str = "certs"

    facturacion_pe_api_key: str = ""
    facturacion_pe_url: str = "https://api.facturacion.pe/v1"

    # "sunat_cloud" (costo S/ 0 por boleta, pero exige certificado digital):
    # RestoMind firma y envía el comprobante a SUNAT desde el servidor, vía
    # el micro-servicio de sunat-service/ (librería sunat-py). A diferencia
    # de "sfs_local", NO necesita una PC con Windows en el restaurante — un
    # local que trabaja solo con tablets puede facturar igual, y desaparece
    # la dependencia del agente de PowerShell.
    #
    # Vive en su propio contenedor porque sunat-py fija cryptography<45 y
    # RestoMind usa la 50: juntarlos obligaría a retroceder 6 versiones
    # mayores la librería que respalda los JWT. Ver sunat-service/app.py.
    sunat_service_url: str = ""
    sunat_service_token: str = ""
    # Generoso a propósito: firmar + comprimir + el ida y vuelta SOAP contra
    # SUNAT puede pasar de 20s en horas pico. Cortar antes deja la boleta en
    # un limbo (SUNAT pudo haberla aceptado y RestoMind no se enteró).
    sunat_service_timeout: int = 45

    # Copia local del Padrón Reducido de SUNAT, construida por
    # backend/scripts/cargar_padron_sunat.py. Si el archivo no existe, la
    # consulta de RUC responde 503 con instrucciones — el resto de la app
    # funciona igual, no es una dependencia dura.
    padron_db_path: str = "data/sunat_padron.db"

    # Servicio externo para resolver un DNI (el Padrón Reducido solo tiene
    # RUC). APAGADO por defecto: sin URL configurada, un DNI desconocido
    # simplemente devuelve "no encontrado" y el cajero escribe el nombre a
    # mano — nunca falla el cobro por esto.
    #
    # Es de PAGO por consulta, de ahí que el resultado se guarde en
    # clientes_frecuentes: la segunda vez que vuelve el mismo comensal sale
    # gratis y al instante.
    dni_api_url: str = ""
    dni_api_token: str = ""
    dni_api_timeout: int = 6

    # Notificaciones push (Firebase Cloud Messaging) — avisan a jefe_cocina
    # cuando entra una comanda nueva, incluso con la app minimizada.
    # firebase_credentials_json: ruta al archivo de credenciales de cuenta de
    # servicio que se descarga desde Firebase Console > Configuración del
    # proyecto > Cuentas de servicio > "Generar nueva clave privada".
    # Sin este valor, el envío de notificaciones se salta en silencio (ver
    # utils/push_notifications.py) — la app funciona igual, solo sin avisos.
    firebase_credentials_json: str = ""
    # firebase_vapid_key: la "Clave pública" que Firebase Console genera en
    # Configuración del proyecto > Cloud Messaging > Certificados push web.
    # No es secreta (se sirve al navegador), pero vive en el backend para no
    # tener que tocar el HTML/JS del frontend al configurarla.
    firebase_vapid_key: str = ""

    # SMTP (para envío de emails)
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from_email: str = ""
    smtp_from_name: str = "RestoMind"
    app_url: str = "http://localhost:8000"

    # Enlace de descarga del APK, para el correo de bienvenida.
    #
    # Va como variable de entorno y no escrito en backend/email.py porque
    # cambia por motivos ajenos al código: una versión nueva, otra carpeta
    # compartida, un cambio de Drive a la Play Store. Con la URL en el
    # código, cada uno de esos cambios obligaría a un commit y un
    # despliegue completo para editar un enlace.
    #
    # Vacío = el correo no muestra la sección del APK. Así el mismo código
    # sirve antes y después de que exista el instalable, sin dejar un botón
    # que lleva a una carpeta vacía.
    apk_url: str = ""

    class Config:
        env_file = ".env"
        case_sensitive = False

    @model_validator(mode="after")
    def _normalizar_emisor(self) -> "Settings":
        """
        Un .env que todavía diga EMISOR_FACTURACION=sfs_local pasa a
        'sunat_cloud'.

        Sin esto, el despacho igual mandaría a la nube (todo lo que no sea
        'facturacion_pe' va por ahí), pero la app REPORTARÍA un emisor que ya
        no existe: en /health, en los logs y en cualquier diagnóstico se
        leería "sfs_local" y alguien buscaría archivos .cab que nadie
        escribe. Normalizar acá deja una sola verdad.
        """
        if self.emisor_facturacion == "sfs_local":
            self.emisor_facturacion = "sunat_cloud"
        return self

    @model_validator(mode="after")
    def _validar_produccion(self) -> "Settings":
        """En producción, un CORS mal configurado es tan grave como un
        SECRET_KEY hardcodeado: "*" o los orígenes de desarrollo por defecto
        dejarían que cualquier sitio web llame a la API usando el token que
        el navegador de la víctima tiene guardado. Igual que con SECRET_KEY,
        preferimos que la app no arranque a que arranque insegura."""
        if self.environment != "production":
            return self

        if self.debug:
            raise ValueError(
                "DEBUG no puede estar activo en producción (expone stack traces detallados)."
            )
        if not self.cors_origins or "*" in self.cors_origins:
            raise ValueError(
                "CORS_ORIGINS debe listar los dominios reales del frontend en producción, no '*'."
            )
        if self.cors_origins == _CORS_ORIGINS_DEFAULT:
            raise ValueError(
                "CORS_ORIGINS sigue en los valores de desarrollo (localhost) — "
                "configura los dominios reales en el .env de producción."
            )
        return self


settings = Settings()
