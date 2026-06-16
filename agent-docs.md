# Agent-First Documentation: FacturaSoft MCP Server

## 1. Contexto General
Servidor MCP para emisión de comprobantes mediante FacturaSoft (plataforma
Abitmedia Cloud). Autenticación con Bearer Token.

## 2. Tecnologías Principales
- **FastMCP 3.3.1**.
- **httpx**: Cliente HTTP asíncrono.
- Header `Authorization: Bearer <FACTURASOFT_BEARER_TOKEN>`.

## 3. Reglas de Negocio
- Cada tool genera un comprobante. Confirmar con el usuario.
- IVA Ecuador: 15% por defecto.
- Identificaciones: CEDULA (10), RUC (13), PASAPORTE, CONSUMIDOR_FINAL (9999999999999).

## 4. Variables de Entorno
- `FACTURASOFT_BEARER_TOKEN`: Token Bearer. **Nunca pasar como parámetro de tool**.
- `FACTURASOFT_BASE_URL`: URL base (default `https://api.abitmedia.cloud/facturasoft/v1`).
- `MCP_HOST`, `MCP_PORT`, `MCP_TRANSPORT_MODE`.

## 5. Herramientas Principales (14 totales)
- `crear_factura`: Emite una factura electrónica.
- `crear_nota_credito`: Nota de crédito.
- `consultar_estado`: Estado de comprobante.
- Y 11 más (clientes, productos, retenciones).

## 6. Consideraciones de Seguridad
- **IDEMPOTENCIA**: usar el campo `reference` único.
- No loguear `FACTURASOFT_BEARER_TOKEN` (filtrado automático).

## 7. Tests
- Pendiente: añadir cobertura mínima.
