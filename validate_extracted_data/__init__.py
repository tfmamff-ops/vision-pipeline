import json
import logging
import os

# This is used to skip validation for specific fields
_SENTINEL_SKIP_VALIDATION = str(os.getenv("SENTINEL_SKIP_VALIDATION", "N/A"))

def _safe_upper(s: str) -> str:
    return (s or "").upper()

def _norm_no_spaces(s: str) -> str:
    # Upper + remove all whitespace for robust matching against OCR variations
    return "".join(_safe_upper(s).split())

def _extract_ocr_text(ocr_result: dict) -> dict:
    """
    Flattens OCR result into two strings:
    - full: all line texts joined with spaces (UPPERCASED)
    - full_ns: same but with all spaces removed (UPPERCASED)
    """
    lines = []
    try:
        blocks = ocr_result.get("readResult", {}).get("blocks", [])
        for blk in blocks:
            for ln in blk.get("lines", []):
                t = ln.get("text", "")
                if t:
                    lines.append(t)
    except Exception as e:
        # Fallback: if OCR structure is unexpected, log and continue with empty lines
        logging.warning("[validate_extracted_data] Error extracting OCR text: %s", e)

    full = " ".join(lines).upper().strip()
    full_ns = _norm_no_spaces(full)

    logging.info("[validate_extracted_data] Extracted OCR text: '%s'", full)
    return {"full": full, "full_ns": full_ns}

def _is_sentinel(value: str | None) -> bool:
    """
    True if the provided expected value means 'skip validation'.
    """
    if not value:
        return False
    return value.strip().upper() == _SENTINEL_SKIP_VALIDATION.upper()

def _contains_robust(hay_full: str, hay_full_ns: str, needle: str) -> bool:
    """
    True if needle appears in OCR with the following rules:
    1. If needle is _SENTINEL_SKIP_VALIDATION, always return True (skip validation)
    2. Try to find needle as-is (case-insensitive) or normalized (no spaces)
    3. If not found and needle contains spaces, split by spaces and search each component
       - All components must be found for validation to pass
    """
    if not needle:
        return False

    # Rule 1: Sentinel always validates as True
    if _is_sentinel(needle):
        logging.info(
            "[validate_extracted_data] Sentinel '%s' detected for '%s' - validation bypassed (True)",
            _SENTINEL_SKIP_VALIDATION,
            needle,
        )
        return True

    ndl = _safe_upper(needle).strip()

    # Rule 2: Try exact match (with and without spaces)
    if ndl and ndl in hay_full:
        logging.debug("[validate_extracted_data] Exact match found for '%s'", needle)
        return True

    if _norm_no_spaces(ndl) in hay_full_ns:
        logging.debug("[validate_extracted_data] Normalized match found for '%s'", needle)
        return True

    # Rule 3: If contains spaces, try finding all components individually
    if " " in ndl:
        components = [c for c in ndl.split() if c]  # Split by spaces, filter empty
        logging.debug(
            "[validate_extracted_data] Searching components %s for '%s'",
            components,
            needle,
        )

        all_found = True
        for comp in components:
            comp_found = comp in hay_full or _norm_no_spaces(comp) in hay_full_ns
            if not comp_found:
                logging.debug(
                    "[validate_extracted_data] Component '%s' NOT found", comp
                )
                all_found = False
                break
            else:
                logging.debug(
                    "[validate_extracted_data] Component '%s' found", comp
                )

        if all_found:
            logging.info(
                "[validate_extracted_data] All components found for '%s'", needle
            )
            return True

    logging.debug("[validate_extracted_data] Search '%s' in OCR: False", needle)
    return False

def main(payload: dict) -> dict:
    """
    Validates OCR and barcode results against expected data.

    Expected payload structure from orchestrator:
    {
      "ocr": {...},
      "barcode": {"barcodeData": {...}},
      "expectedData": {"prodCode": "...", "prodDesc": "...", "lot": "...", "expDate": "...", "packDate": "..."}
    }
    """
    logging.info("[validate_extracted_data] Starting validation")
    logging.info(
        "[validate_extracted_data] Payload (json): %s",
        json.dumps(payload, indent=2, ensure_ascii=False),
    )

    # Extract data from payload (compatible with orchestrator output)
    ocr_container = payload.get("ocr") or {}
    ocr_result = ocr_container.get("ocrResult") or {}
    barcode = payload.get("barcode") or {}
    expected_data = payload.get("expectedData") or {}

    # Extract OCR text surfaces
    ocr_text = _extract_ocr_text(ocr_result)
    full, full_ns = ocr_text["full"], ocr_text["full_ns"]

    # Expected fields
    expected_lot = expected_data.get("lot", "")
    expected_exp_date = expected_data.get("expDate", "")
    expected_pack_date = expected_data.get("packDate", "")

    logging.info(
        "[validate_extracted_data] ExpectedData: lot='%s', expDate='%s', packDate='%s'",
        expected_lot,
        expected_exp_date,
        expected_pack_date,
    )

    # Search expected values in OCR text
    lot_ok = _contains_robust(full, full_ns, expected_lot)
    exp_date_ok = _contains_robust(full, full_ns, expected_exp_date)
    pack_date_ok = _contains_robust(full, full_ns, expected_pack_date)

    logging.info(
        "[validate_extracted_data] OCR validation: lot=%s, expDate=%s, packDate=%s",
        lot_ok,
        exp_date_ok,
        pack_date_ok,
    )

    # Barcode validation
    # Handle both wrapped and unwrapped barcode data
    bc_data = (
        barcode.get("barcodeData")
        if isinstance(barcode.get("barcodeData"), dict)
        else barcode
    )

    barcode_detected_ok = bc_data.get("barcodeDetected") is True
    barcode_legible_ok = bc_data.get("barcodeLegible") is True
    decoded_value = str(bc_data.get("decodedValue") or "").strip()

    logging.info(
        "[validate_extracted_data] Barcode: detected=%s, legible=%s, value='%s'",
        barcode_detected_ok,
        barcode_legible_ok,
        decoded_value,
    )

    # barcodeOK is true only if detected AND legible AND has value
    barcode_ok = (
        barcode_detected_ok and barcode_legible_ok and (decoded_value != "")
    )

    # validationSummary is true only if ALL validations pass
    validation_summary = all(
        [lot_ok, exp_date_ok, pack_date_ok, barcode_ok]
    )

    result = {
        "lotOk": lot_ok,
        "expDateOk": exp_date_ok,
        "packDateOk": pack_date_ok,
        "barcodeDetectedOk": barcode_detected_ok,
        "barcodeLegibleOk": barcode_legible_ok,
        "barcodeOk": barcode_ok,
        "validationSummary": validation_summary,
    }

    logging.info(
        "[validate_extracted_data] Validation complete: summary=%s",
        validation_summary,
    )
    logging.debug("[validate_extracted_data] Full result: %s", result)

    return result
