# Vision Pipeline · Azure Durable Functions

## Descripción general
Este proyecto implementa una canalización de visión por computadora para validar etiquetas de productos utilizando **Azure Functions** y **Azure Durable Functions**. El flujo procesa imágenes almacenadas en Blob Storage, mejora su calidad, detecta códigos de barras, ejecuta OCR con Azure AI Vision y contrasta los resultados con los datos esperados antes de registrar el resultado completo en PostgreSQL. El orquestador se invoca mediante un endpoint HTTP y expone enlaces estándar de Durable Functions para consultar el progreso.

## Características clave
- Optimización de imágenes (enfoque, contraste, escala de grises) previa al análisis de texto y códigos de barras.
- Extracción de códigos de barras con ZXing CPP y generación de overlays/recortes para auditoría visual.
- Integración con Azure Computer Vision (Image Analysis 2023-10-01) para OCR, con creación de overlays de líneas detectadas.
- Validación semántica contra datos esperados del lote (orden, lote y caducidad).
- Persistencia idempotente del resultado completo en PostgreSQL mediante JSONB, preparada para explotación analítica.
- Función auxiliar para emitir SAS de subida/lectura controlada en Blob Storage.

## Arquitectura de la solución
El flujo se articula alrededor de un orquestador Durable Functions que ejecuta actividades en serie. Cada actividad recibe y devuelve una referencia de blob `{"container": ..., "blobName": ...}` para encadenar los pasos.
```text
http_start (HTTP Trigger)
        │
        ▼
orchestrator (Durable Orchestration)
        ├─► enhance_focus
        ├─► adjust_contrast_brightness
        ├─► to_grayscale
        ├─► analyze_barcode
        ├─► run_ocr
        ├─► validate_extracted_data
        └─► persist_run
```

### Flujo de datos y contenedores
| Etapa | Función | Contenedor origen → destino | Resultado principal |
|-------|---------|----------------------------|---------------------|
| Subida inicial | — | `input/uploads/<archivo>` | Imagen original |
| Nitidez | `enhance_focus` | `input` → `work/focus/<uuid>.png` | Imagen enfocada en espacio LAB |
| Contraste | `adjust_contrast_brightness` | `work/focus` → `work/contrast/<uuid>.png` | CLAHE configurable por entorno |
| Escala de grises | `to_grayscale` | `work/contrast` → `work/bw/<uuid>.png` | Imagen 8 bits optimizada |
| Código de barras | `analyze_barcode` | `work/bw` → `output/barcode/...` | Datos + overlay + ROI opcionales |
| OCR y salida final | `run_ocr` | `work/bw` → `output/final/<uuid>.png` | Imagen final + overlay OCR opcional |
| Validación | `validate_extracted_data` | Resultados previos | Flags de cumplimiento |
| Auditoría | `persist_run` | PostgreSQL | Registro `VisionPipelineLog` |

Las actividades de procesamiento de imágenes utilizan un `BlobServiceClient` compartido definido en `shared_code/storage_util.py`, inicializado con las credenciales declaradas en la configuración de la Function App.

