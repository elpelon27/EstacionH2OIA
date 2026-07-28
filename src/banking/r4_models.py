"""R4 Banco - Modelos Pydantic para requests/responses R4 Conecta V3.0"""

from pydantic import BaseModel, Field

# ============================================================================
# MODELOS BASE
# ============================================================================


class R4BaseResponse(BaseModel):
    """Respuesta base del banco"""

    code: str | None = None
    codigo: str | None = None
    message: str | None = None
    mensaje: str | None = None
    success: bool | None = None

    @property
    def response_code(self) -> str:
        return self.code or self.codigo or ""

    @property
    def response_message(self) -> str:
        return self.message or self.mensaje or ""

    @property
    def is_success(self) -> bool:
        return self.response_code in ("00", "202", "ACCP") or self.success is True


# ============================================================================
# CONSULTA TASA BCV (MBbcv)
# ============================================================================


class R4BcvRequest(BaseModel):
    Moneda: str = Field(default="USD", description="Código ISO moneda")
    Fechavalor: str = Field(..., description="Fecha consulta tasa BCV (yyyy-mm-dd)")


class R4BcvResponse(R4BaseResponse):
    fechavalor: str | None = None
    tipocambio: float | None = None


# ============================================================================
# CONSULTA CLIENTE / VALIDACIÓN PAGO MÓVIL (R4consulta)
# ============================================================================


class R4ConsultaRequest(BaseModel):
    IdCliente: str = Field(..., description="Identificación del cliente (requerido) - 8 numérico")
    Monto: str | None = Field(
        None, description="Monto de la operación - máx 8 números y 2 decimales"
    )
    TelefonoComercio: str | None = Field(None, description="Teléfono del comercio - 11 numérico")


class R4ConsultaResponse(BaseModel):
    status: bool


# ============================================================================
# NOTIFICACIÓN PAGO MÓVIL ENTRANTE (R4notifica)
# ============================================================================


class R4NotificaRequest(BaseModel):
    IdComercio: str = Field(..., description="Cédula o RIF del Comercio (requerido) - 8 numérico")
    TelefonoComercio: str = Field(
        ..., description="Teléfono del comercio (requerido) - 11 numérico"
    )
    TelefonoEmisor: str = Field(
        ..., description="Teléfono de origen del pago (requerido) - 11 numérico"
    )
    Concepto: str | None = Field(None, description="Motivo del pago (opcional) - 30 alfanumérico")
    BancoEmisor: str = Field(..., description="Código del banco del pago (requerido) - 3 numérico")
    Monto: str = Field(..., description="Monto con decimales separados por punto '.' (requerido)")
    FechaHora: str = Field(..., description="(requerido) - String ISO 8601")
    Referencia: str = Field(..., description="Referencia interbancaria (requerido) - String")
    CodigoRed: str = Field(
        ..., description="Código de respuesta de la red interbancaria (requerido) - String"
    )


class R4NotificaResponse(BaseModel):
    abono: bool


# ============================================================================
# VÍA SIMF - CONSULTA CLIENTE (MBconsulta)
# ============================================================================


class R4SimfConsultaRequest(BaseModel):
    IdComercio: str
    TelefonoComercio: str
    TelefonoEmisor: str
    Concepto: str
    BancoEmisor: str
    Monto: str
    FechaHora: str
    Referencia: str
    CodigoRed: str


class R4SimfConsultaResponse(BaseModel):
    abono: bool


# ============================================================================
# GESTIÓN DE PAGOS / DISPERSIÓN (R4pagos)
# ============================================================================


class R4PagosPersona(BaseModel):
    nombres: str = Field(..., description="Nombre y apellido del beneficiario")
    documento: str = Field(..., description="Documento de identidad (V/E/J/P + número)")
    destino: str = Field(..., description="Número de cuenta a abonar")
    monto_part: str = Field(
        ..., description="Monto parcial a repartir al beneficiario", alias="montoPart"
    )


class R4PagosRequest(BaseModel):
    monto: str = Field(
        ..., description="Monto total para la dispersión - máx 8 números y 2 decimales"
    )
    fecha: str = Field(..., description="Fecha del pago - Formato MM/DD/YYYY")
    Referencia: str = Field(..., description="String - 8 numérico")
    personas: list[R4PagosPersona]


class R4PagosResponse(R4BaseResponse):
    reference: str | None = None
    error: str | None = None


# ============================================================================
# R4 VUELTO (MBvuelto)
# ============================================================================


class R4VueltoRequest(BaseModel):
    TelefonoDestino: str = Field(..., description="Teléfono del beneficiario - 11 numérico")
    Cedula: str = Field(..., description="Tipo de Documento (V, E) + Documento - 9 alfanumérico")
    Banco: str = Field(..., description="Código del banco del beneficiario - 4 numérico")
    Monto: str = Field(
        ..., description="Monto con decimales separados por punto - máx 8 números y 2 decimales"
    )
    Concepto: str | None = Field(
        "PRUEBA", description="OPCIONAL - Motivo del pago - 30 alfanumérico"
    )
    Ip: str | None = Field("0.0.0.0", description="OPCIONAL - IP de la máquina - 8 numérico")


