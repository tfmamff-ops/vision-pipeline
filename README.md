# Vision Pipeline

## Resumen
Vision Pipeline es una solución de Azure Functions con orquestación durable que automatiza el preprocesamiento de imágenes de etiquetas, la extracción de información mediante OCR y la validación contra datos esperados. El flujo trabaja sobre blobs en Azure Storage, genera artefactos derivados (imágenes procesadas, superposiciones y recortes de códigos de barras) y guarda un registro completo de cada ejecución en PostgreSQL.

## Arquitectura de Azure Functions
| Función | Tipo de disparador | Propósito |
| --- | --- | --- |
| `http_start` | HTTP (POST `/api/process`) + `orchestrationClient` | Recibe la solicitud inicial, valida el payload y lanza una nueva instancia del orquestador durable. |
| `orchestrator` | Durable orchestration | Coordina las actividades: enfoque, contraste, escala de grises, análisis de código de barras, OCR, validación y persistencia de resultados. |
| `enhance_focus` | Activity | Ajusta nitidez con Unsharp Mask adaptativo en espacio LAB y publica el resultado en `work/focus/*.png`. |
| `adjust_contrast_brightness` | Activity | Mejora contraste/iluminación mediante CLAHE configurable y guarda en `work/contrast/*.png`. |
| `to_grayscale` | Activity | Convierte eficazmente la imagen a escala de grises y la publica en `work/bw/*.png`. |
| `analyze_barcode` | Activity | Detecta y decodifica códigos de barras con `zxingcpp`, genera overlays/ROI y los sube a `output/barcode/*`. |
| `run_ocr` | Activity | Llama al servicio Azure AI Vision (Image Analysis) para OCR y crea superposiciones con las regiones detectadas. |
| `validate_extracted_data` | Activity | Compara OCR y código de barras con los valores esperados y produce un resumen de validación granular. |
| `persist_run` | Activity | Upsert de resultados en la tabla `VisionPipelineLog` de PostgreSQL, incluyendo blobs asociados y payloads JSONB. |
| `get_sas` | HTTP (POST `/api/sas`) | Emite SAS de subida/lectura con políticas mínimas para los contenedores `input` y `output`. |

## Flujo de procesamiento
1. **Inicio vía HTTP.** Un POST a `/api/process` con contenedor de entrada, blob y datos esperados crea una instancia durable. La función rechaza peticiones que no usen `container: "input"` o que carezcan de `expectedData`.
2. **Preprocesamiento de imagen.**
   - `enhance_focus` lee el blob original, calcula un métrico de desenfoque (varianza del Laplaciano) y ajusta la nitidez antes de subir la imagen enfocada.
   - `adjust_contrast_brightness` aplica CLAHE sobre el canal L en LAB usando parámetros personalizables (`ADJ_CLAHE_CLIP`, `ADJ_CLAHE_TILE`).
   - `to_grayscale` transforma la imagen resultante a escala de grises, lista para OCR/código de barras.
3. **Análisis de código de barras.** `analyze_barcode` intenta decodificar el primer código, calcula su bounding box, genera overlay y recorte, y marca el resultado como “no detectado” si falla cualquier paso.
4. **OCR con Azure AI Vision.** `run_ocr` envía la imagen al endpoint configurado, guarda la copia final en `output/final/*.png` y, si hay líneas reconocidas, genera una superposición con rectángulos azules.
5. **Validación semántica.** `validate_extracted_data` normaliza el texto OCR (mayúsculas y sin espacios) y verifica presencia de `order`, `batch` y `expiry`, además de comprobar que el código de barras se haya detectado y sea legible.
6. **Persistencia.** El orquestador consolida OCR, código de barras y validaciones en un documento que se upserta en PostgreSQL junto con metadatos de blobs y payloads JSONB.
7. **Estados personalizados.** Durante la orquestación se publican estados (`custom_status`) para seguimiento granular (por ejemplo, `enhance_focus_done`, `persisting_run`, `completed`).