## Componentes principales
- **`http_start`** (`/api/process`, `POST`): valida el payload, inicia la orquestación Durable y devuelve los enlaces de seguimiento estándar (status, events, terminate, purge). Ver `http_start/__init__.py` y `http_start/function.json`.
- **`orchestrator`**: define la cadena de actividades, publica estados personalizados (`stage`) tras cada paso y construye la respuesta agregada. Ver `orchestrator/__init__.py`.
- **`enhance_focus`**: aplica unsharp masking adaptativo y CLAHE sobre la luminancia en espacio LAB para mejorar nitidez. Ver `enhance_focus/__init__.py`.
- **`adjust_contrast_brightness`**: ejecuta CLAHE con parámetros configurables y persiste el resultado en `work/contrast/`. Ver `adjust_contrast_brightness/__init__.py`.
- **`to_grayscale`**: decodifica directamente a escala de grises y guarda una versión PNG optimizada en `work/bw/`. Ver `to_grayscale/__init__.py`.
- **`analyze_barcode`**: utiliza `zxingcpp` sobre la imagen en gris, genera metadatos del código de barras y produce overlays/ROIs en el contenedor `output`. Ver `analyze_barcode/__init__.py`.
- **`run_ocr`**: llama al endpoint Azure AI Vision, guarda la copia final y, si corresponde, crea un overlay con las líneas OCR detectadas. Ver `run_ocr/__init__.py`.
- **`validate_extracted_data`**: normaliza el texto OCR, comprueba los valores esperados (orden, lote, caducidad) y evalúa la legibilidad del código de barras. Ver `validate_extracted_data/__init__.py`.
- **`persist_run`**: consolida entrada y salida, mapea campos clave y realiza un `UPSERT` sobre `VisionPipelineLog` en PostgreSQL mediante `psycopg`. Ver `persist_run/__init__.py`.
- **`get_sas`** (`/api/sas`, `POST`): genera SAS de subida controlada al contenedor `input` y de lectura al contenedor `output`. Ver `get_sas/__init__.py` y `get_sas/function.json`.

## Persistencia y modelo de datos
La tabla `VisionPipelineLog` almacena la traza completa de cada instancia Durable. El script `scripts/create_table_VisionPipelineLog.sql` crea la tabla (id UUID, índices por fecha y validación, columnas JSONB para OCR y código de barras) e índices recomendados para consultas frecuentes.
El activity `persist_run` realiza un `INSERT ... ON CONFLICT` contra `instanceId`, rellenando campos esperados/detectados, indicadores de validación y referencias a blobs (`processedImage`, overlays de OCR y código de barras, ROI). Los payloads completos se almacenan en JSONB para análisis posteriores.

## Dependencias y requisitos previos
- Python **3.11**.
- Azure Functions Core Tools 4.x y Node.js 18/20 para depuración local.
- Cuenta de Azure Blob Storage o Azurite (si se ejecuta en local con emulación).
- Azure AI Vision (Computer Vision) con endpoint y API key válidos.
- Base de datos PostgreSQL 12+ accesible desde la Function App.
- Dependencias Python listadas en `requirements.txt`, que incluyen `azure-functions`, `azure-functions-durable`, `azure-storage-blob`, `opencv-python-headless`, `numpy`, `zxing-cpp`, `requests` y `psycopg` v3.

## Configuración de variables de entorno
Declare las siguientes claves en `local.settings.json` (para desarrollo) o en la configuración de la Function App:
| Clave | Descripción |
|-------|-------------|
| `AzureWebJobsStorage` | Cadena de conexión al Storage usado por Functions (Az. Storage o Azurite). |
| `FUNCTIONS_WORKER_RUNTIME` | Debe ser `python`. |
| `BLOB_ACCOUNT_URL`, `BLOB_ACCOUNT_KEY` | Credenciales usadas por `shared_code.storage_util` para descargar/subir blobs. |
| `ADJ_CLAHE_CLIP`, `ADJ_CLAHE_TILE` | Parámetros opcionales de CLAHE para `adjust_contrast_brightness` (por defecto 2.0 y 8). |
| `AZURE_OCR_ENDPOINT`, `AZURE_OCR_KEY` | Endpoint/key del recurso Azure AI Vision utilizado por `run_ocr`. |
| `POSTGRES_URL` | Cadena `postgresql://user:pass@host:5432/db` utilizada por `persist_run`. |