class R4VueltoResponse(R4BaseResponse):
    reference: str | None = None


# ============================================================================
# PROCESO DÉBITO INMEDIATO
# ============================================================================


class R4GenerarOtpRequest(BaseModel):
    Banco: str = Field(..., description="String - 4 numérico")
    Monto: str = Field(
        ..., description="Monto con decimales separados por punto - máx 8 números y 2 decimales"
    )
    Telefono: str = Field(..., description="String 11 numérico")
    Cedula: str = Field(..., description="String - 9 alfanumérico")


class R4GenerarOtpResponse(R4BaseResponse):
    id: str | None = None


class R4DebitoInmediatoRequest(BaseModel):
    Banco: str = Field(..., description="String - 4 numérico")
    Monto: str = Field(
        ..., description="Monto con decimales separados por punto - máx 8 números y 2 decimales"
    )
    Telefono: str = Field(..., description="String - 11 numérico")
    Cedula: str = Field(..., description="String - 9 alfanumérico")
    Nombre: str = Field(..., description="String - 20 alfa")
    OTP: str = Field(..., description="String - 8 numérico")
    Concepto: str = Field(..., description="String - 30 alfanumérico")


class R4DebitoInmediatoResponse(R4BaseResponse):
    id: str | None = None
    reference: str | None = None


# ============================================================================
# CONSULTAR OPERACIONES
# ============================================================================


class R4ConsultarOperacionesRequest(BaseModel):
    Id: str = Field(..., description="String - 36 alfanuméricos (UUID)")


class R4ConsultarOperacionesResponse(R4BaseResponse):
    reference: str | None = None


# ============================================================================
# DOMICILIACIÓN CUENTAS 20 DÍGITOS
# ============================================================================


class R4DomiciliacionCNTARequest(BaseModel):
    doc_id: str = Field(..., alias="docId")
    nombre: str
    cuenta: str
    monto: str
    concepto: str


class R4DomiciliacionCNTAResponse(R4BaseResponse):
    uuid: str | None = None
    codigo: str | None = None


# ============================================================================
# DOMICILIACIÓN POR TELÉFONO
# ============================================================================


class R4DomiciliacionCELERequest(BaseModel):
    doc_id: str
    telefono: str
    nombre: str
    banco: str
    monto: str
    concepto: str


class R4DomiciliacionCELEResponse(R4BaseResponse):
    uuid: str | None = None
    codigo: str | None = None


# ============================================================================
# CRÉDITO INMEDIATO
# ============================================================================


class R4CreditoInmediatoRequest(BaseModel):
    Banco: str = Field(..., description="String - 4 numérico")
    Cedula: str = Field(..., description="String - 9 alfanuméricos")
    Telefono: str = Field(..., description="String - 11 numérico")
    Monto: str = Field(
        ..., description="Monto con decimales separados por punto - máx 8 números y 2 decimales"
    )
    Concepto: str = Field(..., description="String - 30 alfanumérico")


class R4CreditoInmediatoResponse(R4BaseResponse):
    id: str | None = None
    reference: str | None = None


class R4CreditoInmediatoCuentaRequest(BaseModel):
    Cedula: str
    Cuenta: str
    Monto: str
    Concepto: str


class R4CreditoInmediatoCuentaResponse(R4BaseResponse):
    reference: str | None = None


# ============================================================================
# ANULACIÓN C2P
# ============================================================================


class R4AnulacionC2PRequest(BaseModel):
    Cedula: str
    Banco: str
    Referencia: str


class R4AnulacionC2PResponse(R4BaseResponse):
    reference: str | None = None


# ============================================================================
# COBRO C2P
# ============================================================================


class R4C2PRequest(BaseModel):
    TelefonoDestino: str = Field(..., description="11 numérico")
    Cedula: str = Field(..., description="9 alfanumérico")
    Concepto: str = Field(..., description="30 alfanumérico")
    Banco: str = Field(..., description="4 numérico")
    Ip: str = Field(..., description="String")
    Monto: str = Field(..., description="Máx 8 números y 2 decimales")
    Otp: str = Field(..., description="8 numérico")


class R4C2PResponse(R4BaseResponse):
    reference: str | None = None


# ============================================================================
# UTILIDADES
# ============================================================================


def is_success_response(response: R4BaseResponse) -> bool:
    """Verifica si la respuesta indica éxito"""
    return response.is_success


def get_reference(response: R4BaseResponse) -> str | None:
    """Extrae referencia de respuesta exitosa"""
    return getattr(response, "reference", None) or getattr(response, "id", None)