## Almacenamiento y blobs
- Uso compartido de credenciales mediante `BlobServiceClient` inicializado con `BLOB_ACCOUNT_URL` y `BLOB_ACCOUNT_KEY`.
- Contenedores recomendados: `input` (ingesta), `work` (intermedios), `output` (resultados finales). Los nombres de blobs devueltos por cada actividad siguen prefijos (`focus/`, `contrast/`, `bw/`, `final/`, `barcode/`).
- `get_sas` limita SAS de subida al contenedor `input` y lectura a `output`, protegiendo la ruta de trabajo intermedia.

## Validación y registro histórico
- Resultados persistidos incluyen flags individuales (`orderOK`, `batchOK`, etc.) y resumen global (`validationSummary`).
- El esquema SQL (`scripts/create_table_VisionPipelineLog.sql`) crea índices por fecha, resultado de validación y valor de código de barras, además de columnas JSONB para inspeccionar payloads completos.

## Configuración del entorno
### Variables de aplicación
Defina las siguientes variables de entorno (localmente via `local.settings.json` y en Azure Function App):
- `BLOB_ACCOUNT_URL` y `BLOB_ACCOUNT_KEY`: acceso a la cuenta de almacenamiento donde residen los contenedores `input/work/output`.
- `ADJ_CLAHE_CLIP`, `ADJ_CLAHE_TILE`: parámetros opcionales para ajustar CLAHE (valores por defecto 2.0 y 8).
- `AZURE_OCR_ENDPOINT`, `AZURE_OCR_KEY`: endpoint y clave del recurso Azure AI Vision utilizado para OCR.
- `POSTGRES_URL`: cadena de conexión (psycopg v3) utilizada por `persist_run`.

### Dependencias de Python
Instale los paquetes listados en `requirements.txt`, que incluyen Azure Functions/Durable, SDK de Storage, OpenCV, ZXing y psycopg v3, entre otros.

## Ejecución local
1. Crear y activar un entorno virtual de Python 3.11.
2. Ejecutar `pip install -r requirements.txt`.
3. Configurar `local.settings.json` con las variables anteriores y el `AzureWebJobsStorage` requerido por Azure Functions (por ejemplo, apuntando al Azurite emulator).
4. Iniciar el host local con Azure Functions Core Tools (`func start`) para exponer los endpoints HTTP y la orquestación durable.

## Despliegue en Azure
- El script `scripts/environment.txt` documenta la creación del grupo de recursos, cuenta de almacenamiento, Function App Linux (Python 3.11) y configuración de contenedores/SAS/OCR en la región `westus3`.
- `scripts/update.ps1` automatiza la actualización remota: activa la venv, instala dependencias y publica con `func azure functionapp publish --build remote --python`.
- Cree la tabla `VisionPipelineLog` en su instancia de PostgreSQL usando el script SQL incluido antes de ejecutar el pipeline por primera vez.

## Operación y observabilidad
- `host.json` habilita Application Insights con muestreo y el paquete de extensiones oficial para Functions v4.
- Cada actividad registra mensajes detallados (`logging.info`/`logging.error`) que facilitan el seguimiento en Application Insights o en los logs locales del host.
- Los estados personalizados del orquestador (`custom_status`) permiten consultar el progreso a través del Durable Functions Management API o el portal de Azure.

## API: ejemplos de solicitud
```json
POST /api/process
{
  "container": "input",
  "blobName": "uploads/ejemplo.png",
  "expectedData": {
    "order": "M-AR-23-00219",
    "batch": "L 97907",
    "expiry": "JUN/2028"
  }
}
```

```json
POST /api/sas
{
  "mode": "upload",
  "container": "input",
  "blobName": "uploads/ejemplo.png",
  "minutes": 10,
  "contentType": "image/png"
}
```
Estos endpoints devuelven referencias de estado durable (`/statusQueryGetUri`) y URLs SAS respectivamente, que la aplicación cliente puede usar para consultar resultados o transferir archivos.
