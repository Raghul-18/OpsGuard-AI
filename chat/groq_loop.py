import json
import os
from typing import Any

from groq import Groq

from chat.citation import enforce_citations
from chat.tools import TOOL_DEFINITIONS

SYSTEM_PROMPT = """
You are OpsGuard AI, an ops assistant for an Indian D2C brand.
You can query Shopify orders, Google Sheets SKU master rows, and Shiprocket shipments via tools.

CITATION RULE: Every number you state must be immediately followed by a cite tag in the format <cite:row_id>.
Use numeric format only, such as INR 4,700 <cite:row_id> or 23% <cite:row_id>.
If you do not have a cited source for a number, say you do not have a cited source. Never guess.

WRITE RULE: You may only write data using mark_action_taken.
Never call mark_action_taken unless the user explicitly asks to mark a specific reconciliation item as actioned and provides its ID.
SCOPE RULE: Only answer questions about this merchant's data.
"""


def _tool_functions() -> dict[str, Any]:
    from chat.tools import (
        calculate_pnl,
        find_weight_mismatches,
        get_inventory_status,
        get_rto_rate,
        get_top_skus,
        mark_action_taken,
    )

    return {
        "find_weight_mismatches": find_weight_mismatches,
        "get_rto_rate": get_rto_rate,
        "calculate_pnl": calculate_pnl,
        "get_inventory_status": get_inventory_status,
        "get_top_skus": get_top_skus,
        "mark_action_taken": mark_action_taken,
    }


def run_chat_loop(merchant_id: str, message: str, history: list[dict] | None = None) -> str:
    if not os.environ.get("GROQ_API_KEY"):
        return "Groq is not configured. Set GROQ_API_KEY to enable the live chat model."

    client = Groq(api_key=os.environ["GROQ_API_KEY"])
    messages: list[dict] = [{"role": "system", "content": SYSTEM_PROMPT}]
    for item in history or []:
        if item.get("role") in {"user", "assistant"} and item.get("content"):
            messages.append({"role": item["role"], "content": item["content"]})
    messages.append({"role": "user", "content": f"merchant_id={merchant_id}\n\n{message}"})

    model = os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile")
    functions = _tool_functions()
    write_allowed = "mark" in message.lower() and ("action" in message.lower() or "resolved" in message.lower())
    for _ in range(6):
        completion = client.chat.completions.create(
            model=model,
            messages=messages,
            tools=TOOL_DEFINITIONS,
            tool_choice="auto",
            temperature=0.1,
        )
        assistant_message = completion.choices[0].message
        messages.append(assistant_message.model_dump(exclude_none=True))

        if not assistant_message.tool_calls:
            return enforce_citations(assistant_message.content or "")

        for tool_call in assistant_message.tool_calls:
            name = tool_call.function.name
            args = json.loads(tool_call.function.arguments or "{}")
            if name == "mark_action_taken" and not write_allowed:
                result = {
                    "error": "mark_action_taken was blocked because the user did not explicitly request a write action.",
                    "allowed_tools": [
                        "find_weight_mismatches",
                        "get_rto_rate",
                        "calculate_pnl",
                        "get_inventory_status",
                        "get_top_skus",
                    ],
                }
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "name": name,
                    "content": json.dumps(result, default=str),
                })
                continue
            if name != "mark_action_taken":
                args["merchant_id"] = merchant_id
            result = functions[name](**args)
            messages.append({
                "role": "tool",
                "tool_call_id": tool_call.id,
                "name": name,
                "content": json.dumps(result, default=str),
            })

    return "The chat loop reached its tool-call limit before producing an answer."
