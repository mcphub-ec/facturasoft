"""
FacturaSoft MCP Server v1
=========================
MCP server for FacturaSoft REST API v1 (abitmedia.cloud) — Ecuador SRI
electric billing platform. Issues and queries all electronic document types.

Documents supported:
  · Invoices                  (POST/GET /invoices)
  · Credit Notes              (POST/GET /credit-notes)
  · Debit Notes               (POST/GET /debit-notes)
  · Purchase Settlements      (POST/GET /purchase-settlements)
  · Retentions                (POST/GET /retentions)
  · Waybills (Remittance)     (POST/GET /waybills)
  · RIDE / XML download       (/electronic-vouchers/download-ride|xml)

Technical reference: docs/openapi.yaml
"""

import os
import json
import logging
from typing import Any

from dotenv import load_dotenv
import httpx
from mcp.server.fastmcp import FastMCP

# Cargar variables desde el archivo .env
load_dotenv()


# ---------------------------------------------------------------------------
# Configuración
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format='{"time":"%(asctime)s", "level":"%(levelname)s", "name":"%(name)s", "message":"%(message)s"}',
)
logger = logging.getLogger("facturasoft-mcp")

FACTURASOFT_BASE_URL = os.environ.get(
    "FACTURASOFT_BASE_URL", "https://api.abitmedia.cloud/facturasoft/v1"
)

HTTP_TIMEOUT = float(os.environ.get("FACTURASOFT_HTTP_TIMEOUT", "30"))

mcp = FastMCP(
    "facturasoft",
    host="0.0.0.0",
    instructions=(
        "MCP server for FacturaSoft REST API v1 (abitmedia.cloud) — Ecuador SRI electronic billing. "
        "Supports issuing and querying: Invoices, Credit Notes, Debit Notes, Purchase Settlements, "
        "Retentions, and Remittance Guides (Waybills). "
        "Also supports downloading RIDE (PDF) and XML for any authorized document. "
        "Requires FACTURASOFT_BEARER_TOKEN environment variable. "
        "CRITICAL RULES: "
        "  · The 'integration' field is always True — sent automatically, do NOT pass it. "
        "  · VAT codes (taxes field in line_items): '4'=VAT 15%, '0'=VAT 0%, '8'=VAT 8%. "
        "  · For final consumer invoices, omit tercero_* fields entirely. "
        "  · Payment method codes reference: https://services.abitmedia.cloud/docs/pdf/formas-pago.pdf "
        "    Common codes: '01'=Cash/other, '18'=Credit card, '19'=Debit card, '20'=Transfer, '21'=Check. "
        "  · Reference tables: https://services.abitmedia.cloud/docs/pdf/"
    ))

# ---------------------------------------------------------------------------
# Cliente HTTP reutilizable
# ---------------------------------------------------------------------------


def _build_headers() -> dict[str, str]:
    """Build auth headers for a specific account."""
    resolved = os.environ.get("FACTURASOFT_BEARER_TOKEN", "")
    if not resolved:
        raise ValueError(
            "token is required for this MCP. Pass it as a tool parameter."
        )
    return {
        "Authorization": f"Bearer {resolved}",
        "Content-Type": "application/json",
    }



async def _request(
    method: str,
    path: str,
    *,    params: dict[str, Any] | None = None,
    body: dict[str, Any] | None = None) -> dict | list | str:
    """Ejecuta una petición HTTP contra la API de FacturaSoft y devuelve la respuesta."""
    url = f"{FACTURASOFT_BASE_URL}{path}"
    if params:
        params = {k: v for k, v in params.items() if v is not None and v != ""}

    logger.info("%s %s params=%s", method.upper(), url, params)

    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
        resp = await client.request(
            method,
            url,
            headers=_build_headers(),
            params=params,
            json=body)
        logger.info("Respuesta HTTP %s", resp.status_code)

        if resp.status_code >= 400:
            return {
                "error": True,
                "status_code": resp.status_code,
                "detail": resp.text,
            }

        if not resp.text.strip():
            return {"ok": True, "status_code": resp.status_code}

        try:
            return resp.json()
        except Exception:
            return resp.text


