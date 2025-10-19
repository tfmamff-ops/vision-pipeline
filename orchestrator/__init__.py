import azure.durable_functions as df

def orchestrator_function(context: df.DurableOrchestrationContext):
    """
    Input:
      {
        "container": "input",
        "blobName": "uploads/archivo.png",
        "expectedData": { "expiry": "...", "batch": "...", "order": "..." }
      }
    """
    ref_in = context.get_input()

    ref_focus = yield context.call_activity("enhance_focus", ref_in)
    ref_cb    = yield context.call_activity("adjust_contrast_brightness", ref_focus)
    ref_bw    = yield context.call_activity("to_grayscale", ref_cb)
    bc_out    = yield context.call_activity("analyze_barcode", ref_bw)
    ocr_out   = yield context.call_activity("run_ocr", ref_bw)

    payload = {
        "ocr": ocr_out,
        "barcode": bc_out,
        "expected": ref_in["expectedData"]
    }

    val_out = yield context.call_activity("validate_extracted_data", payload)

    return {
        "ocrResult": ocr_out["ocrResult"],
        "processedImageBlob": ocr_out["outputBlob"],
        "ocrOverlayBlob": ocr_out.get("overlayBlob"),
        "barcode": bc_out,
        "validation": val_out
    }

main = df.Orchestrator.create(orchestrator_function)
