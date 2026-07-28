"""R4 Banco - Constantes, endpoints y configuración R4 Conecta V3.0"""


# ============================================================================
# ENDPOINTS BASE (desde manual R4 Conecta V3.0)
# ============================================================================

BASE_URL_PROD = "https://r4conecta.mibanco.com.ve/"

ENDPOINTS: dict[str, str] = {
    # Consultas
    "bcv": "MBbcv",  # Tasa BCV oficial
    "consulta": "R4consulta",  # Validar cliente (banco → nosotros)
    "notifica": "R4notifica",  # Webhook pago móvil entrante (banco → nosotros)
    "simf_consulta": "MBconsulta",  # Alternativa vía SIMF
    # Cobros
    "c2p": "MBc2p",  # Cobro C2P (nosotros → banco)
    "anulacion_c2p": "MBanulacionC2P",  # Anular C2P
    # Verificación
    "consultar_ops": "ConsultarOperaciones",  # Consultar estado operación (cuando AC00)
    # Créditos / Transferencias
    "credito_inmediato": "CreditoInmediato",  # Crédito inmediato a teléfono
    "credito_inmediato_cuenta": "CICuentas",  # Crédito inmediato a cuenta 20 dígitos
    "domiciliacion_cuenta": "TransferenciaOnline/DomiciliacionCNTA",  # Domiciliación 20 dígitos
    "domiciliacion_cel": "TransferenciaOnline/DomiciliacionCELE",  # Domiciliación por teléfono
    # Débito inmediato (requiere OTP previo)
    "generar_otp": "GenerarOtp",
    "debito_inmediato": "DebitoInmediato",
    # Otros
    "vuelto": "MBvuelto",  # Vuelto (transferencia a teléfono)
    "dispersar": "R4pagos",  # Gestión de pagos / dispersión
}


# ============================================================================
# STRINGS A FIRMAR POR ENDPOINT (HMAC-SHA256)
# Según manual: cada endpoint tiene su propio formato de string a firmar
# La llave es siempre el Commerce Token
# ============================================================================

SIGN_STRINGS: dict[str, str] = {
    # MBbcv: "fechavalor + moneda"
    "bcv": "{Fechavalor}{Moneda}",
    # R4consulta: Authorization creado por comercio, formato UUID
    # No hay string a firmar estándar, el comercio genera su propio auth
    "consulta": "",  # Comercio genera su propio UUID
    # R4notifica: Authorization creado por comercio, formato UUID
    "notifica": "",  # Comercio genera su propio UUID
    # R4pagos (dispersión): "monto + fecha (MM/DD/YYYY)"
    "dispersar": "{monto}{fecha}",
    # MBvuelto: "Telefono_destino + Monto + Banco + Cedula"
    "vuelto": "{TelefonoDestino}{Monto}{Banco}{Cedula}",
    # GenerarOtp: "Banco + Monto + Telefono + Cedula"
    "generar_otp": "{Banco}{Monto}{Telefono}{Cedula}",
    # DebitoInmediato: "Banco + Cedula + Telefono + Monto + OTP"
    "debito_inmediato": "{Banco}{Cedula}{Telefono}{Monto}{OTP}",
    # CreditoInmediato: "Banco + Cedula + Telefono + Monto"
    "credito_inmediato": "{Banco}{Cedula}{Telefono}{Monto}",
    # DomiciliacionCNTA: "cuenta"
    "domiciliacion_cuenta": "{cuenta}",
    # DomiciliacionCELE: "telefono"
    "domiciliacion_cel": "{telefono}",
    # MBc2p (Cobro C2P): "TelefonoDestino + Monto + Banco + Cedula"
    "c2p": "{TelefonoDestino}{Monto}{Banco}{Cedula}",
    # MBanulacionC2P: "Banco"
    "anulacion_c2p": "{Banco}",
    # ConsultarOperaciones: "Id"
    "consultar_ops": "{Id}",
    # MBconsulta (SIMF): Authorization UUID creado por comercio
    "simf_consulta": "",
}


# ============================================================================
# CÓDIGOS DE RESPUESTA DEL BANCO (mapeo a significado legible)
# ============================================================================

