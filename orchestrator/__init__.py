import azure.durable_functions as df

def orchestrator_function(context: df.DurableOrchestrationContext):
    """
    Accepts JSON with blob reference, expected data, and requester context:
    {
        "container": "input",
        "blobName": "uploads/archivo.png",
        "expectedData": {
            "prodCode": "EUTEBROL-A7E0",
            "prodDesc": "EUTEBROL DUO",
            "lot": "S 101144",
            "expDate": "V JUL/2027",
            "packDate": "E JUL/2025"
        },
        "requestContext": {
            "user": {
                "id": "auth0|9a0812ffb13",
                "name": "Bob Operator",
                "email": "operator.qa@lab.com",
                "role": "qa_operator"
            },
            "client": {
                "appVersion": "web-1.0.0",
                "ip": "127.0.0.1",
                "userAgent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
            }
        }
    }
    """

    ref_in = context.get_input()

    ref_focus = yield context.call_activity("enhance_focus", ref_in)
    context.set_custom_status({"stage": "enhance_focus_done"})
    ref_cb    = yield context.call_activity("adjust_contrast_brightness", ref_focus)
    context.set_custom_status({"stage": "adjust_contrast_brightness_done"})
    ref_bw    = yield context.call_activity("to_grayscale", ref_cb)
    context.set_custom_status({"stage": "to_grayscale_done"})
    bc_out    = yield context.call_activity("analyze_barcode", ref_bw)
    context.set_custom_status({"stage": "analyze_barcode_done"})
    ocr_out   = yield context.call_activity("run_ocr", ref_bw)
    context.set_custom_status({"stage": "run_ocr_done"})

    payload = {
        "ocr": ocr_out,
        "barcode": bc_out,
        "expectedData": ref_in["expectedData"]
    }

    val_out = yield context.call_activity("validate_extracted_data", payload)
    context.set_custom_status({"stage": "validation_done"})

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
    # RetryOptions in some versions: (first_retry_interval: timedelta, max_number_of_attempts: int)
    # In other versions: (first_retry_interval: timedelta, max_retry_interval: timedelta)
    # Using direct instantiation without retry options to avoid version conflicts
    # Will rely on default retry behavior of the activity
    context.set_custom_status({"stage": "persisting_run"})
    yield context.call_activity("persist_run", run_doc)
    context.set_custom_status({"stage": "completed"})

    return run_doc["output"]

main = df.Orchestrator.create(orchestrator_function)
