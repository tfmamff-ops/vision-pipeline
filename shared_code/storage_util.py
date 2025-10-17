import os
from azure.storage.blob import BlobServiceClient, ContentSettings

# Lee las credenciales desde app settings (Function App)
ACCOUNT_URL = os.environ["BLOB_ACCOUNT_URL"]    # p.ej. https://stvision109330379.blob.core.windows.net
ACCOUNT_KEY = os.environ["BLOB_ACCOUNT_KEY"]

# Cliente único reutilizable (conexiones internas son pooleadas)
_bsc = BlobServiceClient(account_url=ACCOUNT_URL, credential=ACCOUNT_KEY)

def download_bytes(container: str, blob_name: str) -> bytes:
    """
    Descarga el blob completo como bytes.
    """
    return (
        _bsc.get_container_client(container)
           .get_blob_client(blob_name)
           .download_blob()
           .readall()
    )

def upload_bytes(container: str, blob_name: str, data: bytes, content_type: str = "application/octet-stream") -> None:
    """
    Sube bytes al blob (overwrite=True) y setea el Content-Type.
    """
    (
        _bsc.get_container_client(container)
            .get_blob_client(blob_name)
            .upload_blob(
                data,
                overwrite=True,
                content_settings=ContentSettings(content_type=content_type)
            )
    )
