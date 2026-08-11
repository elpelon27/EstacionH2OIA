#!/usr/bin/env python3
"""
Códigos de Red Interbancaria (Codigored) - R4 Conecta V3.0
Extraídos de la Guía de Integración R4 Conecta (página 11 del PDF oficial).

Este módulo proporciona la tabla completa de códigos de respuesta
de la red interbancaria venezolana según especificación del banco.
"""

from enum import StrEnum


class CodigosRedInterbancaria(StrEnum):
    """
    Códigos de respuesta de la red interbancaria (Codigored).

    Extraídos de la Guía de Integración R4 Conecta V3.0 - Página 11.
    Sección: "Listado de Códigos de Red Interbancaria (Codigored)".
    """

    # Aprobados
    APROBADO = "00"

    # Referidos al cliente
    REFERIRSE_AL_CLIENTE = "01"

    # Errores de transacción
    TRANSACCION_INVALIDA = "12"
    MONTO_INVALIDO = "13"
    ERROR_DE_FORMATO = "30"
    TIEMPO_RESPUESTA_EXCEDIDO = "05"
    ERROR_EN_NOTIFICACION = "99"

    # Errores de teléfono/celular
    NUMERO_TELEFONO_RECEPTOR_ERRADO = "14"
    CELULAR_NO_COINCIDE = "56"
    TELEFONO_ORIGEN_NO_EXISTE = "55"
    NO_COINCIDE_NUMERO_CELULAR_CON_AFILIADO = "56"  # alias

    # Errores de servicio
    SERVICIO_NO_ACTIVO = "41"
    SERVICIO_NO_ACTIVO_ALT = "43"
    SERVICIO_NO_ACTIVO_BANCO_FUERA_SERVICIO = "41"
    INSTITUCION_NO_DISPONIBLE = "91"
    BANCO_RECEPTOR_NO_AFILIADO = "92"
    CIERRE_BANCARIO_EN_PROCESO = "90"
    FUERA_DE_HORARIO_PERMITIDO = "VE01"

    # Errores de token/autenticación
    TOKEN_INVALIDO = "55"
    TOKEN_INCORRECTO = "15"
    TOKEN_CM = "TKCM"
    LLAVE_ERRONEA = "15"

    # Errores de documento/identificación
    CEDULA_O_PASAPORTE_ERRADO = "80"
    CEDULA_RECEPTOR_INVALIDA = "80"
    DOCUMENTO_IDENTIFICACION_ERRADO = "80"

    # Errores de cuenta
    CUENTA_RESTRINGIDA = "62"
    CUENTA_CANCELADA = "AC04"
    CUENTA_BLOQUEADA = "AC06"
    CUENTA_INCORRECTA = "AC01"
    NUMERO_CUENTA_INCORRECTO = "AC01"

    # Errores de fondos
    SIN_FONDOS_DISPONIBLES = "51"
    INSUFICIENCIA_DE_FONDOS = "51"
    SALDO_INSUFICIENTE = "AM04"
    MONTO_INCORRECTO = "MD15"
    MONTO_NO_PERMITIDO = "AM02"
    MONTO_TRANSACCION_NO_PERMITIDO = "AM02"

    # Errores de monto/decimales
    NUMERO_DECIMALES_INCORRECTO = "CH20"

    # Errores de tiempo
    TIEMPO_RESPUESTA_EXCEDIDO_ALT = "05"
    TIME_OUT = "87"
    TIEMPO_ESPERA_AGOTADO = "AB01"
    RESPUESTA_TARDIA_REVERSO = "68"
    FECHA_PROCESAMIENTO_NO_VALIDA = "DT03"
    FUERA_HORARIO_PERMITIDO = "VE01"

    # Errores de banco/institución
    INSTITUCION_NO_DISPONIBLE_ALT = "91"
    BANCO_NO_EXISTE_COMPENSACION = "RC08"
    BANCO_RECEPTOR_NO_AFILIADO_ALT = "92"
    BANCO_FUERA_SERVICIO = "41"
    CODIGO_BANCO_NO_EXISTE = "RC08"

    # Errores de operación
    OPERACION_NO_PERMITIDA = "41"
    TRANSACCION_NO_PERMITIDA = "41"
    OPERACION_CANCELADA = "DS02"
    OPERACION_DUPLICADA = "AM05"
    IDENTIFICACION_MENSAJE_DUPLICADO = "DU01"
    TRANSACCION_RECHAZADA = "RJCT"
    CANCELACION_SOLICITADA_DEUDOR = "CUST"
    COBRO_NO_PERMITIDO = "MD21"

    # Errores de agente/usuario
    AGENTE_FUERA_LINEA = "AB07"
    AGENTE_SUSPENDIDO_EXCLUIDO = "AG10"
    AGENTE_RESTRINGIDO = "AG01"
    AFILIACION_INACTIVA = "MD09"
    AFILIACION_SUSPENDIDA = "MD22"
    NO_POSEE_AFILIACION = "MD01"
    AFILIACION_NO_REGISTRADA = "14"
    COMBO_CELULAR_CEDULA_NO_REGISTRADO = "14"

    # Errores de validación
    LONGITUD_NOMBRE_INVALIDA = "BE20"
    DATOS_CLIENTE_NO_CORRESPONDEN = "BE01"
    NO_COINCIDE_CELULAR_CEDULA = "56"
    CEDULA_INVALIDA = "80"
    MONEDA_NO_VALIDA = "AC09"
    CODIGO_PRODUCTO_INCORRECTO = "FF05"
    CODIGO_SUBPRODUCTO_INCORRECTO = "FF07"

    # Errores técnicos
    RECHAZO_TECNICO = "TM01"
    ERROR_RESPUESTA = "11"
    ERROR_EN_FORMATO = "30"
    ERROR_LIQUIDACION_FALLIDA = "ED05"
    ERROR_FORMATO_30 = "30"

    # Códigos de respuesta específicos para Débito/Crédito Inmediato
    ACCP = "ACCP"  # Aprobado
    AC00 = "AC00"  # En espera de respuesta del receptor
    AC01 = "AC01"  # Número de cuenta incorrecto
    AC04 = "AC04"  # Cuenta cancelada
    AC06 = "AC06"  # Cuenta bloqueada
    AC09 = "AC09"  # Moneda no válida
    AB01 = "AB01"  # Tiempo de espera agotado
    AB07 = "AB07"  # Agente fuera de línea
    AG01 = "AG01"  # Transacción restringida
    AG09 = "AG09"  # Pago no recibido
    AG10 = "AG10"  # Agente suspendido o excluido
    AM02 = "AM02"  # Monto no permitido
    AM04 = "AM04"  # Saldo insuficiente
    AM05 = "AM05"  # Operación duplicada
    BE01 = "BE01"  # Datos cliente no corresponden
    BE20 = "BE20"  # Longitud nombre inválida
    CH20 = "CH20"  # Decimales incorrectos
    CUST = "CUST"  # Cancelación solicitada por deudor
    DS02 = "DS02"  # Operación cancelada
    DT03 = "DT03"  # Fecha procesamiento no válida
    DU01 = "DU01"  # Mensaje duplicado
    ED05 = "ED05"  # Liquidación fallida
    FF05 = "FF05"  # Código producto incorrecto
    FF07 = "FF07"  # Código subproducto incorrecto
    MD01 = "MD01"  # No posee afiliación
    MD09 = "MD09"  # Afiliación inactiva
    MD15 = "MD15"  # Monto incorrecto / Cobro no permitido
    MD21 = "MD21"  # Cobro no permitido
    MD22 = "MD22"  # Afiliación suspendida
    RC08 = "RC08"  # Banco no existe en compensación
    RJCT = "RJCT"  # Operación rechazada
    TKCM = "TKCM"  # Código único débito incorrecto
    TKCM_ALT = "TKCM"  # alias
    VE01 = "VE01"  # Fuera de horario permitido
    TM01 = "TM01"  # Rechazo técnico

    # Códigos específicos C2P
    C2P_00 = "00"  # Aprobado
    C2P_08 = "08"  # Token inválido
    C2P_15 = "15"  # Llave errónea
    C2P_30 = "30"  # Error en formato
    C2P_41 = "41"  # Banco fuera de servicio
    C2P_51 = "51"  # Insuficiencia de fondos
    C2P_56 = "56"  # Celular no coincide
    C2P_80 = "80"  # Documento identificación errado

    # Códigos C2P Anulación
    C2P_ANUL_00 = "00"  # Aprobado
    C2P_ANUL_41 = "41"  # Servicio no activo / negado por banco

    # Códigos Vuelto
    VUELTO_00 = "00"  # Exitoso
    VUELTO_08 = "08"  # Token inválido
    VUELTO_14 = "14"  # Combo celular-cédula no registrado
    VUELTO_51 = "51"  # Sin fondos
    VUELTO_55 = "55"  # Teléfono origen no existe
    VUELTO_56 = "56"  # Celular no coincide con cédula
    VUELTO_80 = "80"  # Cédula receptor inválida

    # Códigos Domiciliación
    DOM_202 = "202"  # Recibido satisfactoriamente
    DOM_07 = "07"  # Request inválido
    DOM_11 = "11"  # Error de respuesta

    # Códigos Cobro C2P (banco → comercio)
    C2P_BANCO_00 = "00"
    C2P_BANCO_08 = "08"
    C2P_BANCO_15 = "15"
    C2P_BANCO_30 = "30"
    C2P_BANCO_41 = "41"
    C2P_BANCO_51 = "51"
    C2P_BANCO_56 = "56"
    C2P_BANCO_80 = "80"

    @classmethod
    def get_description(cls, code: str) -> str:
        """Obtiene la descripción legible para un código."""
        descriptions = {
            "00": "APROBADO / TRANSACCION EXITOSA",
            "01": "REFERIRSE AL CLIENTE",
            "05": "TIEMPO DE RESPUESTA EXCEDIDO",
            "07": "REQUEST INVÁLIDO",
            "08": "TOKEN INVÁLIDO / LLAVE ERRÓNEA",
            "11": "ERROR DE RESPUESTA / ERROR EN FORMATO",
            "12": "TRANSACCIÓN INVÁLIDA",
            "13": "MONTO INVÁLIDO",
            "14": (
                "NÚMERO TELÉFONO RECEPTOR ERRADO / "
                "AFILIACIÓN NO REGISTRADA / "
                "COMBO CELULAR-CÉDULA NO REGISTRADO"
            ),
            "15": "LLAVE ERRÓNEA",
            "30": "ERROR DE FORMATO / ERROR EN FORMATO:30",
            "41": (
                "SERVICIO NO ACTIVO / BANCO FUERA DE SERVICIO / "
                "OPERACIÓN NO PERMITIDA / SERVICIO NO ACTIVO O NEGADO POR EL BANCO"
            ),
            "43": "SERVICIO NO ACTIVO",
            "51": "SIN FONDOS DISPONIBLES / INSUFICIENCIA DE FONDOS",
            "55": "TOKEN INVÁLIDO / TELÉFONO ORIGEN NO EXISTE",
            "56": (
                "CELULAR NO COINCIDE / "
                "NO COINCIDE NÚMERO DEL CELULAR CON EL AFILIADO A LA CÉDULA"
            ),
            "57": "NEGADA POR EL RECEPTOR",
            "62": "CUENTA RESTRINGIDA",
            "68": "RESPUESTA TARDÍA, PROCEDE REVERSO",
            "80": (
                "CÉDULA O PASAPORTE ERRADO / "
                "CÉDULA RECEPTOR INVÁLIDA / "
                "DOCUMENTO DE IDENTIFICACIÓN ERRADO"
            ),
            "87": "TIME OUT",
            "90": "CIERRE BANCARIO EN PROCESO",
            "91": "INSTITUCIÓN NO DISPONIBLE",
            "92": "BANCO RECEPTOR NO AFILIADO",
            "99": "ERROR EN NOTIFICACIÓN",
            # Débito/Crédito Inmediato
            "ACCP": "OPERACIÓN ACEPTADA",
            "AC00": "OPERACIÓN EN ESPERA DE RESPUESTA DEL RECEPTOR",
            "AC01": "NÚMERO DE CUENTA INCORRECTO",
            "AC04": "CUENTA CANCELADA",
            "AC06": "CUENTA BLOQUEADA",
            "AC09": "MONEDA NO VÁLIDA",
            "AB01": "TIEMPO DE ESPERA AGOTADO",
            "AB07": "AGENTE FUERA DE LÍNEA",
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
            "FF07": "CÓDIGO DEL SUBPRODUCTO INCORRECTO",
            "MD01": "NO POSEE AFILIACIÓN",
            "MD09": "AFILIACIÓN INACTIVA",
            "MD15": "MONTO INCORRECTO / COBRO NO PERMITIDO",
            "MD21": "COBRO NO PERMITIDO",
            "MD22": "AFILIACIÓN SUSPENDIDA",
            "RC08": "CÓDIGO DEL BANCO NO EXISTE EN EL SISTEMA DE COMPENSACIÓN/LIQUIDACIÓN",
            "RJCT": "OPERACIÓN RECHAZADA",
            "TKCM": "CÓDIGO ÚNICO DE OPERACIÓN DE DÉBITO INCORRECTO",
            "VE01": "FUERA DEL HORARIO PERMITIDO",
            "TM01": "RECHAZO TÉCNICO",
            # C2P
            "C2P_00": "TRANSACCIÓN EXITOSA",
            "C2P_08": "TOKEN INVÁLIDO",
            "C2P_15": "LLAVE ERRÓNEA",
            "C2P_30": "ERROR EN FORMATO:30",
            "C2P_41": "TRANSACCIÓN NO PERMITIDA BANCO FUERA DE SERVICIO",
            "C2P_51": "INSUFICIENCIA DE FONDOS",
            "C2P_56": "NUMERO DE CELULAR NO COINCIDE",
            "C2P_80": "DOCUMENTO DE IDENTIFICACIÓN ERRADO",
            # C2P Anulación
            "C2P_ANUL_00": "TRANSACCIÓN EXITOSA",
            "C2P_ANUL_41": "SERVICIO NO ACTIVO O NEGADA POR EL BANCO",
            # Vuelto
            "VUELTO_00": "TRANSACCIÓN EXITOSA",
            "VUELTO_08": "TOKEN INVÁLIDO",
            "VUELTO_14": "COMBO CELULAR CEDULA NO REGISTRADO VERIFIQUE DATOS DEL RECEPTOR",
            "VUELTO_51": "NO TIENE FONDOS DISPONIBLES",
            "VUELTO_55": "TELEFONO ORIGEN NO EXISTE",
            "VUELTO_56": "NO COINCIDE NÚMERO DEL CELULAR CON EL AFILIADO A LA CEDULA",
            "VUELTO_80": "CÉDULA DEL RECEPTOR INVALIDA VERIFIQUE DATOS",
            # Domiciliación
            "DOM_202": "SE HA RECIBIDO EL MENSAJE DE FORMA SATISFACTORIA",
            "DOM_07": "REQUEST INVÁLIDA, ERROR EN EL CAMPO",
            "DOM_11": "ERROR DE RESPUESTA",
            # Cobro C2P (banco → comercio)
            "C2P_BANCO_00": "TRANSACCIÓN EXITOSA",
            "C2P_BANCO_08": "TOKEN INVÁLIDO",
            "C2P_BANCO_15": "LLAVE ERRÓNEA",
            "C2P_BANCO_30": "ERROR EN FORMATO:30",
            "C2P_BANCO_41": "TRANSACCIÓN NO PERMITIDA BANCO FUERA DE SERVICIO",
            "C2P_BANCO_51": "INSUFICIENCIA DE FONDOS",
            "C2P_BANCO_56": "NUMERO DE CELULAR NO COINCIDE",
            "C2P_BANCO_80": "DOCUMENTO DE IDENTIFICACIÓN ERRADO",
        }
        return descriptions.get(code, f"CÓDIGO DESCONOCIDO: {code}")

    @classmethod
    def is_success(cls, code: str) -> bool:
        """Determina si un código indica éxito/transacción aprobada."""
        success_codes = {
            "00",
            "ACCP",
            "C2P_00",
            "C2P_ANUL_00",
            "VUELTO_00",
            "DOM_202",
            "C2P_BANCO_00",
        }
        return code in success_codes

    @classmethod
    def is_retryable(cls, code: str) -> bool:
        """Determina si un código sugiere reintentar la operación."""
        retryable_codes = {"05", "87", "68", "AB01", "TM01", "ED05", "DS02", "DU01"}
        return code in retryable_codes

    @classmethod
    def is_client_error(cls, code: str) -> bool:
        """Determina si el error es por datos del cliente (no reintentar)."""
        client_errors = {
            "01",
            "12",
            "13",
            "14",
            "15",
            "30",
            "41",
            "43",
            "51",
            "55",
            "56",
            "57",
            "62",
            "80",
            "87",
            "90",
            "91",
            "92",
            "99",
            "AC01",
            "AC04",
            "AC06",
            "AC09",
            "AB07",
            "AG01",
            "AG09",
            "AG10",
            "AM02",
            "AM04",
            "AM05",
            "BE01",
            "BE20",
            "CH20",
            "CUST",
            "DT03",
            "FF05",
            "FF07",
            "MD01",
            "MD09",
            "MD15",
            "MD21",
            "MD22",
            "RC08",
            "RJCT",
            "TKCM",
            "VE01",
            "C2P_08",
            "C2P_15",
            "C2P_30",
            "C2P_41",
            "C2P_51",
            "C2P_56",
            "C2P_80",
            "C2P_ANUL_41",
            "VUELTO_08",
            "VUELTO_14",
            "VUELTO_51",
            "VUELTO_55",
            "VUELTO_56",
            "VUELTO_80",
            "DOM_07",
            "DOM_11",
            "C2P_BANCO_08",
            "C2P_BANCO_15",
            "C2P_BANCO_30",
            "C2P_BANCO_41",
            "C2P_BANCO_51",
            "C2P_BANCO_56",
            "C2P_BANCO_80",
        }
        return code in client_errors


