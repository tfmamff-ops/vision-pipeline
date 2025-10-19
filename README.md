# Vision Pipeline (Azure Durable Functions)

## Resumen ejecutivo
Este repositorio implementa un pipeline de visión artificial basado en **Azure Durable Functions**. El orquestador coordina múltiples actividades serverless para mejorar imágenes, extraer texto mediante Azure Computer Vision y validar la información frente a datos esperados antes de emitir un resultado consolidado.【F:orchestrator/__init__.py†L3-L34】 El flujo se invoca a través de un disparador HTTP y utiliza Azure Blob Storage para los artefactos de entrada, trabajo intermedio y salida final.

## Arquitectura y flujo de datos
1. **Entrada HTTP** (`/api/process`): recibe la referencia del blob de origen y los metadatos esperados que deben verificarse en la etiqueta del producto.【F:http_start/__init__.py†L6-L41】  
2. **Orquestador Durable**: ejecuta las actividades `enhance_focus`, `adjust_contrast_brightness`, `to_grayscale`, `analyze_barcode`, `run_ocr` y `validate_extracted_data` en secuencia; finalmente entrega el resultado compuesto (imagen procesada, overlay OCR, datos del código de barras y validaciones).【F:orchestrator/__init__.py†L14-L34】  
3. **Azure Blob Storage**: todas las funciones consumen y publican blobs utilizando un `BlobServiceClient` compartido configurado mediante las credenciales de la cuenta de almacenamiento.【F:shared_code/storage_util.py†L1-L34】  
4. **Servicios externos**: `run_ocr` llama al servicio Azure Computer Vision (Image Analysis API 2023‑10‑01) empleando el endpoint y la API key configurados por entorno.【F:run_ocr/__init__.py†L6-L134】  
5. **Respuesta**: se devuelve el estado durable estándar con enlaces para consultar el progreso y, al completarse, la carga JSON con los resultados de OCR, código de barras y validación.【F:http_start/__init__.py†L40-L58】【F:orchestrator/__init__.py†L28-L34】

### Contenedores y rutas de blobs
| Propósito | Contenedor | Carpeta | Fuente |
|-----------|------------|---------|--------|
| Imágenes originales | `input` | `uploads/` u otra ruta definida por el cliente | Entrada HTTP | 
| Trabajo intermedio (enfoque) | `work` | `focus/<uuid>.png` | `enhance_focus`【F:enhance_focus/__init__.py†L17-L59】 |
| Trabajo intermedio (contraste) | `work` | `contrast/<uuid>.png` | `adjust_contrast_brightness`【F:adjust_contrast_brightness/__init__.py†L24-L60】 |
| Trabajo intermedio (B/N) | `work` | `bw/<uuid>.png` | `to_grayscale`【F:to_grayscale/__init__.py†L6-L27】 |
| Salida final | `output` | `final/<uuid>.png` | `run_ocr`【F:run_ocr/__init__.py†L100-L135】 |
| Overlay OCR | `output` | `final/overlay/<uuid>.png` (opcional) | `run_ocr`【F:run_ocr/__init__.py†L119-L134】 |
| Overlay código de barras | `output` | `barcode/overlay/<uuid>.png` (opcional) | `analyze_barcode`【F:analyze_barcode/__init__.py†L140-L166】 |
| Recorte código de barras | `output` | `barcode/roi/<uuid>.png` (opcional) | `analyze_barcode`【F:analyze_barcode/__init__.py†L147-L166】 |

## Funciones Azure incluidas
| Nombre | Tipo de trigger | Responsabilidad principal |
|--------|-----------------|---------------------------|
| `http_start` | `httpTrigger` (POST `/api/process`) | Valida el payload, inicia la orquestación y expone los endpoints de seguimiento.【F:http_start/__init__.py†L6-L58】 |
| `orchestrator` | `orchestrationTrigger` | Coordina la cadena de actividades y compone la respuesta final.【F:orchestrator/__init__.py†L14-L34】 |
| `enhance_focus` | `activityTrigger` | Aplica unsharp masking adaptativo en espacio LAB para mejorar nitidez.【F:enhance_focus/__init__.py†L10-L59】 |
| `adjust_contrast_brightness` | `activityTrigger` | Mejora contraste con CLAHE configurable mediante variables de entorno.【F:adjust_contrast_brightness/__init__.py†L7-L60】 |
| `to_grayscale` | `activityTrigger` | Convierte la imagen a escala de grises optimizando memoria.【F:to_grayscale/__init__.py†L6-L27】 |
| `analyze_barcode` | `activityTrigger` | Detecta y decodifica códigos de barras con ZXing, generando overlays/ROIs opcionales.【F:analyze_barcode/__init__.py†L71-L169】 |
| `run_ocr` | `activityTrigger` | Llama a Azure Computer Vision, guarda la imagen final y genera overlays de líneas OCR.【F:run_ocr/__init__.py†L100-L135】 |
| `validate_extracted_data` | `activityTrigger` | Compara OCR y código de barras frente a los valores esperados y devuelve flags de validación.【F:validate_extracted_data/__init__.py†L49-L119】 |
| `get_sas` | `httpTrigger` (POST `/api/sas`) | Emite URLs SAS restringidas para subir a `input` o leer desde `output` en Blob Storage.【F:get_sas/__init__.py†L16-L70】 |

## Configuración y variables de entorno
Crear un archivo `local.settings.json` (no versionado) con las claves necesarias bajo `Values`. Ejemplo:

