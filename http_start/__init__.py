import logging
import json
import azure.functions as func
import azure.durable_functions as df

async def main(req: func.HttpRequest, starter: str) -> func.HttpResponse:
    """
    SOLO acepta JSON:
    {
      "container": "input",
      "blobName": "uploads/archivo.png",
      "expectedData": {expiry: 'JUN/2028', batch: 'L 97907', order: 'M-AR-23-00219'}
    }
    """
    client = df.DurableOrchestrationClient(starter)
    try:
        payload = req.get_json()
        
        # Loguear el JSON completo recibido
        logging.info("[http_start] JSON recibido (raw): %s", req.get_body().decode('utf-8'))
        logging.info("[http_start] JSON parseado (payload): %s", json.dumps(payload, indent=2, ensure_ascii=False))
        
        container = payload.get("container")
        blob_name = payload.get("blobName")
        expected_data = payload.get("expectedData", {})
        
        logging.info("[http_start] container=%s, blobName=%s, expectedData=%s", container, blob_name, expected_data)
        
        if container != "input" or not blob_name or not expected_data:
            return func.HttpResponse("Esperado {container:'input', blobName:'...', expectedData:{...}}", status_code=400)
    except Exception as e:
        return func.HttpResponse(f"JSON inválido: {e}", status_code=400)

    instance_id = await client.start_new("orchestrator", None, {"container": container, "blobName": blob_name, "expectedData": expected_data})
    return client.create_check_status_response(req, instance_id)