## Puesta en marcha local
1. **Crear entorno virtual e instalar dependencias**
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # Windows: .venv\Scripts\Activate.ps1
   pip install -r requirements.txt
   ```
2. **Configurar `local.settings.json`** con las variables anteriores y, si se usa Azurite, `UseDevelopmentStorage=true` para `AzureWebJobsStorage`.
3. **Iniciar Azurite** (opcional): `azurite --silent --location ./.azurite`.
4. **Arrancar el runtime** desde la raíz del proyecto:
   ```bash
   func start
   ```
5. **Consultar logs** mediante la consola; la configuración `host.json` habilita Application Insights con muestreo para entradas distintas a `Request`.

## Operación manual
1. **Solicitar SAS para subida (opcional)**
   ```http
   POST /api/sas
   {
     "mode": "upload",
     "container": "input",
     "blobName": "uploads/ejemplo.png",
     "minutes": 15,
     "contentType": "image/png"
   }
   ```
   La función restringe la subida al contenedor `input` y la lectura al contenedor `output`.
2. **Invocar el pipeline**
   ```http
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
   El disparador valida el payload y devuelve la respuesta estándar de Durable Functions. El progreso puede consultarse en `statusQueryGetUri`; además el orquestador publica estados personalizados (`stage`) para identificar la actividad en curso.
3. **Resultados finales**: al completarse, la salida incluye `processedImageBlob`, `ocrOverlayBlob` (si hay líneas detectadas), `barcode.barcodeData` con indicadores de detección/legibilidad, referencias a overlays/ROIs y `validation` con los flags `orderOK`, `batchOK`, `expiryOK`, `barcodeOK` y `validationSummary`.

## Monitorización y observabilidad
- Las funciones registran trazas detalladas sobre métricas de imagen, resultados de ZXing y valores esperados/obtenidos, facilitando el diagnóstico en Application Insights o Log Analytics.
- El estado personalizado (`context.set_custom_status`) permite construir dashboards en tiempo real con el progreso de la instancia Durable.
- `run_ocr` informa cuántas regiones OCR se dibujaron en el overlay y registra códigos de error del servicio externo.

## Despliegue recomendado
El archivo `scripts/environment.txt` recopila comandos de Azure CLI para crear recursos (Resource Group, Storage, Function App, AI Vision) y establecer las `app settings`. Incluye también la publicación mediante `func azure functionapp publish` y notas para la base de datos PostgreSQL.
Pasos generales:
1. Crear recursos en la región `westus3` (o la que corresponda) siguiendo las instrucciones del script.
2. Configurar las variables de entorno en la Function App (`BLOB_ACCOUNT_URL`, `BLOB_ACCOUNT_KEY`, `AZURE_OCR_*`, `POSTGRES_URL`, etc.).
3. Crear la tabla `VisionPipelineLog` ejecutando `scripts/create_table_VisionPipelineLog.sql` en la base de datos objetivo.
4. Publicar la aplicación con Functions Core Tools o pipelines CI/CD.

## Estructura del repositorio
```text
vision-pipeline/
├─ adjust_contrast_brightness/   # Activity: CLAHE para contraste
├─ analyze_barcode/              # Activity: detección/overlay de códigos de barras
├─ enhance_focus/                # Activity: unsharp masking + CLAHE
├─ get_sas/                      # HTTP Trigger: generación de SAS
├─ http_start/                   # HTTP Trigger: entrada del pipeline
├─ orchestrator/                 # Orquestador Durable
├─ persist_run/                  # Activity: persistencia en PostgreSQL
├─ run_ocr/                      # Activity: Azure AI Vision OCR + overlay
├─ to_grayscale/                 # Activity: conversión a B/N
├─ validate_extracted_data/      # Activity: validaciones semánticas
├─ shared_code/                  # Utilidades compartidas (BlobServiceClient)
├─ scripts/                      # SQL, ejemplos y automatizaciones
├─ requirements.txt
└─ host.json
```

## Recursos adicionales
- `scripts/test_pipeline.ps1`: ejemplo end-to-end para subir una imagen, invocar la orquestación y recuperar resultados.
- `scripts/resp.json`: respuesta de muestra del pipeline para pruebas manuales.
- `scripts/final_image.png` y `scripts/samplePicture.png`: activos de prueba para validar el flujo completo.

---
Para soporte o mejoras, abra un issue interno describiendo el escenario y adjunte la instancia Durable (`instanceId`) registrada en `VisionPipelineLog`.
