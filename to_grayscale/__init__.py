import cv2, uuid
import numpy as np
from shared_code.storage_util import download_bytes, upload_bytes

def main(ref: dict) -> dict:
    raw = download_bytes(ref["container"], ref["blobName"])
    img = cv2.imdecode(np.frombuffer(raw, np.uint8), cv2.IMREAD_COLOR)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    _, buf = cv2.imencode(".png", gray)
    out_name = f"bw/{uuid.uuid4()}.png"
    upload_bytes("work", out_name, buf.tobytes(), "image/png")
    return {"container": "work", "blobName": out_name}
