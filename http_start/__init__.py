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
    logging.info("[http_start] Response body (raw): %s", response.get_body().decode('utf-8'))
    logging.info("[http_start] Parsed JSON (Response body): %s", json.dumps(response.get_body().decode('utf-8'), indent=2, ensure_ascii=False))
    return response
