import os
from typing import Any, Protocol


class TextractClient(Protocol):
    def analyze_expense(self, **kwargs: Any) -> dict[str, Any]: ...


class TextractNotConfigured(RuntimeError):
    pass


def _value(field: dict[str, Any]) -> str:
    detection = field.get("ValueDetection") or {}
    return str(detection.get("Text") or "").strip()


def _field_type(field: dict[str, Any]) -> str:
    detected = field.get("Type") or {}
    return str(detected.get("Text") or "").strip().upper().replace(" ", "_")


def normalize_textract_expense(response: dict[str, Any]) -> dict[str, Any]:
    summary: dict[str, str] = {}
    line_items: list[dict[str, str | None]] = []
    documents = response.get("ExpenseDocuments") or []
    for document in documents:
        for field in document.get("SummaryFields") or []:
            kind, value = _field_type(field), _value(field)
            if kind and value:
                summary.setdefault(kind, value)
        for group in document.get("LineItemGroups") or []:
            for line in group.get("LineItems") or []:
                item: dict[str, str | None] = {"item_name": None, "quantity": None, "lot_number": None, "expiry_date": None}
                for field in line.get("LineItemExpenseFields") or []:
                    kind, value = _field_type(field), _value(field)
                    if not value:
                        continue
                    if kind in {"ITEM", "DESCRIPTION", "PRODUCT_NAME"}:
                        item["item_name"] = value
                    elif kind in {"QUANTITY", "ITEM_QUANTITY"}:
                        item["quantity"] = value
                    elif kind in {"LOT", "LOT_NUMBER", "BATCH", "BATCH_NUMBER"}:
                        item["lot_number"] = value
                    elif kind in {"EXPIRY_DATE", "EXPIRATION_DATE", "BEST_BEFORE"}:
                        item["expiry_date"] = value
                line_items.append(item)
    return {
        "vendor": summary.get("VENDOR_NAME") or summary.get("VENDOR"),
        "invoice_date": summary.get("INVOICE_RECEIPT_DATE"),
        "items": line_items,
        "needs_review": True,
    }


class TextractExpenseProvider:
    def __init__(self, client: TextractClient):
        self.client = client

    def extract(self, document: bytes) -> dict[str, Any]:
        return normalize_textract_expense(self.client.analyze_expense(Document={"Bytes": document}))


def textract_provider_from_environment() -> TextractExpenseProvider:
    region = os.getenv("AWS_REGION")
    if not region:
        raise TextractNotConfigured("Set AWS_REGION and provide AWS credentials through the runtime role")
    try:
        import boto3
    except ImportError as error:
        raise TextractNotConfigured("Install boto3 to enable Textract document parsing") from error
    return TextractExpenseProvider(boto3.client("textract", region_name=region))