import json
import logging

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

def _contains_robust(hay_full: str, hay_full_ns: str, needle: str) -> bool:
    """
    True if needle appears in OCR either as-is (case-insensitive) or
    when both sides are normalized (uppercased, no spaces).
    """
    if not needle:
        return False
    ndl = _safe_upper(needle).strip()
    if ndl and ndl in hay_full:
        return True
    found = _norm_no_spaces(ndl) in hay_full_ns
    logging.debug("[validate_extracted_data] Search '%s' in OCR: %s", needle, found)
    return found

def main(payload: dict) -> dict:
    """
    Validates OCR and barcode results against expected data.
    
    Expected payload structure from orchestrator:
    {
      "ocr": {...},
      "barcode": {"barcodeData": {...}},
      "expected": {"order": "...", "batch": "...", "expiry": "..."}
    }
    """
    logging.info("[validate_extracted_data] Starting validation")
    logging.info("[validate_extracted_data] Payload (json): %s", json.dumps(payload, indent=2, ensure_ascii=False))

    # Extract data from payload (compatible with orchestrator output)
    ocr_result = payload.get("ocr") or {}
    barcode = payload.get("barcode") or {}
    expected_data = payload.get("expected") or {}
    
    # Extract OCR text surfaces
    ocr_text = _extract_ocr_text(ocr_result)
    full, full_ns = ocr_text["full"], ocr_text["full_ns"]
    
    # Expected fields
    exp_order = expected_data.get("order", "")
    exp_batch = expected_data.get("batch", "")
    exp_expiry = expected_data.get("expiry", "")
    
    logging.info("[validate_extracted_data] Expected: order='%s', batch='%s', expiry='%s'", 
                 exp_order, exp_batch, exp_expiry)
    
    # Search expected values in OCR text
    order_ok = _contains_robust(full, full_ns, exp_order)
    batch_ok = _contains_robust(full, full_ns, exp_batch)
    expiry_ok = _contains_robust(full, full_ns, exp_expiry)
    
    logging.info("[validate_extracted_data] OCR validation: order=%s, batch=%s, expiry=%s", 
                 order_ok, batch_ok, expiry_ok)
    
    # Barcode validation
    # Handle both wrapped and unwrapped barcode data
    bc_data = barcode.get("barcodeData") if isinstance(barcode.get("barcodeData"), dict) else barcode
    
    barcode_detected_ok = bc_data.get("barcodeDetected") is True
    barcode_legible_ok = bc_data.get("barcodeLegible") is True
    decoded_value = str(bc_data.get("decodedValue") or "").strip()
    
    logging.info("[validate_extracted_data] Barcode: detected=%s, legible=%s, value='%s'", 
                 barcode_detected_ok, barcode_legible_ok, decoded_value)
    
    # barcodeOK is true only if detected AND legible AND has value
    barcode_ok = barcode_detected_ok and barcode_legible_ok and (decoded_value != "")
    
    # validationSummary is true only if ALL validations pass
    validation_summary = all([order_ok, batch_ok, expiry_ok, barcode_ok])
    
    result = {
        "validation": {
            "orderOK": order_ok,
            "batchOK": batch_ok,
            "expiryOK": expiry_ok,
            "barcodeDetectedOK": barcode_detected_ok,
            "barcodeLegibleOK": barcode_legible_ok,
            "barcodeOK": barcode_ok,
            "validationSummary": validation_summary
        }
    }
    
    logging.info("[validate_extracted_data] Validation complete: summary=%s", validation_summary)
    logging.debug("[validate_extracted_data] Full result: %s", result)
    
    return result