RESPONSE_CODES: dict[str, str] = {
    # Éxito
    "00": "APROBADO / TRANSACCION EXITOSA",
    "202": "SE HA RECIBIDO EL MENSAJE DE FORMA SATISFACTORIA",
    "ACCP": "OPERACIÓN ACEPTADA",
    "true": "ACEPTADO / STATUS TRUE",
    # En proceso / Espera
    "AC00": "OPERACIÓN EN ESPERA DE RESPUESTA DEL RECEPTOR",
    # Errores comunes
    "01": "REFERIRSE AL CLIENTE",
    "05": "TIEMPO DE RESPUESTA EXCEDIDO",
    "07": "REQUEST INVÁLIDA, ERROR EN CAMPO ESPECÍFICO",
    "08": "TOKEN INVÁLIDO / LLAVE ERRÓNEA",
    "11": "ERROR DE RESPUESTA",
    "12": "TRANSACCIÓN INVÁLIDA",
    "13": "MONTO INVÁLIDO",
    "14": "NÚMERO TELÉFONO RECEPTOR ERRADO",
    "15": "LLAVE ERRÓNEA",
    "30": "ERROR DE FORMATO",
    "41": "SERVICIO NO ACTIVO / BANCO FUERA DE SERVICIO",
    "51": "INSUFICIENCIA DE FONDOS / NO TIENE FONDOS DISPONIBLES",
    "55": "TELÉFONO ORIGEN NO EXISTE",
    "56": "NO COINCIDE NÚMERO DE CELULAR CON EL AFILIADO A LA CÉDULA",
    "57": "NEGADA POR EL RECEPTOR",
    "62": "CUENTA RESTRINGIDA",
    "68": "RESPUESTA TARDÍA, PROCEDE REVERSO",
    "80": "CÉDULA O PASAPORTE ERRADO / DOCUMENTO DE IDENTIFICACIÓN ERRADO",
    "87": "TIME OUT",
    "90": "CIERRE BANCARIO EN PROCESO",
    "91": "INSTITUCIÓN NO DISPONIBLE",
    "92": "BANCO RECEPTOR NO AFILIADO",
    "99": "ERROR EN NOTIFICACIÓN",
    # Códigos extendidos (manual páginas 23-29)
    "AB01": "TIEMPO DE ESPERA AGOTADO",
    "AB07": "AGENTE FUERA DE LÍNEA",
    "AC01": "NÚMERO DE CUENTA INCORRECTO",
    "AC04": "CUENTA CANCELADA",
    "AC06": "CUENTA BLOQUEADA",
    "AC09": "MONEDA NO VÁLIDA",
    "AG01": "TRANSACCIÓN RESTRINGIDA",
    "AG09": "PAGO NO RECIBIDO",
    "AG10": "AGENTE SUSPENDIDO O EXCLUIDO",
    "AM02": "MONTO DE LA TRANSACCIÓN NO PERMITIDO",
    "AM04": "SALDO INSUFICIENTE",
    "AM05": "OPERACIÓN DUPLICADA",
    "BE01": "DATOS DEL CLIENTE NO CORRESPONDEN A LA CUENTA",
    "BE20": "LONGITUD DEL NOMBRE INVÁLIDA",
    "CH20": "NÚMERO DE DECIMALES INCORRECTO",
    "CUST": "CANCELACIÓN SOLICITADA POR EL DEUDOR",
    "DS02": "OPERACIÓN CANCELADA",
    "DT03": "FECHA DE PROCESAMIENTO NO BANCARIA NO VÁLIDA",
    "DU01": "IDENTIFICACIÓN DE MENSAJE DUPLICADO",
    "ED05": "LIQUIDACIÓN FALLIDA",
    "FF05": "CÓDIGO DEL PRODUCTO INCORRECTO",
    "FF07": "CÓDIGO DEL SUB PRODUCTO INCORRECTO",
    "MD01": "NO POSEE AFILIACIÓN",
    "MD09": "AFILIACIÓN INACTIVA",
    "MD15": "MONTO INCORRECTO / COBRO NO PERMITIDO",
    "MD21": "COBRO NO PERMITIDO",
    "MD22": "AFILIACIÓN SUSPENDIDA",
    "RC08": "CÓDIGO DEL BANCO NO EXISTE EN EL SISTEMA DE COMPENSACIÓN/LIQUIDACIÓN",
    "RJCT": "OPERACIÓN RECHAZADA",
    "TKCM": "CÓDIGO ÚNICO DE OPERACIÓN DE DÉBITO INCORRECTO",
    "TM01": "RECHAZO TÉCNICO",
    "VE01": "FUERA DEL HORARIO PERMITIDO",
}


# ============================================================================
# IPS DEL BANCO (WHITELIST) - Manual página 4
# ============================================================================

BANK_IPS: set[str] = {
    "45.175.213.98",
    "200.74.203.91",
    "204.199.249.3",
    # Nota: el manual lista 204.199.249.3 dos veces, usamos set para dedup
}


# ============================================================================
# UTILIDADES
# ============================================================================


def is_bank_ip_allowed(ip: str) -> bool:
    """Verifica si una IP está en whitelist del banco"""
    return ip in BANK_IPS


def get_response_meaning(code: str) -> str:
    """Retorna significado legible del código de respuesta"""
    return RESPONSE_CODES.get(code, f"CÓDIGO DESCONOCIDO: {code}")


def is_success_code(code: str) -> bool:
    """Verifica si un código indica éxito"""
    return code in ("00", "202", "ACCP", "true", "True")


def build_url(endpoint_key: str, base_url: str = BASE_URL_PROD) -> str:
    """Construye URL completa para un endpoint"""
    path = ENDPOINTS.get(endpoint_key, endpoint_key)
    return base_url.rstrip("/") + "/" + path.lstrip("/")


# ============================================================================
# CÓDIGOS DE BANCO (referencia - 3 dígitos)
# El manual no lista todos, estos son los comunes en Venezuela
# ============================================================================

BANK_CODES: dict[str, str] = {
    "0102": "Banco Mercantil",
    "0104": "Banco de Venezuela",
    "0105": "Banco Bicentenario",
    "0108": "Banco Provincial",
    "0114": "Bancaribe",
    "0115": "Banco Exterior",
    "0116": "Banco Occidental de Descuento",
    "0128": "Banco Caroní",
    "0134": "Banesco",
    "0137": "Banco Sofitasa",
    "0138": "Banco Plaza",
    "0146": "Banco del Tesoro",
    "0151": "Banco Fondo Común",
    "0156": "100% Banco",
    "0157": "Banco del Sur",
    "0163": "Banco Nacional de Crédito",
    "0166": "Banco Agrícola de Venezuela",
    "0168": "Bancamiga",
    "0169": "Mi Banco",
    "0171": "Banco Activo",
    "0172": "Bancamiga",
    "0173": "Banco Internacional de Desarrollo",
    "0174": "Banco Nacional de Desarrollo",
    "0175": "Banco Universal",
    "0177": "Banfanb",
    "0191": "Banco de la Fuerza Armada",
    "0192": "Banco de la Fuerza Armada (Bicentenaria)",
    "0601": "Instituto Municipal de Crédito Popular",
    "0602": "Banco del Caribe",
}