```json
{
  "IsEncrypted": false,
  "Values": {
    "AzureWebJobsStorage": "UseDevelopmentStorage=true",
    "FUNCTIONS_WORKER_RUNTIME": "python",
    "BLOB_ACCOUNT_URL": "https://<account>.blob.core.windows.net",
    "BLOB_ACCOUNT_KEY": "<storage-account-key>",
    "AZURE_OCR_ENDPOINT": "https://<resource>.cognitiveservices.azure.com",
    "AZURE_OCR_KEY": "<vision-key>",
    "ADJ_CLAHE_CLIP": "2.0",
    "ADJ_CLAHE_TILE": "8"
  }
}
```

- `BLOB_ACCOUNT_URL` y `BLOB_ACCOUNT_KEY` alimentan al `BlobServiceClient` utilizado por todas las actividades de I/O.【F:shared_code/storage_util.py†L4-L34】  
- `AZURE_OCR_ENDPOINT` y `AZURE_OCR_KEY` permiten autenticar la llamada al servicio Image Analysis 2023‑10‑01.【F:run_ocr/__init__.py†L6-L135】  
- `ADJ_CLAHE_CLIP` y `ADJ_CLAHE_TILE` son opcionales y ajustan el contraste local aplicado por CLAHE.【F:adjust_contrast_brightness/__init__.py†L7-L60】

## Requisitos previos
- Python 3.11 con soporte para virtual environments.
- Node.js 18 LTS o 20 LTS y Azure Functions Core Tools 4.x para ejecutar y depurar funciones localmente.
- Azurite (emulador de Azure Storage) o acceso a una cuenta de almacenamiento real.
- Dependencias Python listadas en `requirements.txt`, incluidas OpenCV, ZXing y SDKs de Azure Functions/Storage.【F:requirements.txt†L1-L37】

## Puesta en marcha local
1. **Clonar y preparar entorno virtual**
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # En Windows: .venv\Scripts\Activate.ps1
   pip install -r requirements.txt
   ```
2. **Arrancar Azurite** (en otra terminal) si se usa el emulador: `azurite --silent --location ./.azurite`.
3. **Configurar `local.settings.json`** con las claves descritas arriba.
4. **Iniciar Functions Core Tools** desde la raíz del proyecto:
   ```bash
   func start
   ```
   El runtime utilizará la configuración global de `host.json`, incluida la integración con Application Insights si está habilitada.【F:host.json†L1-L14】

## Ejecución del pipeline
1. **Subir la imagen de trabajo**: solicitar un SAS temporal (opcional) mediante `POST /api/sas` con payload:
   ```json
   {
     "mode": "upload",
     "container": "input",
     "blobName": "uploads/<archivo>.png",
     "minutes": 15,
     "contentType": "image/png"
   }
   ```
   La función valida que solo se suba al contenedor `input` y devuelve la URL SAS lista para usar.【F:get_sas/__init__.py†L45-L70】

2. **Invocar el proceso durable** con `POST /api/process`:
   ```json
   {
     "container": "input",
     "blobName": "uploads/<archivo>.png",
     "expectedData": {
       "order": "M-AR-23-00219",
       "batch": "L 97907",
       "expiry": "JUN/2028"
     }
   }
   ```
   Si el payload es inválido, se responde `400`. En caso contrario se devuelve el estatus durable estándar con URLs para sondear el estado.【F:http_start/__init__.py†L6-L58】

3. **Consultar el resultado** mediante los enlaces `statusQueryGetUri` o `terminatePostUri`. Al completar, el `output` incluye:
   - `processedImageBlob` y `ocrOverlayBlob` con referencias a los blobs finales.【F:orchestrator/__init__.py†L28-L34】
   - `barcode` con datos y blobs opcionales de overlay/ROI.【F:analyze_barcode/__init__.py†L156-L169】
   - `validation` con indicadores `orderOK`, `batchOK`, `expiryOK`, `barcodeOK` y un resumen agregado.【F:validate_extracted_data/__init__.py†L82-L114】

## Observabilidad y registros
- Las funciones realizan logging detallado para cada etapa, incluyendo trazas de validación y métricas de procesamiento de imágenes.【F:http_start/__init__.py†L19-L58】【F:analyze_barcode/__init__.py†L87-L169】【F:validate_extracted_data/__init__.py†L60-L117】
- `host.json` habilita Application Insights con muestreo para tipos distintos de `Request` (ver `logging.applicationInsights`).【F:host.json†L1-L14】

## Despliegue en Azure
1. Crear recursos: cuenta de almacenamiento (GPv2), Azure Function App (plan de consumo o Premium) y recurso de Azure AI Vision (Computer Vision 2023‑10‑01).
2. Configurar las variables de entorno del Function App con las claves mencionadas.
3. Publicar el proyecto con `func azure functionapp publish <nombre-funcion>` o mediante pipelines CI/CD.
4. Revisar reglas de red y permisos del Storage para garantizar el acceso desde la Function App.

## Scripts auxiliares
La carpeta `scripts/` contiene ejemplos de payloads y automatizaciones (PowerShell) para probar la orquestación end-to-end, junto con artefactos de referencia como `ocrResult.json`.

## Licencia y soporte
Documenta internamente los contratos de respuesta y coordina con el equipo de plataforma para la monitorización del recurso. Abra issues en este repositorio para rastrear mejoras o incidencias.