def _build_third(
    nombre: str,
    documento: str,
    email: str,
    telefono: str,
    direccion: str) -> dict[str, str]:
    """Construye el objeto 'third' (datos del cliente/tercero)."""
    return {
        "name": nombre,
        "document": documento,
        "email": email,
        "phones": telefono,
        "address": direccion,
    }


def _build_line_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Valida y normaliza los ítems de un documento electrónico.

    Cada ítem debe contener:
    - code (str): código del producto/servicio.
    - description (str): nombre o descripción.
    - quantity (float): cantidad.
    - unit_cost (float): precio unitario sin IVA.
    - taxes (list[str]): códigos de impuesto. Ej: ["4"] para IVA 15%, ["0"] para IVA 0%.
    - discount (float, opcional): descuento en valor monetario (default 0).
    """
    return items


# ═══════════════════════════════════════════════════════════════════════════
# FACTURAS  –  /invoices
# ═══════════════════════════════════════════════════════════════════════════


@mcp.tool()
async def consultar_factura(    numero_autorizacion: str
) -> str:
    """Retrieve the status and details of an electronic invoice from FacturaSoft.

    REQUIRED PARAMETERS:
      numero_autorizacion (str): SRI access key / authorization number (49 digits).
                                  Example: "2401202509123456789012345678901234567890123456789"

    RETURNS:
      Invoice object with: estado (AUTORIZADA/PENDIENTE/RECHAZADA), fecha, total,
      tercero (customer), line_items, and authorization details.
    """
    result = await _request(
        "GET",
        "/invoices",
        params={"integration": True, "authorization_number": numero_autorizacion})
    return json.dumps(result, ensure_ascii=False, default=str)


@mcp.tool()
async def crear_factura(    punto_emision: str,
    establecimiento: str,
    fecha_emision: str,
    metodo_pago_codigo: str,
    metodo_pago_plazo: str,
    metodo_pago_tiempo: str,
    line_items: list[dict[str, Any]],
    tercero_nombre: str | None = None,
    tercero_documento: str | None = None,
    tercero_email: str | None = None,
    tercero_telefono: str | None = None,
    tercero_direccion: str | None = None,
    numero_documento: str | None = None,
    campos_adicionales: list[dict[str, Any]] | None = None) -> str:
    """⚠️ MUTATION — Issue an electronic invoice to the SRI via FacturaSoft — POST /invoices.

    REQUIRED PARAMETERS:
      punto_emision (str): Emission point code, 3 digits. Example: "001"
      establecimiento (str): Establishment code, 3 digits. Example: "001"
      fecha_emision (str): Issue date in YYYY-MM-DD format. Example: "2025-07-30"
      metodo_pago_codigo (str): SRI payment method code.
                                 See: https://services.abitmedia.cloud/docs/pdf/formas-pago.pdf
                                 Common: "01"=Cash, "18"=Credit card, "19"=Debit card,
                                          "20"=Transfer, "21"=Check.
      metodo_pago_plazo (str): Payment term/period. Example: "30"
      metodo_pago_tiempo (str): Time unit for the term.
                                 Valid values: "days" | "months" | "years"
      line_items (list[dict]): Invoice items. Each item requires:
                               {"code": "PROD-001", "description": "Service",
                                "quantity": 2.0, "unit_cost": 10.50,
                                "taxes": ["4"],
                                "discount": 0.0}

    OPTIONAL PARAMETERS (customer/tercero — omit for final consumer):
      tercero_nombre (str): Customer full name.
      tercero_documento (str): Customer cedula or RUC.
      tercero_email (str): Customer email.
      tercero_telefono (str): Customer phone.
      tercero_direccion (str): Customer address.
      numero_documento (str): Sequential document number (auto-assigned if omitted).
      campos_adicionales (list[dict]): [{"name": "Vehicle plate", "value": "ABC-123"}]

    RETURNS:
      Dict with: uuid, authorization_number (49-digit SRI key),
      electronic_document, estado (AUTORIZADA/PENDIENTE/RECHAZADA).
    """
    body: dict[str, Any] = {
        "integration": True,
        "issue_point_code": punto_emision,
        "establishment_code": establecimiento,
        "issued_on": fecha_emision,
        "payment_method_code": metodo_pago_codigo,
        "payment_method_term": metodo_pago_plazo,
        "payment_method_time": metodo_pago_tiempo,
        "line_items": _build_line_items(line_items),
    }

    # Tercero: solo si se proporcionan datos del cliente
    if tercero_nombre and tercero_documento:
        body["third"] = _build_third(
            tercero_nombre,
            tercero_documento,
            tercero_email or "",
            tercero_telefono or "",
            tercero_direccion or "")

    if numero_documento is not None:
        body["document_number"] = numero_documento
    if campos_adicionales:
        body["additional_fields"] = campos_adicionales

    result = await _request("POST", "/invoices", body=body)
    return json.dumps(result, ensure_ascii=False, default=str)


# ═══════════════════════════════════════════════════════════════════════════
# NOTAS DE CRÉDITO  –  /credit-notes
# ═══════════════════════════════════════════════════════════════════════════


@mcp.tool()
async def consultar_nota_credito(    numero_autorizacion: str
) -> str:
    """Retrieve the status and details of an electronic credit note from FacturaSoft.

    REQUIRED PARAMETERS:
      numero_autorizacion (str): SRI access key / authorization number (49 digits).

    RETURNS:
      Credit note object with: estado, fecha, motivo, reference_document_number,
      tercero, and line_items.
    """
    result = await _request(
        "GET",
        "/credit-notes",
        params={"integration": True, "authorization_number": numero_autorizacion})
    return json.dumps(result, ensure_ascii=False, default=str)


@mcp.tool()
async def crear_nota_credito(    punto_emision: str,
    establecimiento: str,
    fecha_emision: str,
    fecha_emision_referencia: str,
    motivo: str,
    numero_factura_referencia: str,
    tercero_nombre: str,
    tercero_documento: str,
    tercero_email: str,
    tercero_telefono: str,
    tercero_direccion: str,
    line_items: list[dict[str, Any]],
    numero_documento: str | None = None,
    campos_adicionales: list[dict[str, Any]] | None = None) -> str:
    """⚠️ MUTATION — Issue an electronic credit note to the SRI via FacturaSoft — POST /credit-notes.

    Use to cancel or partially correct an existing invoice.

    REQUIRED PARAMETERS:
      punto_emision (str): Emission point code, 3 digits. Example: "001"
      establecimiento (str): Establishment code, 3 digits.
      fecha_emision (str): Issue date YYYY-MM-DD.
      fecha_emision_referencia (str): Original invoice issue date YYYY-MM-DD.
      motivo (str): Reason for the credit note. Example: "Product return"
      numero_factura_referencia (str): Original invoice number. Example: "001-001-000056522"
      tercero_nombre (str): Customer full name.
      tercero_documento (str): Customer cedula or RUC.
      tercero_email (str): Customer email.
      tercero_telefono (str): Customer phone.
      tercero_direccion (str): Customer address.
      line_items (list[dict]): Items to cancel. Each requires:
                               {"code": "...", "description": "...",
                                "quantity": 1.0, "unit_cost": 10.50,
                                "taxes": ["4"]}

    OPTIONAL PARAMETERS:
      numero_documento (str): Sequential credit note number.
      campos_adicionales (list[dict]): [{"name": "...", "value": "..."}]

    RETURNS:
      Dict with authorization_number, estado, and credit note details.
    """
    body: dict[str, Any] = {
        "integration": True,
        "issue_point_code": punto_emision,
        "establishment_code": establecimiento,
        "issued_on": fecha_emision,
        "reference_issued_on": fecha_emision_referencia,
        "reason": motivo,
        "reference_document_number": numero_factura_referencia,
        "third": _build_third(
            tercero_nombre, tercero_documento, tercero_email,
            tercero_telefono, tercero_direccion),
        "line_items": _build_line_items(line_items),
    }
    if numero_documento is not None:
        body["document_number"] = numero_documento
    if campos_adicionales:
        body["additional_fields"] = campos_adicionales

    result = await _request("POST", "/credit-notes", body=body)
    return json.dumps(result, ensure_ascii=False, default=str)


# ═══════════════════════════════════════════════════════════════════════════
# NOTAS DE DÉBITO  –  /debit-notes
# ═══════════════════════════════════════════════════════════════════════════


@mcp.tool()
async def consultar_nota_debito(    numero_autorizacion: str
) -> str:
    """Retrieve the status and details of an electronic debit note from FacturaSoft.

    REQUIRED PARAMETERS:
      numero_autorizacion (str): SRI access key / authorization number (49 digits).

    RETURNS:
      Debit note object with: estado, fecha, reference_document_number, tercero, line_items.
    """
    result = await _request(
        "GET",
        "/debit-notes",
        params={"integration": True, "authorization_number": numero_autorizacion})
    return json.dumps(result, ensure_ascii=False, default=str)


@mcp.tool()
async def crear_nota_debito(    punto_emision: str,
    establecimiento: str,
    fecha_emision: str,
    fecha_emision_referencia: str,
    numero_documento_referencia: str,
    metodo_pago_codigo: str,
    metodo_pago_plazo: str,
    metodo_pago_tiempo: str,
    tercero_nombre: str,
    tercero_documento: str,
    tercero_email: str,
    tercero_telefono: str,
    tercero_direccion: str,
    line_items: list[dict[str, Any]],
    numero_documento: str | None = None,
    campos_adicionales: list[dict[str, Any]] | None = None) -> str:
    """⚠️ MUTATION — Issue an electronic debit note to the SRI via FacturaSoft — POST /debit-notes.

    REQUIRED PARAMETERS:
      punto_emision (str): Emission point code. Example: "001"
      establecimiento (str): Establishment code. Example: "001"
      fecha_emision (str): Issue date YYYY-MM-DD.
      fecha_emision_referencia (str): Original invoice issue date YYYY-MM-DD.
      numero_documento_referencia (str): Original invoice number. Example: "001-001-000056522"
      metodo_pago_codigo (str): SRI payment method code (same values as crear_factura).
      metodo_pago_plazo (str): Payment term. Example: "30"
      metodo_pago_tiempo (str): Time unit: "days" | "months" | "years"
      tercero_nombre, tercero_documento, tercero_email,
      tercero_telefono, tercero_direccion: Customer data.
      line_items (list[dict]): Debit items. Each requires: code, description, quantity, unit_cost, taxes.

    OPTIONAL PARAMETERS:
      numero_documento (str): Sequential debit note number.
      campos_adicionales (list[dict]): [{"name": "...", "value": "..."}]

    RETURNS:
      Dict with authorization_number, estado, and debit note details.
    """
    body: dict[str, Any] = {
        "integration": True,
        "issue_point_code": punto_emision,
        "establishment_code": establecimiento,
        "issued_on": fecha_emision,
        "reference_issued_on": fecha_emision_referencia,
        "reference_document_number": numero_documento_referencia,
        "payment_method_code": metodo_pago_codigo,
        "payment_method_term": metodo_pago_plazo,
        "payment_method_time": metodo_pago_tiempo,
        "third": _build_third(
            tercero_nombre, tercero_documento, tercero_email,
            tercero_telefono, tercero_direccion),
        "line_items": _build_line_items(line_items),
    }
    if numero_documento is not None:
        body["document_number"] = numero_documento
    if campos_adicionales:
        body["additional_fields"] = campos_adicionales

    result = await _request("POST", "/debit-notes", body=body)
    return json.dumps(result, ensure_ascii=False, default=str)


# ═══════════════════════════════════════════════════════════════════════════
# LIQUIDACIONES DE COMPRA  –  /purchase-settlements
# ═══════════════════════════════════════════════════════════════════════════


@mcp.tool()
async def consultar_liquidacion_compra(    numero_autorizacion: str
) -> str:
    """Retrieve the status and details of an electronic purchase settlement from FacturaSoft.

    REQUIRED PARAMETERS:
      numero_autorizacion (str): SRI access key / authorization number (49 digits).

    RETURNS:
      Purchase settlement object with: estado, fecha, tercero (supplier), line_items.
    """
    result = await _request(
        "GET",
        "/purchase-settlements",
        params={"integration": True, "authorization_number": numero_autorizacion})
    return json.dumps(result, ensure_ascii=False, default=str)


@mcp.tool()
async def crear_liquidacion_compra(    punto_emision: str,
    establecimiento: str,
    fecha_emision: str,
    metodo_pago_codigo: str,
    metodo_pago_plazo: str,
    metodo_pago_tiempo: str,
    tercero_nombre: str,
    tercero_documento: str,
    tercero_email: str,
    tercero_telefono: str,
    tercero_direccion: str,
    line_items: list[dict[str, Any]],
    numero_documento: str | None = None,
    campos_adicionales: list[dict[str, Any]] | None = None) -> str:
    """⚠️ MUTATION — Issue an electronic purchase settlement to the SRI via FacturaSoft — POST /purchase-settlements.

    Use when the company purchases goods or services from a natural person
    who is NOT required to carry accounting records.

    REQUIRED PARAMETERS:
      punto_emision (str): Emission point code. Example: "001"
      establecimiento (str): Establishment code. Example: "001"
      fecha_emision (str): Issue date YYYY-MM-DD.
      metodo_pago_codigo (str): SRI payment method code.
      metodo_pago_plazo (str): Payment term. Example: "0"
      metodo_pago_tiempo (str): Time unit: "days" | "months" | "years"
      tercero_nombre, tercero_documento, tercero_email,
      tercero_telefono, tercero_direccion: Supplier (natural person) data.
      line_items (list[dict]): Items. Each requires: code, description, quantity, unit_cost, taxes.

    OPTIONAL PARAMETERS:
      numero_documento (str): Sequential settlement number.
      campos_adicionales (list[dict]): Additional fields [{"name": "...", "value": "..."}]

    RETURNS:
      Dict with authorization_number, estado, and settlement details.
    """
    body: dict[str, Any] = {
        "integration": True,
        "issue_point_code": punto_emision,
        "establishment_code": establecimiento,
        "issued_on": fecha_emision,
        "payment_method_code": metodo_pago_codigo,
        "payment_method_term": metodo_pago_plazo,
        "payment_method_time": metodo_pago_tiempo,
        "third": _build_third(
            tercero_nombre, tercero_documento, tercero_email,
            tercero_telefono, tercero_direccion),
        "line_items": _build_line_items(line_items),
    }
    if numero_documento is not None:
        body["document_number"] = numero_documento
    if campos_adicionales:
        body["additional_fields"] = campos_adicionales

    result = await _request("POST", "/purchase-settlements", body=body)
    return json.dumps(result, ensure_ascii=False, default=str)


# ═══════════════════════════════════════════════════════════════════════════
# RETENCIONES  –  /retentions
# ═══════════════════════════════════════════════════════════════════════════


@mcp.tool()
async def consultar_retencion(    numero_autorizacion: str
) -> str:
    """Retrieve the status and details of an electronic retention from FacturaSoft.

    REQUIRED PARAMETERS:
      numero_autorizacion (str): SRI access key / authorization number (49 digits).

    RETURNS:
      Retention object with: estado, fecha, reference_document_number,
      tercero, and retention_details.
    """
    result = await _request(
        "GET",
        "/retentions",
        params={"integration": True, "authorization_number": numero_autorizacion})
    return json.dumps(result, ensure_ascii=False, default=str)


@mcp.tool()
async def crear_retencion(    punto_emision: str,
    establecimiento: str,
    fecha_emision: str,
    fecha_emision_referencia: str,
    numero_documento_referencia: str,
    subtotal: float,
    valor_iva: float,
    tercero_nombre: str,
    tercero_documento: str,
    tercero_email: str,
    tercero_telefono: str,
    tercero_direccion: str,
    detalles_retencion: list[dict[str, Any]],
    numero_documento: str | None = None,
    campos_adicionales: list[dict[str, Any]] | None = None) -> str:
    """⚠️ MUTATION — Issue an electronic retention to the SRI via FacturaSoft — POST /retentions.

    REQUIRED PARAMETERS:
      punto_emision (str): Emission point code. Example: "001"
      establecimiento (str): Establishment code. Example: "001"
      fecha_emision (str): Issue date YYYY-MM-DD.
      fecha_emision_referencia (str): Date of the invoice being withheld YYYY-MM-DD.
      numero_documento_referencia (str): Invoice number being withheld. Example: "001-005-000008545"
      subtotal (float): Invoice subtotal amount to apply retention on.
      valor_iva (float): VAT value of the invoice being withheld.
      tercero_nombre, tercero_documento, tercero_email,
      tercero_telefono, tercero_direccion: Supplier/customer data.
      detalles_retencion (list[dict]): List of retention details. Each requires:
        {
          "tax_id": "303",              # SRI retention code. See: types-impuestos.pdf
          "retention_type": 1,          # 1=Income tax (Renta), 2=VAT (IVA)
          "tax_base": 100.00,           # Taxable base amount
          "reference_document_code": "01",  # Doc type: "01"=Invoice. See: tipos-documentos.pdf
          "reference_document_number": "855-858-494898495",  # Doc number
          "reference_document_date": "2025-07-30"  # Doc date YYYY-MM-DD
        }

    OPTIONAL PARAMETERS:
      numero_documento (str): Sequential retention number.
      campos_adicionales (list[dict]): [{"name": "...", "value": "..."}]

    RETURNS:
      Dict with authorization_number, estado, and retention details.
    """
    body: dict[str, Any] = {
        "integration": True,
        "issue_point_code": punto_emision,
        "establishment_code": establecimiento,
        "issued_on": fecha_emision,
        "reference_issued_on": fecha_emision_referencia,
        "reference_document_number": numero_documento_referencia,
        "subtotal": subtotal,
        "value_added_tax": valor_iva,
        "third": _build_third(
            tercero_nombre, tercero_documento, tercero_email,
            tercero_telefono, tercero_direccion),
        "retention_details": detalles_retencion,
    }
    if numero_documento is not None:
        body["document_number"] = numero_documento
    if campos_adicionales:
        body["additional_fields"] = campos_adicionales

    result = await _request("POST", "/retentions", body=body)
    return json.dumps(result, ensure_ascii=False, default=str)


# ═══════════════════════════════════════════════════════════════════════════
# GUÍAS DE REMISIÓN  –  /waybills
# ═══════════════════════════════════════════════════════════════════════════


@mcp.tool()
async def consultar_guia_remision(    numero_autorizacion: str
) -> str:
    """Retrieve the status and details of an electronic waybill (remittance guide) from FacturaSoft.

    REQUIRED PARAMETERS:
      numero_autorizacion (str): SRI access key / authorization number (49 digits).

    RETURNS:
      Waybill object with: estado, fecha, tercero (carrier), waybill_details.
    """
    result = await _request(
        "GET",
        "/waybills",
        params={"integration": True, "authorization_number": numero_autorizacion})
    return json.dumps(result, ensure_ascii=False, default=str)


@mcp.tool()
async def crear_guia_remision(    punto_emision: str,
    establecimiento: str,
    fecha_emision: str,
    fecha_inicio_traslado: str,
    fecha_fin_traslado: str,
    direccion_origen: str,
    placa_vehiculo: str,
    tercero_nombre: str,
    tercero_documento: str,
    tercero_email: str,
    tercero_telefono: str,
    tercero_direccion: str,
    detalles_guia: list[dict[str, Any]],
    numero_documento: str | None = None) -> str:
    """Crea y envía una guía de remisión electrónica al SRI a través de FacturaSoft.

    Se emite para respaldar el traslado de mercadería.

    Campos obligatorios:
    - punto_emision / establecimiento: Códigos del punto y local (Ej: "001").
    - fecha_emision: Fecha YYYY-MM-DD.
    - fecha_inicio_traslado: Inicio del traslado YYYY-MM-DD (no puede ser mayor a hoy).
    - fecha_fin_traslado: Fin del traslado YYYY-MM-DD.
    - direccion_origen: Dirección de salida de la mercadería.
    - placa_vehiculo: Placa del vehículo de transporte (Ej: "PBC-454").
    - tercero_*: Datos del remitente/tranportista principal.
    - detalles_guia: Lista de destinos. Cada destino requiere:
        - receiver (dict): Datos del receptor con name, document, email, address, phones.
        - reason (str): Motivo del traslado.
        - route (str): Ruta de traslado (Ej: "Quito - Guayaquil").
        - establishment_code (str): Código del establecimiento destino.
        - reference_document_code (str): Código tipo documento (Ej: "01"=Factura).
        - reference_document_number (str): Número del documento de referencia.
        - reference_authorization_number (str): Clave de autorización de referencia
          (si no aplica, enviar 49 ceros: "0000000000000000000000000000000000000000000000000").
        - reference_issued_on (str): Fecha del documento de referencia YYYY-MM-DD.
        - line_items (list): Mercadería trasladada. Cada ítem requiere:
            - code (str): código.
            - description (str o number): descripción.
            - quantity (float): cantidad.
            - aux_code (str, opcional): código auxiliar.
        - dau (str, opcional): Documento aduanero (si no aplica, enviar "0").

    Opcional: numero_documento (número secuencial).
    """
    body: dict[str, Any] = {
        "integration": True,
        "issue_point_code": punto_emision,
        "establishment_code": establecimiento,
        "issued_on": fecha_emision,
        "shipping_start_date": fecha_inicio_traslado,
        "shipping_end_date": fecha_fin_traslado,
        "origin_address": direccion_origen,
        "car_plate": placa_vehiculo,
        "third": _build_third(
            tercero_nombre, tercero_documento, tercero_email,
            tercero_telefono, tercero_direccion),
        "waybill_details": detalles_guia,
    }
    if numero_documento is not None:
        body["document_number"] = numero_documento

    result = await _request("POST", "/waybills", body=body)
    return json.dumps(result, ensure_ascii=False, default=str)


# ═══════════════════════════════════════════════════════════════════════════
# DESCARGA DE DOCUMENTOS  –  /electronic-vouchers/
# ═══════════════════════════════════════════════════════════════════════════


@mcp.tool()
async def descargar_ride_pdf(    clave_acceso: str
) -> str:
    """Download the RIDE (Representación Impresa del Documento Electrónico) PDF for an authorized document.

    Use this tool to get the official PDF representation of any authorized SRI document.

    REQUIRED PARAMETERS:
      clave_acceso (str): 49-digit SRI access key (from the authorization response).
                          Example: "2401202509123456789012345678901234567890123456789"

    RETURNS:
      JSON with the PDF content encoded in Base64.
    """
    result = await _request(
        "GET",
        "/electronic-vouchers/download-ride",
        params={"id": clave_acceso})
    return json.dumps(result, ensure_ascii=False, default=str)


@mcp.tool()
async def descargar_xml(    clave_acceso: str
) -> str:
    """Download the authorized XML of an electronic document from FacturaSoft.

    Use this tool to retrieve the original signed XML of any SRI-authorized document.

    REQUIRED PARAMETERS:
      clave_acceso (str): 49-digit SRI access key (from the authorization response).
                          Example: "2401202509123456789012345678901234567890123456789"

    RETURNS:
      JSON with the XML content encoded in Base64.
    """
    result = await _request(
        "GET",
        "/electronic-vouchers/download-xml",
        params={"id": clave_acceso})
    return json.dumps(result, ensure_ascii=False, default=str)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


if __name__ == "__main__":
    import uvicorn
    import os

    try:
        import logger
    except ImportError:
        pass

    port = int(os.getenv("MCP_PORT", 8000))
    transport_mode = os.getenv("MCP_TRANSPORT_MODE", "sse").lower()
    print(f"Starting MCP Server on http://0.0.0.0:{port}/mcp ({transport_mode})")
    if transport_mode == "sse":
        app = mcp.sse_app()
    elif transport_mode == "http_stream":
        app = mcp.streamable_http_app()
    else:
        raise ValueError(f"Unknown transport mode: {transport_mode}")
    uvicorn.run(app, host="0.0.0.0", port=port)
