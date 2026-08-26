#!/usr/bin/env python3
"""
Odoo XML-RPC Client for Estación H2O
Sincroniza pedidos, pagos, inventario y facturación entre Valentina y Odoo.
"""

import logging
import xmlrpc.client
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any, cast

logger = logging.getLogger("odoo_sync")


class DocumentType(Enum):
    INVOICE = "invoice"  # Factura electrónica
    DELIVERY_NOTE = "delivery_note"  # Nota de entrega


@dataclass
class OdooConfig:
    url: str = "http://localhost:8069"
    db: str = "postgres"
    username: str = "admin"
    password: str = "admin"


class OdooClient:
    """Cliente XML-RPC para Odoo Community 17"""

    def __init__(self, config: OdooConfig | None = None):
        self.config = config or OdooConfig()
        self._common: xmlrpc.client.ServerProxy | None = None
        self._models: xmlrpc.client.ServerProxy | None = None
        self._uid: int | None = None

    def connect(self) -> bool:
        """Conecta y autentica con Odoo"""
        try:
            common = xmlrpc.client.ServerProxy(f"{self.config.url}/xmlrpc/2/common")
            models = xmlrpc.client.ServerProxy(f"{self.config.url}/xmlrpc/2/object")
            uid = cast(
                int | None,
                common.authenticate(self.config.db, self.config.username, self.config.password, {}),
            )
            if uid:
                self._common = common
                self._models = models
                self._uid = uid
                logger.info(f"Odoo connected successfully (uid={uid})")
                return True
            else:
                logger.error("Odoo authentication failed")
                return False
        except Exception as e:
            logger.error(f"Odoo connection error: {e}")
            return False

    @property
    def connected(self) -> bool:
        return self._uid is not None

    def _ensure_connected(self) -> None:
        if not self.connected and not self.connect():
            raise RuntimeError("Cannot connect to Odoo")

    def execute_kw(
        self,
        model: str,
        method: str,
        args: list[Any],
        kwargs: dict[str, Any] | None = None,
    ) -> Any:
        """Ejecuta método en modelo Odoo"""
        self._ensure_connected()
        assert self._models is not None and self._uid is not None
        return self._models.execute_kw(
            self.config.db, self._uid, self.config.password, model, method, args, kwargs or {}
        )

    # ============================================================
    # CLIENTES (res.partner)
    # ============================================================

    def get_or_create_partner(
        self,
        name: str,
        vat: str = "",
        phone: str = "",
        street: str = "",
        city: str = "Maracaibo",
        country_id: int = 238,
    ) -> int:
        """Busca o crea un cliente (partner) por RIF/VAT"""
        # Buscar por VAT si se proporciona
        if vat:
            partners = self.execute_kw(
                "res.partner",
                "search_read",
                [[("vat", "=", vat)]],
                {"fields": ["id", "name", "vat"], "limit": 1},
            )
            if partners:
                logger.info(f"Partner existente: {partners[0]['name']} (ID={partners[0]['id']})")
                return cast(int, partners[0]["id"])

        # Buscar por nombre + teléfono
        if phone:
            partners = self.execute_kw(
                "res.partner",
                "search_read",
                [[("phone", "=", phone)]],
                {"fields": ["id", "name", "phone"], "limit": 1},
            )
            if partners:
                logger.info(
                    f"Partner existente por teléfono: "
                    f"{partners[0]['name']} (ID={partners[0]['id']})"
                )
                return cast(int, partners[0]["id"])

        # Crear nuevo
        partner_vals = {
            "name": name,
            "vat": vat,
            "phone": phone,
            "street": street,
            "city": city,
            "country_id": country_id,
            "customer_rank": 1,
            "supplier_rank": 0,
            "lang": "es_419",  # Spanish (Latin America)
        }
        partner_id = self.execute_kw("res.partner", "create", [partner_vals])
        logger.info(f"Partner creado: {name} (ID={partner_id})")
        return cast(int, partner_id)

    # ============================================================
    # PRODUCTOS
    # ============================================================

    def get_product_by_name(self, name: str) -> dict[str, Any] | None:
        """Busca producto por nombre exacto"""
        products = self.execute_kw(
            "product.template",
            "search_read",
            [[("name", "=", name)]],
            {"fields": ["id", "name", "list_price", "uom_id", "taxes_id"], "limit": 1},
        )
        return products[0] if products else None

    def get_product_price(self, name: str) -> float | None:
        """Obtiene precio de venta de un producto"""
        product = self.get_product_by_name(name)
        return product["list_price"] if product else None

    # ============================================================
    # PEDIDOS (sale.order) y NOTAS DE ENTREGA (stock.picking)
    # ============================================================

    def create_sale_order(
        self,
        partner_id: int,
        order_lines: list[dict[str, Any]],
        payment_term_id: int | None = None,
        note: str = "",
    ) -> int:
        """
        Crea sale.order (factura) en Odoo
        order_lines: [{'product_id': int, 'quantity': float, 'price_unit': float, 'tax_id': int}]
        """
        order_vals = {
            "partner_id": partner_id,
            "order_line": [(0, 0, line) for line in order_lines],
            "note": note,
            "state": "draft",  # Queda en borrador para aprobación
        }
        if payment_term_id:
            order_vals["payment_term_id"] = payment_term_id
        order_id = self.execute_kw("sale.order", "create", [order_vals])
        logger.info(f"Sale order creado: ID={order_id}")
        return cast(int, order_id)

    def create_delivery_note(
        self, partner_id: int, items: list[dict[str, Any]], origin: str = ""
    ) -> int:
        """
        Crea stock.picking (nota de entrega) en Odoo
        items: [{'product_id': int, 'quantity': float, 'location_id': int, 'location_dest_id': int}]
        """
        # Buscar tipo de operación: Entrega
        picking_type = self.execute_kw(
            "stock.picking.type",
            "search_read",
            [[("code", "=", "outgoing")]],
            {"fields": ["id", "default_location_src_id", "default_location_dest_id"], "limit": 1},
        )

        if not picking_type:
            raise ValueError("No hay tipo de operación 'Entrega' configurado")

        pt = picking_type[0]

        # Usar ubicaciones por defecto o fallback
        # Location source: WH/Stock (internal)
        location_id = pt["default_location_src_id"][0] if pt["default_location_src_id"] else 8
        # Location destination: Customers (customer) - fallback to ID 5
        location_dest_id = (
            pt["default_location_dest_id"][0] if pt["default_location_dest_id"] else 5
        )

        move_lines = []
        for item in items:
            # Get product price if not provided
            price_unit = item.get("price_unit")
            if price_unit is None:
                product = self.get_product_by_name(item.get("product_name", ""))
                if product:
                    price_unit = product["list_price"]
                else:
                    # Try to get from product_id
                    prod = self.execute_kw(
                        "product.template",
                        "read",
                        [[item["product_id"]]],
                        {"fields": ["list_price"]},
                    )
                    price_unit = prod[0]["list_price"] if prod else 0.0

            move_lines.append(
                (
                    0,
                    0,
                    {
                        "name": item.get("name", "Entrega"),
                        "product_id": item["product_id"],
                        "product_uom_qty": item["quantity"],
                        "product_uom": item.get("uom_id", 1),
                        "location_id": location_id,
                        "location_dest_id": location_dest_id,
                        "price_unit": price_unit,
                    },
                )
            )

        picking_vals = {
            "partner_id": partner_id,
            "picking_type_id": pt["id"],
            "move_ids_without_package": move_lines,
            "origin": origin,
            "state": "draft",
        }
        picking_id = self.execute_kw("stock.picking", "create", [picking_vals])
        logger.info(f"Delivery note (stock.picking) creado: ID={picking_id}")
        return cast(int, picking_id)

    def confirm_delivery_note(self, picking_id: int) -> bool:
        """Confirma y valida la nota de entrega (descuenta inventario)"""
        try:
            # 1. Action assign (reserve quantities)
            self.execute_kw("stock.picking", "action_assign", [[picking_id]])

            # 2. Create move lines with quantities if not already created
            picking = self.execute_kw(
                "stock.picking",
                "read",
                [[picking_id]],
                {
                    "fields": [
                        "move_ids_without_package",
                        "move_line_ids_without_package",
                        "picking_type_id",
                        "location_id",
                        "location_dest_id",
                    ]
                },
            )[0]

            if picking["move_ids_without_package"] and not picking["move_line_ids_without_package"]:
                # Get picking type locations
                pt = self.execute_kw(
                    "stock.picking.type",
                    "read",
                    [[picking["picking_type_id"][0]]],
                    {"fields": ["default_location_src_id", "default_location_dest_id"]},
                )[0]

                location_id = (
                    pt["default_location_src_id"][0] if pt["default_location_src_id"] else 8
                )
                location_dest_id = (
                    pt["default_location_dest_id"][0] if pt["default_location_dest_id"] else 5
                )

                # Create move lines for each move
                for move_id in picking["move_ids_without_package"]:
                    move = self.execute_kw(
                        "stock.move",
                        "read",
                        [[move_id]],
                        {
                            "fields": [
                                "product_id",
                                "product_uom_qty",
                                "product_uom",
                                "product_uom_category_id",
                            ]
                        },
                    )[0]

                    move_line_vals = {
                        "picking_id": picking_id,
                        "move_id": move_id,
                        "product_id": move["product_id"][0],
                        "product_uom_id": move["product_uom"][0],
                        "location_id": location_id,
                        "location_dest_id": location_dest_id,
                        "quantity": move["product_uom_qty"],
                        "product_uom_category_id": move["product_uom_category_id"][0]
                        if move["product_uom_category_id"]
                        else 1,
                    }
                    self.execute_kw("stock.move.line", "create", [move_line_vals])

            # 3. Validate the picking
            self.execute_kw(
                "stock.picking",
                "button_validate",
                [[picking_id]],
                {"context": {"skip_immediate": True, "skip_sms": True}},
            )

            logger.info(f"Delivery note {picking_id} confirmada y validada (inventario descontado)")
            return True
        except Exception as e:
            logger.error(f"Error confirmando delivery note {picking_id}: {e}")
            return False

    # ============================================================
    # CONVERSIÓN NOTA DE ENTREGA → FACTURA
    # ============================================================

    def convert_delivery_to_invoice(
        self, picking_id: int, partner_vat: str, partner_name: str, partner_street: str
    ) -> int | None:
        """
        Convierte una nota de entrega (stock.picking) en factura (sale.order + account.move)
        Sin duplicar inventario (referencia la nota original)
        """
        try:
            # 1. Obtener datos de la picking
            picking = self.execute_kw(
                "stock.picking",
                "read",
                [[picking_id]],
                {"fields": ["move_ids_without_package", "partner_id", "origin", "name"]},
            )[0]

            # 2. Crear sale.order a partir de los moves
            order_lines = []
            for move_id in picking["move_ids_without_package"]:
                move = self.execute_kw(
                    "stock.move",
                    "read",
                    [[move_id]],
                    {"fields": ["product_id", "product_uom_qty", "price_unit", "name"]},
                )[0]
                order_lines.append(
                    (
                        0,
                        0,
                        {
                            "product_id": move["product_id"][0],
                            "product_uom_qty": move["product_uom_qty"],
                            "price_unit": move["price_unit"] or 0,
                            "name": move.get("name", "Entrega convertida"),
                        },
                    )
                )

            # 3. Asegurar partner con RIF actualizado
            partner_data = self.execute_kw(
                "res.partner",
                "read",
                [[picking["partner_id"][0]]],
                {"fields": ["id", "name", "vat", "street"]},
            )[0]

            partner_id = partner_data["id"]  # Extract ID from many2one

            # Actualizar RIF si es nuevo
            if partner_vat and partner_vat != partner_data.get("vat"):
                self.execute_kw("res.partner", "write", [[partner_id], {"vat": partner_vat}])

            # 4. Crear sale.order vinculada a la picking original
            order_vals = {
                "partner_id": partner_id,
                "order_line": order_lines,
                "origin": f"ND-{picking.get('origin') or picking['name']}",
                # Referencia a nota original
                "note": (
                    f"Convertida de nota de entrega {picking['name']}. Inventario ya descontado."
                ),
                "state": "draft",
            }
            order_id = self.execute_kw("sale.order", "create", [order_vals])

            # 5. Crear factura (account.move) directamente desde sale.order
            # Confirmar el sale.order primero
            self.execute_kw("sale.order", "action_confirm", [[order_id]])

            # Crear invoice (account.move) manualmente
            invoice_vals = {
                "move_type": "out_invoice",
                "partner_id": partner_id,
                "invoice_origin": f"ND-{picking.get('origin') or picking['name']}",
                "invoice_line_ids": [
                    (
                        0,
                        0,
                        {
                            "product_id": line[2]["product_id"],
                            "quantity": line[2]["product_uom_qty"],
                            "price_unit": line[2]["price_unit"],
                            "name": line[2].get("name", "Entrega convertida"),
                        },
                    )
                    for line in order_lines
                ],
            }
            invoice_id = self.execute_kw("account.move", "create", [invoice_vals])

            # Post the invoice to make it official
            self.execute_kw("account.move", "action_post", [[invoice_id]])

            logger.info(
                "Nota de entrega "
                f"{picking['name']} convertida a Sale Order "
                f"{order_id} + Invoice {invoice_id}"
            )
            return cast(int, order_id)

        except Exception as e:
            logger.error(f"Error convirtiendo picking {picking_id} a factura: {e}")
            return None

    # ============================================================
    # PAGOS
    # ============================================================

    @staticmethod
    def _now() -> str:
        """Fecha actual en formato YYYY-MM-DD (extraída para pureza/testabilidad)."""
        return datetime.now().strftime("%Y-%m-%d")

    def register_payment(
        self,
        invoice_id: int,
        amount: float,
        payment_method: str = "pago_movil",
        reference: str = "",
        date: str | None = None,
    ) -> int | None:
        """Registra un pago en Odoo para una factura"""
        try:
            # Buscar journal de banco/pagos
            journal = self.execute_kw(
                "account.journal",
                "search_read",
                [[("type", "=", "bank")]],
                {"fields": ["id"], "limit": 1},
            )
            if not journal:
                journal = self.execute_kw(
                    "account.journal",
                    "search_read",
                    [[("type", "=", "cash")]],
                    {"fields": ["id"], "limit": 1},
                )
            if not journal:
                raise ValueError("No hay journal de banco/cash configurado")

            payment_vals = {
                "amount": amount,
                "payment_type": "inbound",
                "partner_type": "customer",
                "partner_id": self.execute_kw(
                    "account.move", "read", [[invoice_id]], {"fields": ["partner_id"]}
                )[0]["partner_id"][0],
                "journal_id": journal[0]["id"],
                "payment_method_id": self._get_payment_method_id("manual"),
                "ref": reference or f"Pago {payment_method}",
                "date": date or self._now(),
            }

            payment_id = self.execute_kw("account.payment", "create", [payment_vals])
            self.execute_kw("account.payment", "action_post", [[payment_id]])

            # Conciliar con factura
            self.execute_kw("account.payment", "reconcile", [[payment_id]])

            logger.info(f"Pago registrado: ID={payment_id} para factura {invoice_id}")
            return cast(int, payment_id)

        except Exception as e:
            logger.error(f"Error registrando pago para factura {invoice_id}: {e}")
            return None

    def _get_payment_method_id(self, name: str) -> int:
        """Obtiene ID de método de pago"""
        methods = self.execute_kw(
            "account.payment.method",
            "search_read",
            [[("name", "=", name)]],
            {"fields": ["id"], "limit": 1},
        )
        if methods:
            return cast(int, methods[0]["id"])
        # Fallback: primer método disponible
        all_methods = self.execute_kw(
            "account.payment.method", "search_read", [], {"fields": ["id"], "limit": 1}
        )
        return cast(int, all_methods[0]["id"]) if all_methods else 1

    # ============================================================
    # REPORTES / CONSULTAS
    # ============================================================

    def get_sales_report(self, date_from: str, date_to: str) -> list[dict[str, Any]]:
        """Reporte de ventas por período"""
        orders = self.execute_kw(
            "sale.order",
            "search_read",
            [
                ["date_order", ">=", date_from],
                ["date_order", "<=", date_to],
                ["state", "in", ["sale", "done"]],
            ],
            {
                "fields": [
                    "name",
                    "partner_id",
                    "amount_total",
                    "date_order",
                    "state",
                    "payment_term_id",
                ]
            },
        )
        return cast(list[dict[str, Any]], orders)

    def get_driver_commissions(self, date_from: str, date_to: str) -> dict[str, Any]:
        """
        Calcula comisiones por chofer basado en entregas confirmadas
        """
        # Buscar entregas confirmadas en el período
        pickings = self.execute_kw(
            "stock.picking",
            "search_read",
            [
                ["date_done", ">=", date_from],
                ["date_done", "<=", date_to],
                ["state", "=", "done"],
                ["picking_type_id.code", "=", "outgoing"],
            ],
            {"fields": ["name", "partner_id", "move_ids_without_package", "date_done"]},
        )

        commissions: dict[str, Any] = {}
        for _ in pickings:
            # Aquí se sumaría por chofer (requiere campo chofer en picking o en move)
            # Por ahora retorna estructura base
            pass

        return commissions

    def get_inventory_levels(self) -> dict[str, float]:
        """Niveles actuales de inventario"""
        quants = self.execute_kw(
            "stock.quant",
            "search_read",
            [["location_id.usage", "=", "internal"]],
            {"fields": ["product_id", "quantity", "location_id"]},
        )

        inventory: dict[str, float] = {}
        for q in quants:
            prod_name = q["product_id"][1] if q["product_id"] else "Unknown"
            if prod_name not in inventory:
                inventory[prod_name] = 0.0
            inventory[prod_name] += float(q["quantity"])

        return inventory


# Singleton global
_odoo_client: OdooClient | None = None


def get_odoo_client(config: OdooConfig | None = None) -> OdooClient:
    global _odoo_client
    if _odoo_client is None:
        _odoo_client = OdooClient(config)
        if not _odoo_client.connect():
            raise RuntimeError("No se pudo conectar a Odoo")
    return _odoo_client


def reset_odoo_client() -> None:
    global _odoo_client
    _odoo_client = None


if __name__ == "__main__":
    # Test rápido
    import os

    os.environ.setdefault("BRIDGE_ALLOW_INSECURE_SALT", "1")

    logging.basicConfig(level=logging.INFO)

    client = OdooClient()
    if client.connect():
        print("✅ Odoo connection successful")

        # Test products
        botellon = client.get_product_by_name("Botellón 20L")
        print(f"Botellón: {botellon}")

        hielo = client.get_product_by_name("Bolsa Hielo 5kg")
        print(f"Hielo: {hielo}")

        # Test inventory
        inv = client.get_inventory_levels()
        print(f"Inventory: {inv}")
    else:
        print("❌ Odoo connection failed")
