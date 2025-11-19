import json
import logging

import azure.durable_functions as df
import azure.functions as func

logger = logging.getLogger(__name__)


async def main(req: func.HttpRequest, starter: str) -> func.HttpResponse:
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

    client = df.DurableOrchestrationClient(starter)
    try:
        payload = req.get_json()

        # Log the full received JSON
        logger.info("JSON received (raw): %s", req.get_body().decode("utf-8"))
        logger.info(
            "Parsed JSON (payload): %s",
            json.dumps(payload, indent=2, ensure_ascii=False),
        )

        container = payload.get("container")
        blob_name = payload.get("blobName")
        expected_data = payload.get("expectedData", {})
        request_context = payload.get("requestContext")

        logger.info(
            "container=%s, blobName=%s, expectedData=%s, hasRequestContext=%s",
            container,
            blob_name,
            bool(expected_data),
            bool(request_context),
        )

        # Basic validations
        missing = []
        if container != "input":
            missing.append("container=='input'")
        if not blob_name:
            missing.append("blobName")
        if not isinstance(expected_data, dict) or not expected_data:
            missing.append("expectedData")

        # Identity must be present because DB enforces NOT NULL
        user_id = None
        if isinstance(request_context, dict):
            user = request_context.get("user") or {}
            user_id = user.get("id")
        if not user_id:
            missing.append("requestContext.user.id")

        if missing:
            msg = {
                "error": "Bad Request",
                "missing": missing,
                "hint": "Expected container='input', blobName, expectedData{prodCode, prodDesc, lot, expDate, packDate}, requestContext.user.id",
            }
            logger.warning("Validation failed: %s", msg)
            response = func.HttpResponse(
                json.dumps(msg, ensure_ascii=False),
                status_code=400,
                mimetype="application/json",
            )
            logger.info(
                "Response status=%s, body=%s",
                response.status_code,
                response.get_body().decode("utf-8"),
            )
            return response
    except Exception as e:
        logger.exception("Error processing JSON - returning 400")
        response = func.HttpResponse(
            json.dumps({"error": "Invalid JSON", "detail": str(e)}, ensure_ascii=False),
            status_code=400,
            mimetype="application/json",
        )
        logger.info(
            "Response status=%s, body=%s",
            response.status_code,
            response.get_body().decode("utf-8"),
        )
        return response

    # Forward full context to the orchestrator (keeps strict identity requirements)
    orch_input = {
        "container": container,
        "blobName": blob_name,
        "expectedData": expected_data,
        "requestContext": request_context,
    }
    instance_id = await client.start_new("orchestrator", None, orch_input)
    logger.info("Orchestrator started with instance_id=%s", instance_id)

    response = client.create_check_status_response(req, instance_id)
    logger.info("Response status=%s", response.status_code)

    # Read body once
    _body_bytes = response.get_body()
    _body_text = (
        _body_bytes.decode("utf-8")
        if isinstance(_body_bytes, (bytes, bytearray))
        else str(_body_bytes)
    )
    logger.info("Response body (raw): %s", _body_text)

    # Pretty-print JSON if valid
    try:
        _body_json = json.loads(_body_text)
        logger.info(
            "Response body (json): %s",
            json.dumps(_body_json, indent=2, ensure_ascii=False),
        )
    except Exception as e:
        # Not JSON; keep raw only
        logger.debug("Response body is not valid JSON: %s", e)
    return response
