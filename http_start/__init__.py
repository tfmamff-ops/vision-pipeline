import logging
import json
import azure.functions as func
import azure.durable_functions as df

async def main(req: func.HttpRequest, starter: str) -> func.HttpResponse:
    """
    ONLY accepts JSON:
    {
      "container": "input",
      "blobName": "uploads/archivo.png",
      "expectedData": {expiry: 'JUN/2028', batch: 'L 97907', order: 'M-AR-23-00219'}
    }
    """
    client = df.DurableOrchestrationClient(starter)
    try:
        payload = req.get_json()
        
        # Log the full received JSON
        logging.info("[http_start] JSON received (raw): %s", req.get_body().decode('utf-8'))
        logging.info("[http_start] Parsed JSON (payload): %s", json.dumps(payload, indent=2, ensure_ascii=False))
        
        container = payload.get("container")
        blob_name = payload.get("blobName")
        expected_data = payload.get("expectedData", {})
        
        logging.info("[http_start] container=%s, blobName=%s, expectedData=%s", container, blob_name, expected_data)
        
        if container != "input" or not blob_name or not expected_data:
            logging.warning("[http_start] Validation failed - returning 400")
            response = func.HttpResponse("Expected {container:'input', blobName:'...', expectedData:{...}}", status_code=400)
            logging.info("[http_start] Response status=%s, body=%s", response.status_code, response.get_body().decode('utf-8'))
            return response
    except Exception as e:
        logging.exception("[http_start] Error processing JSON - returning 400")
        response = func.HttpResponse(f"Invalid JSON: {e}", status_code=400)
        logging.info("[http_start] Response status=%s, body=%s", response.status_code, response.get_body().decode('utf-8'))
        return response

    instance_id = await client.start_new("orchestrator", None, {"container": container, "blobName": blob_name, "expectedData": expected_data})
    logging.info("[http_start] Orchestrator started with instance_id=%s", instance_id)
    
    response = client.create_check_status_response(req, instance_id)
    logging.info("[http_start] Response status=%s", response.status_code)

    # Read body once
    _body_bytes = response.get_body()
    _body_text = _body_bytes.decode('utf-8') if isinstance(_body_bytes, (bytes, bytearray)) else str(_body_bytes)
    logging.info("[http_start] Response body (raw): %s", _body_text)

    # Pretty-print JSON if valid
    try:
        _body_json = json.loads(_body_text)
        logging.info("[http_start] Response body (json): %s", json.dumps(_body_json, indent=2, ensure_ascii=False))
    except Exception as e:
        # Not JSON; keep raw only
        logging.debug("[http_start] Response body is not valid JSON: %s", e)
    return response
