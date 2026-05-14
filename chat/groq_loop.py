import json
import os
from copy import deepcopy
from typing import Any

from groq import Groq

from chat.citation import enforce_citations
from chat.tools import TOOL_DEFINITIONS

# Groq on-demand tier hits TPM / per-request limits easily with long history + fat tool JSON.
MAX_HISTORY_MESSAGES = 14
MAX_MESSAGE_CHARS = 4000
MAX_TOOL_JSON_CHARS = 11_000

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


def _trim_history(history: list[dict] | None) -> list[dict]:
    if not history:
        return []
    rows = [
        {"role": h["role"], "content": h["content"]}
        for h in history
        if h.get("role") in {"user", "assistant"} and h.get("content")
    ]
    tail = rows[-MAX_HISTORY_MESSAGES:]
    out = []
    for h in tail:
        c = h["content"]
        if len(c) > MAX_MESSAGE_CHARS:
            c = c[: MAX_MESSAGE_CHARS - 20] + "\n...[truncated]"
        out.append({"role": h["role"], "content": c})
    return out


def _shrink_tool_result(data: Any) -> Any:
    """Keep tool totals but cap large lists so follow-up completions stay under token limits."""
    if not isinstance(data, dict):
        return data
    out = deepcopy(data)
    mm = out.get("mismatches")
    if isinstance(mm, list) and len(mm) > 35:
        out["mismatches"] = mm[:35]
        out["_mismatches_omitted"] = len(mm) - 35
    low = out.get("low_stock_skus")
    if isinstance(low, list) and len(low) > 60:
        out["low_stock_skus"] = low[:60]
        out["_low_stock_omitted"] = len(low) - 60
    rids = out.get("row_ids")
    if isinstance(rids, list) and len(rids) > 150:
        out["row_ids"] = rids[:150]
        out["_row_ids_omitted"] = len(rids) - 150
    return out


def _tool_json_for_model(result: Any) -> str:
    shrunk = _shrink_tool_result(result)
    raw = json.dumps(shrunk, default=str)
    if len(raw) <= MAX_TOOL_JSON_CHARS:
        return raw
    if isinstance(shrunk, dict) and isinstance(shrunk.get("mismatches"), list):
        mm_full = shrunk["mismatches"]
        total = shrunk.get("total_count", len(mm_full))
        for cap in (25, 15, 10, 5):
            s2 = dict(shrunk)
            s2["mismatches"] = mm_full[:cap]
            s2["_mismatches_shown"] = cap
            s2["_mismatches_omitted"] = max(0, int(total) - cap) if isinstance(total, (int, float)) else len(mm_full) - cap
            raw = json.dumps(s2, default=str)
            if len(raw) <= MAX_TOOL_JSON_CHARS:
                return raw
    return json.dumps(
        {
            "_error": "tool_payload_too_large",
            "_hint": "Try a narrower question (e.g. fewer days for weight mismatches).",
        },
        default=str,
    )


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
    for item in _trim_history(history):
        messages.append(item)
    user_block = f"merchant_id={merchant_id}\n\n{message}"
    if len(user_block) > MAX_MESSAGE_CHARS:
        user_block = user_block[: MAX_MESSAGE_CHARS - 20] + "\n...[truncated]"
    messages.append({"role": "user", "content": user_block})

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
                "content": _tool_json_for_model(result),
            })

    return "The chat loop reached its tool-call limit before producing an answer."
