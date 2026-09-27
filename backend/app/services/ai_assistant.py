import json

from app.services.ai_provider import AIProviderError, complete


def summarize_invoice_report(report: dict) -> str | None:
    return complete(
        "Summarize the supplied invoice metrics for a warehouse manager. Use only the provided figures, distinguish counts from amounts, and do not infer causes or financial advice.",
        json.dumps(report, sort_keys=True),
        max_tokens=260,
    )


def answer_warehouse_question(question: str, context: dict) -> str | None:
    return complete(
        "You are a warehouse operations assistant. Answer only from the supplied current warehouse data. Do not invent stock, quantities, dates, or orders. Never claim to have changed inventory or created an order. If the data is insufficient, say so.",
        json.dumps({"question": question[:500], "warehouse_data": context}, sort_keys=True),
        max_tokens=300,
    )


def suggest_inventory_actions(results: list[dict]) -> list[dict]:
    if not results:
        return []
    allowed_products = {item["product_id"]: item for item in results}
    context = [{
        "product_id": item["product_id"],
        "product_name": item["product_name"],
        "current_stock": item["current_stock"],
        "recommended_reorder": item["recommended_reorder"],
        "stockout_risk": item["stockout_risk"],
        "waste_risk": item["waste_risk"],
        "estimated_days_remaining": item["estimated_days_remaining"],
    } for item in results[:20]]
    response = complete(
        'Return JSON only: {"suggestions":[{"product_id":1,"action":"ORDER_REVIEW|INVENTORY_CHECK","priority":"HIGH|MEDIUM|LOW"}]}. Suggest at most three actions. Use only supplied product IDs. Choose ORDER_REVIEW only when recommended_reorder is positive; choose INVENTORY_CHECK only for a stockout or waste risk. Do not invent quantities and do not create or approve orders.',
        json.dumps(context, sort_keys=True),
        max_tokens=350,
    )
    if response is None:
        return []

    response = response.strip()
    if not response:
        return []
    if response.startswith("```") and response.endswith("```"):
        response = response[3:-3].strip()
        if response.startswith("json"):
            response = response[4:].strip()

    try:
        payload = json.loads(response)
    except json.JSONDecodeError:
        object_start = response.find("{")
        if object_start == -1:
            return []
        try:
            payload, _ = json.JSONDecoder().raw_decode(response[object_start:])
        except json.JSONDecodeError:
            return []

    suggestions = []
    for item in payload.get("suggestions", []) if isinstance(payload, dict) else []:
        if not isinstance(item, dict):
            continue
        product_id = item.get("product_id")
        action = item.get("action")
        priority = item.get("priority")
        if not isinstance(product_id, int) or product_id not in allowed_products:
            continue
        if action not in {"ORDER_REVIEW", "INVENTORY_CHECK"} or priority not in {"HIGH", "MEDIUM", "LOW"}:
            continue
        product = allowed_products[product_id]
        if action == "ORDER_REVIEW" and product["recommended_reorder"] <= 0:
            continue
        if action == "INVENTORY_CHECK" and product["stockout_risk"] == "LOW" and product["waste_risk"] == "LOW":
            continue
        suggestions.append({
            "product_id": product_id,
            "action": action,
            "priority": priority,
        })
        if len(suggestions) == 3:
            break
    return suggestions