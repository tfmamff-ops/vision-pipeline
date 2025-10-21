from datetime import timedelta
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

    output = {
        "ocrResult": ocr_out.get("ocrResult"),
        "processedImageBlob": ocr_out.get("outputBlob"),
        "ocrOverlayBlob": ocr_out.get("overlayBlob"),
        "barcode": bc_out,
        "validation": val_out,
    }

    run_doc = {
        "instanceId": context.instance_id,
        "createdTime": context.current_utc_datetime.isoformat(),  # determinista
        "input": ref_in,
        "output": output
    }

    # Persist run with retries
    # Some versions of azure.durable_functions expect positional args for RetryOptions
    # (first_retry_interval: timedelta, max_number_of_attempts: int)
    retry = df.RetryOptions(timedelta(seconds=10), 5)
    yield context.call_activity_with_retry("persist_run", retry, run_doc)

    return run_doc["output"]

main = df.Orchestrator.create(orchestrator_function)
