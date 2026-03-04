"""Stage 1: Guided Parsing - Extract structured data from Excel files."""
import asyncio
import io
import re
import time
from typing import Any, Dict, List, Optional

import anthropic
import openpyxl
from openpyxl.utils import get_column_letter

from src.core.exceptions import (
    ClaudeAPIError,
    ExtractionError,
    InvalidFileError,
    RateLimitError,
)
from src.core.logging import extraction_logger as logger, log_performance, log_exception
from src.extraction.base import ExtractionStage, PipelineContext
from src.extraction.claude_client import get_claude_client
from src.extraction.prompts import get_prompt
from src.extraction.utils import extract_json

# Pattern to detect subtotal/total rows from their label text
_SUBTOTAL_PATTERN = re.compile(
    r"\b(total|subtotal|net|gross)\b", re.IGNORECASE
)


class ParsingStage(ExtractionStage):
    """Stage 1: Parse Excel with Claude."""

    @property
    def name(self) -> str:
        return "parsing"

    @property
    def stage_number(self) -> int:
        return 1

    async def execute(self, context: PipelineContext) -> Dict[str, Any]:
        """
        Parse Excel file bytes using Claude vision.

        Uses manual retry logic with exponential backoff for rate limits.
        """
        max_retries = 3
        retry_count = 0
        backoff_base = 2

        logger.info("Stage 1: Parsing started")
        start_time = time.time()

        # Pre-process Excel to structured representation
        structured = self._excel_to_structured_repr(context.file_bytes)
        logger.debug(
            f"Structured extraction: {structured['sheet_count']} sheets, "
            f"{structured['total_rows']} rows"
        )

        # Convert to token-efficient markdown for Claude
        excel_text = self._structured_to_markdown(structured)
        logger.debug(f"Converted structured repr to markdown ({len(excel_text)} chars)")

        while retry_count < max_retries:
            try:
                logger.debug(f"Calling Claude API (attempt {retry_count + 1}/{max_retries})")

                prompt_text = get_prompt("parsing").content
                full_prompt = (
                    f"Below is the content of an Excel file, with each sheet shown separately.\n\n"
                    f"{excel_text}\n\n"
                    f"{prompt_text}"
                )

                response = get_claude_client().messages.create(
                    model="claude-sonnet-4-20250514",
                    max_tokens=8192,
                    messages=[{
                        "role": "user",
                        "content": full_prompt,
                    }],
                )

                content = response.content[0].text  # type: ignore[union-attr]
                parsed = extract_json(content)

                tokens = response.usage.input_tokens + response.usage.output_tokens
                duration = time.time() - start_time

                log_performance(
                    logger,
                    "stage_1_parsing",
                    duration,
                    {"tokens": tokens, "sheets": len(parsed.get("sheets", []) if isinstance(parsed, dict) else [])},  # type: ignore[union-attr]
                )

                sheets_count = len(parsed.get("sheets", []) if isinstance(parsed, dict) else [])  # type: ignore[union-attr]
                logger.info(f"Stage 1: Parsing completed - {sheets_count} sheets found")

                return {
                    "parsed": parsed,
                    "tokens": tokens,
                    "lineage_metadata": {
                        "sheets_count": sheets_count,
                        "file_size_bytes": len(context.file_bytes),
                    },
                    "structured": structured,
                }

            except anthropic.RateLimitError:
                retry_count += 1
                wait_time = backoff_base ** retry_count

                logger.warning(
                    f"Stage 1: Rate limit hit (attempt {retry_count}/{max_retries}), "
                    f"waiting {wait_time}s before retry"
                )

                if retry_count >= max_retries:
                    error = RateLimitError(
                        "Rate limit exceeded after retries",
                        stage="parsing",
                        retry_after=wait_time,
                    )
                    log_exception(logger, error, {"retry_count": retry_count})
                    raise error

                await asyncio.sleep(wait_time)

            except anthropic.APIStatusError as e:
                # Retry on transient server errors (500, 502, 503, 529)
                if e.status_code in (500, 502, 503, 529):
                    retry_count += 1
                    if retry_count >= max_retries:
                        raise ClaudeAPIError(
                            str(e), stage="parsing",
                            retry_count=retry_count, status_code=e.status_code,
                        )
                    wait_time = backoff_base ** retry_count
                    logger.warning(
                        f"Stage 1: Transient API error (status {e.status_code}), "
                        f"retrying in {wait_time}s"
                    )
                    await asyncio.sleep(wait_time)
                else:
                    # Non-retryable API error (400, 401, 403, etc.)
                    raise ClaudeAPIError(
                        str(e), stage="parsing",
                        retry_count=retry_count, status_code=e.status_code,
                    )

            except anthropic.APIConnectionError:
                retry_count += 1
                if retry_count >= max_retries:
                    raise ClaudeAPIError(
                        "Connection error after retries", stage="parsing",
                        retry_count=retry_count,
                    )
                wait_time = backoff_base ** retry_count
                logger.warning(
                    f"Stage 1: Connection error, retrying in {wait_time}s"
                )
                await asyncio.sleep(wait_time)

            except anthropic.APIError as e:
                logger.error(f"Stage 1: Claude API error - {str(e)}")
                error = ClaudeAPIError(  # type: ignore[assignment]
                    str(e),
                    stage="parsing",
                    retry_count=retry_count,
                    status_code=getattr(e, "status_code", None),
                )
                log_exception(logger, error)
                raise error

            except ExtractionError:
                raise

            except Exception as e:
                logger.error(f"Stage 1: Unexpected error - {str(e)}")
                error = ExtractionError(f"Parsing failed: {str(e)}", stage="parsing")  # type: ignore[assignment]
                log_exception(logger, error)
                raise error

        raise ClaudeAPIError("Max retries exceeded", stage="parsing", retry_count=max_retries)

    # ------------------------------------------------------------------
    # Structured Excel extraction
    # ------------------------------------------------------------------

    @staticmethod
    def _excel_to_structured_repr(file_bytes: bytes) -> Dict[str, Any]:
        """
        Extract a rich structured representation from an Excel file.

        Opens the workbook **twice**:
          1. ``data_only=False`` (default) to capture formulas and formatting.
          2. ``data_only=True`` to capture computed/cached values.

        The two passes are merged so every cell carries both its computed
        *value* and its *formula* string (if any).

        Returns a dict with keys: sheets, named_ranges, sheet_count, total_rows.
        Raises InvalidFileError for password-protected or corrupted files.
        """
        try:
            # Pass 1 – formulas + formatting (read_only=False required for styles)
            wb_formulas = openpyxl.load_workbook(
                io.BytesIO(file_bytes), data_only=False, read_only=False
            )
        except Exception as e:
            raise InvalidFileError(
                f"Cannot open Excel file: {e}",
                file_type="xlsx",
            )

        try:
            # Pass 2 – computed/cached values
            wb_values = openpyxl.load_workbook(
                io.BytesIO(file_bytes), data_only=True, read_only=True
            )
        except Exception:
            # If the second pass fails, close the first workbook and raise
            wb_formulas.close()
            raise InvalidFileError(
                "Cannot open Excel file for value extraction",
                file_type="xlsx",
            )

        try:
            sheets: List[Dict[str, Any]] = []
            total_rows = 0

            for sheet_name in wb_formulas.sheetnames:
                ws_fmt = wb_formulas[sheet_name]
                ws_val = wb_values[sheet_name]

                # Build a lookup of computed values by (row, col) from the
                # values-only workbook
                value_lookup: Dict[tuple, Any] = {}
                for row in ws_val.iter_rows():
                    for cell in row:
                        if cell.value is not None:
                            value_lookup[(cell.row, cell.column)] = cell.value

                # Detect merged cell regions
                merged_regions = [
                    str(m) for m in ws_fmt.merged_cells.ranges
                ]

                is_hidden = ws_fmt.sheet_state != "visible"

                row_dicts: List[Dict[str, Any]] = []
                for row_cells in ws_fmt.iter_rows():
                    cells_out: List[Dict[str, Any]] = []
                    row_empty = True

                    for cell in row_cells:
                        raw = cell.value
                        computed = value_lookup.get(
                            (cell.row, cell.column), raw
                        )

                        # Determine formula
                        formula: Optional[str] = None
                        if isinstance(raw, str) and raw.startswith("="):
                            formula = raw
                            # If there is a cached computed value use it;
                            # otherwise fall back to None (formula not evaluated)
                            value = computed if computed != raw else None
                        else:
                            value = raw

                        # Skip truly empty cells
                        if value is None and formula is None:
                            continue

                        row_empty = False

                        # Formatting clues
                        font = cell.font
                        alignment = cell.alignment

                        is_bold = bool(font and font.bold)
                        indent_level = int(
                            alignment.indent if alignment and alignment.indent else 0
                        )
                        number_format = cell.number_format or "General"

                        col_letter = get_column_letter(cell.column)
                        ref = f"{col_letter}{cell.row}"

                        cell_dict: Dict[str, Any] = {
                            "ref": ref,
                            "value": value,
                            "formula": formula,
                            "is_bold": is_bold,
                            "indent_level": indent_level,
                            "number_format": number_format,
                        }

                        # Label-based subtotal detection
                        if isinstance(value, str) and _SUBTOTAL_PATTERN.search(value):
                            cell_dict["is_subtotal"] = True

                        cells_out.append(cell_dict)

                    if row_empty or not cells_out:
                        continue  # skip entirely empty rows

                    row_index = row_cells[0].row
                    row_dict: Dict[str, Any] = {
                        "row_index": row_index,
                        "cells": cells_out,
                    }

                    # Mark row-level subtotal if the first cell is a subtotal
                    if cells_out and cells_out[0].get("is_subtotal"):
                        row_dict["is_subtotal"] = True

                    row_dicts.append(row_dict)

                total_rows += len(row_dicts)

                sheets.append({
                    "sheet_name": sheet_name,
                    "is_hidden": is_hidden,
                    "merged_regions": merged_regions,
                    "rows": row_dicts,
                })

            # Collect named ranges (openpyxl 3.1+ uses a dict-like API)
            named_ranges: Dict[str, str] = {}
            dn = wb_formulas.defined_names
            # Support both openpyxl < 3.1 (.definedName) and >= 3.1 (.values())
            defn_iter = (
                getattr(dn, "definedName", None) or dn.values()
            )
            for defn in defn_iter:
                try:
                    destinations = list(defn.destinations)
                    if destinations:
                        ws_title, coord = destinations[0]
                        named_ranges[defn.name] = f"{ws_title}!{coord}"
                except Exception:
                    # Some defined names are malformed or refer to external
                    # sheets; skip gracefully.
                    pass

            return {
                "sheets": sheets,
                "named_ranges": named_ranges,
                "sheet_count": len(sheets),
                "total_rows": total_rows,
            }

        finally:
            wb_formulas.close()
            wb_values.close()

    # ------------------------------------------------------------------
    # Markdown serialisation for Claude
    # ------------------------------------------------------------------

    @staticmethod
    def _structured_to_markdown(structured: Dict[str, Any]) -> str:
        """
        Convert the structured dict to a token-efficient markdown table
        suitable for sending to Claude.

        Each sheet becomes a ``## Sheet: <name>`` section.  Merged regions
        are listed, then a pipe-delimited table with columns:

            Row | Ref | <dynamic value columns...> | Formula | Bold | Indent

        The first non-empty cell in each row is treated as the label; all
        subsequent cells become value columns.
        """
        parts: List[str] = []

        for sheet in structured.get("sheets", []):
            header = f"## Sheet: {sheet['sheet_name']}"
            if sheet.get("is_hidden"):
                header += " (hidden)"
            parts.append(header)

            if sheet.get("merged_regions"):
                parts.append(
                    "Merged: " + ", ".join(sheet["merged_regions"])
                )

            rows = sheet.get("rows", [])
            if not rows:
                parts.append("_(empty sheet)_")
                parts.append("")
                continue

            # Determine the maximum number of cells across all rows so we
            # can create uniform columns.
            max_cells = max(len(r["cells"]) for r in rows)

            # Build a simple header row: Row | Cell1 | Cell2 | ... | Formula | Bold | Indent
            col_headers = ["Row"]
            for i in range(max_cells):
                col_headers.append(f"C{i + 1}")
            col_headers.extend(["Formula", "Bold", "Indent"])

            parts.append("| " + " | ".join(col_headers) + " |")
            parts.append("|" + "|".join(["---"] * len(col_headers)) + "|")

            for row in rows:
                cells = row["cells"]
                row_idx = str(row["row_index"])

                # Cell values (pad to max_cells)
                cell_values: List[str] = []
                formulas: List[str] = []
                bold_flags: List[str] = []
                indent_vals: List[str] = []

                for cell in cells:
                    val = cell.get("value")
                    if val is None:
                        cell_values.append("")
                    elif isinstance(val, float):
                        # Use number_format hint for display
                        nf = cell.get("number_format", "General")
                        if "%" in nf:
                            cell_values.append(f"{val:.1%}")
                        elif "0.0" in nf or "#,##0.0" in nf:
                            cell_values.append(f"{val:,.1f}")
                        elif "#,##0" in nf or "," in nf:
                            cell_values.append(f"{val:,.0f}")
                        else:
                            cell_values.append(str(val))
                    else:
                        cell_values.append(str(val))

                    formulas.append(cell.get("formula") or "")
                    bold_flags.append("Y" if cell.get("is_bold") else "N")
                    indent_vals.append(str(cell.get("indent_level", 0)))

                # Pad cell_values to max_cells
                while len(cell_values) < max_cells:
                    cell_values.append("")

                # Summarise formatting: take first cell's bold/indent as
                # the representative for the row.
                formula_str = formulas[0] if formulas else ""
                bold_str = bold_flags[0] if bold_flags else "N"
                indent_str = indent_vals[0] if indent_vals else "0"

                row_parts = [row_idx] + cell_values + [
                    formula_str or "\u2014",
                    bold_str,
                    indent_str,
                ]
                parts.append("| " + " | ".join(row_parts) + " |")

            parts.append("")  # blank line between sheets

        # Named ranges summary
        named = structured.get("named_ranges", {})
        if named:
            parts.append("## Named Ranges")
            for name, target in named.items():
                parts.append(f"- **{name}**: `{target}`")
            parts.append("")

        return "\n".join(parts)


# Self-register at import time
from src.extraction.registry import registry  # noqa: E402
registry.register(ParsingStage())