# Diccionario plano para uso rápido
CODIGOS_RED = {member.value: member.name for member in CodigosRedInterbancaria}

# Descripciones legibles
DESCRIPCIONES_CODIGOS = {
    code: CodigosRedInterbancaria.get_description(code) for code in CODIGOS_RED
}


def get_description(code: str) -> str:
    """Función helper para obtener descripción de un código."""
    return CodigosRedInterbancaria.get_description(code)


def is_success(code: str) -> bool:
    """Función helper para verificar si un código es éxito."""
    return CodigosRedInterbancaria.is_success(code)


def is_retryable(code: str) -> bool:
    """Función helper para verificar si un código es reintentable."""
    return CodigosRedInterbancaria.is_retryable(code)


def is_client_error(code: str) -> bool:
    """Función helper para verificar si es error de datos del cliente."""
    return CodigosRedInterbancaria.is_client_error(code)


if __name__ == "__main__":
    # Demo / test
    print("=== Códigos de Red Interbancaria R4 Conecta V3.0 ===\n")

    # Test some codes
    test_codes = [
        "00",
        "01",
        "05",
        "12",
        "13",
        "14",
        "30",
        "41",
        "51",
        "55",
        "56",
        "80",
        "ACCP",
        "AC00",
        "AC01",
        "C2P_00",
        "C2P_51",
        "VUELTO_00",
        "DOM_202",
    ]

    for code in test_codes:
        desc = get_description(code)
        success = is_success(code)
        retryable = is_retryable(code)
        client_err = is_client_error(code)
        status = "✓" if success else "✗"
        retry = "⟳" if retryable else "  "
        client = "!" if client_err else " "
        print(f"  {code:12} | {status} | {retry} | {client} | {desc}")

    print(f"\nTotal códigos en enum: {len(CodigosRedInterbancaria)}")
    print(f"Total en dict CODIGOS_RED: {len(CODIGOS_RED)}")
