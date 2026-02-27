"""
Mock Claude API server for E2E testing.

Mimics Anthropic's /v1/messages endpoint with canned responses.
Stage detection uses the same keyword matching as tests/conftest.py.

Usage:
    uvicorn mock_claude_server:app --host 0.0.0.0 --port 8080
"""
import json
import uuid

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

app = FastAPI(title="Mock Claude API")

# ---------------------------------------------------------------------------
# Canned responses (same data as tests/conftest.py fixtures)
# ---------------------------------------------------------------------------

PARSING_RESPONSE = {
    "sheets": [
        {
            "sheet_name": "Income Statement",
            "sheet_type": "income_statement",
            "layout": "time_across_columns",
            "periods": ["FY2022", "FY2023", "FY2024E"],
            "rows": [
                {
                    "row_index": 2, "label": "Revenue", "hierarchy_level": 1,
                    "values": {"FY2022": 100000, "FY2023": 115000, "FY2024E": 132000},
                    "is_formula": False, "is_subtotal": False,
                },
                {
                    "row_index": 4, "label": "Cost of Goods Sold", "hierarchy_level": 1,
                    "values": {"FY2022": 40000, "FY2023": 46000, "FY2024E": 53000},
                    "is_formula": False, "is_subtotal": False,
                },
                {
                    "row_index": 5, "label": "Gross Profit", "hierarchy_level": 1,
                    "values": {"FY2022": 60000, "FY2023": 69000, "FY2024E": 79000},
                    "is_formula": True, "is_subtotal": True,
                },
            ],
        },
        {
            "sheet_name": "Balance Sheet",
            "sheet_type": "balance_sheet",
            "layout": "time_across_columns",
            "periods": ["FY2022", "FY2023", "FY2024E"],
            "rows": [],
        },
    ]
}

TRIAGE_RESPONSE = [
    {
        "sheet_name": "Income Statement", "tier": 1,
        "decision": "PROCESS_HIGH", "confidence": 0.95,
        "reasoning": "Standard income statement with revenue, costs, and profitability",
    },
    {
        "sheet_name": "Balance Sheet", "tier": 1,
        "decision": "PROCESS_HIGH", "confidence": 0.95,
        "reasoning": "Standard balance sheet with assets, liabilities, and equity",
    },
    {
        "sheet_name": "Scratch - Working", "tier": 4,
        "decision": "SKIP", "confidence": 0.99,
        "reasoning": "Scratch sheet with notes, should be skipped",
    },
]

MAPPING_RESPONSE = [
    {"original_label": "Revenue", "canonical_name": "revenue",
     "confidence": 0.95, "reasoning": "Direct match for revenue"},
    {"original_label": "Cost of Goods Sold", "canonical_name": "cogs",
     "confidence": 0.95, "reasoning": "Standard abbreviation for Cost of Goods Sold"},
    {"original_label": "Gross Profit", "canonical_name": "gross_profit",
     "confidence": 0.95, "reasoning": "Standard gross profit calculation"},
]

VALIDATION_RESPONSE = [
    {"flag_index": 0, "assessment": "acceptable", "confidence": 0.8,
     "reasoning": "Variation within tolerance", "suggested_fix": None},
]


# ---------------------------------------------------------------------------
# Stage detection
# ---------------------------------------------------------------------------

def _detect_stage(messages: list) -> str:
    """Detect which pipeline stage is calling based on prompt content."""
    prompt_text = ""
    for msg in messages:
        content = msg.get("content", "")
        if isinstance(content, str):
            prompt_text += content
        elif isinstance(content, list):
            for item in content:
                if isinstance(item, dict) and item.get("type") == "text":
                    prompt_text += item.get("text", "")

    prompt_lower = prompt_text.lower()

    if "parsing" in prompt_lower or "extract all data" in prompt_lower:
        return "parsing"
    if "triage" in prompt_lower or "classify each sheet" in prompt_lower:
        return "triage"
    if "validation flags" in prompt_lower:
        return "validation"
    if "hierarchy context" in prompt_lower or "items to map" in prompt_lower:
        return "enhanced_mapping"
    if "mapping" in prompt_lower or "canonical" in prompt_lower:
        return "mapping"
    return "unknown"


_STAGE_RESPONSES = {
    "parsing": PARSING_RESPONSE,
    "triage": TRIAGE_RESPONSE,
    "mapping": MAPPING_RESPONSE,
    "validation": VALIDATION_RESPONSE,
    "enhanced_mapping": MAPPING_RESPONSE,
}


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.post("/v1/messages")
async def create_message(request: Request):
    body = await request.json()
    messages = body.get("messages", [])
    stage = _detect_stage(messages)
    response_data = _STAGE_RESPONSES.get(stage, {"error": "unknown stage"})
    response_text = json.dumps(response_data)

    print(f"[mock-claude] Stage: {stage} | Response: {len(response_text)} chars")

    return JSONResponse({
        "id": f"msg_{uuid.uuid4().hex[:24]}",
        "type": "message",
        "role": "assistant",
        "content": [{"type": "text", "text": response_text}],
        "model": body.get("model", "claude-sonnet-4-20250514"),
        "stop_reason": "end_turn",
        "stop_sequence": None,
        "usage": {"input_tokens": 500, "output_tokens": 300},
    })


@app.get("/health")
async def health():
    return {"status": "healthy", "service": "mock-claude"}
