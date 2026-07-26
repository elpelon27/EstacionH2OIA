"""Payment Skill — Validación de pagos Pago Móvil vía OCR con Qwen2.5-VL."""
from typing import Any
import httpx
import json
import base64
import ollama
from skills.base_skill import BaseSkill

class PaymentSkill(BaseSkill):
    def __init__(self) -> None:
        super().__init__("payment")

    async def execute(self, **kwargs: Any) -> dict[str, Any]:
        image_url = kwargs.get("image_url")
        expected_amount = kwargs.get("expected_amount")
        order_id = kwargs.get("order_id")

        if not image_url:
            return self._error("Falta image_url")

        try:
            image_data = await self._download_image(image_url)
            if not image_data:
                return self._error("No se pudo descargar imagen")

            extracted = await self._extract_payment_data(image_data)
            if not extracted:
                return self._error("No se pudo extraer datos de la captura")

            verified = False
            amount_str = extracted.get("amount", "")
            if expected_amount and amount_str:
                try:
                    extracted_amount = float(amount_str.replace(",", "."))
                    verified = abs(extracted_amount - expected_amount) <= (expected_amount * 0.01)
                except ValueError:
                    verified = False

            return self._success({
                "verified": verified,
                "extracted_amount": amount_str,
                "reference": extracted.get("reference", ""),
                "bank": extracted.get("bank", ""),
                "date": extracted.get("date", ""),
                "order_id": order_id,
                "expected_amount": expected_amount,
            })
        except Exception as e:
            return self._error(f"Error procesando pago: {str(e)}")

    async def _download_image(self, url: str) -> bytes | None:
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.get(url)
                return resp.content if resp.status_code == 200 else None
        except Exception:
            return None

    async def _extract_payment_data(self, image_data: bytes) -> dict[str, str]:
        base64_image = base64.b64encode(image_data).decode("utf-8")
        prompt = """Analiza esta captura de Pago Móvil venezolano.
Extrae: amount, reference, bank, date, phone.
Retorna SOLO JSON: {"amount":"515.18","reference":"123","bank":"Banesco","date":"2026-06-28","phone":""}"""
        
        try:
            response = ollama.chat(
                model="qwen2.5:7b",
                messages=[{"role": "user", "content": prompt, "images": [base64_image]}],
            )
            text = response.get("message", {}).get("content", "")
            if "```json" in text:
                text = text.split("```json")[1].split("```")[0]
            return json.loads(text.strip())  # type: ignore[no-any-return]
        except Exception as e:
            self.logger.error("ocr_error", error=str(e))
            return {}
