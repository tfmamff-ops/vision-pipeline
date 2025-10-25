# Vision Pipeline (Azure Functions)

## Descripción general
Este repositorio contiene una solución completa de Azure Functions Durable orientada a automatizar la ingesta de imágenes de productos farmacéuticos, aplicar un pipeline de mejora visual, extraer texto y códigos de barras, y validar los resultados frente a datos esperados. El orquestador definido en [./orchestrator/__init__.py](./orchestrator/__init__.py) coordina actividades especializadas de preprocesado de imagen, análisis OCR y lectura de códigos, así como la persistencia auditada de cada ejecución en PostgreSQL.

La solución está pensada para operar sobre blobs en Azure Storage y proporcionar mecanismos seguros de subida/descarga mediante SAS, garantizando trazabilidad del usuario que dispara el flujo, la versión del cliente y las evidencias generadas en el proceso.

## Arquitectura y flujo de alto nivel
1. **Carga del archivo**: un cliente solicita una URL de subida firmada mediante la Function HTTP [`get_sas`](./get_sas/__init__.py) y coloca la imagen en `input/uploads/` del Storage.
2. **Inicio del pipeline**: el cliente invoca la Function HTTP [`http_start`](./http_start/__init__.py), enviando la referencia del blob, los datos esperados (lote, caducidad, etc.) y el contexto de usuario.
3. **Orquestación Durable**: el flujo definido en [`orchestrator`](./orchestrator/__init__.py) ejecuta secuencialmente las actividades de mejora de foco, ajuste de contraste, conversión a escala de grises, análisis de código de barras, OCR y validación.
4. **Persistencia y entrega**: tras combinar los resultados, se generan blobs finales y se invoca [`persist_run`](./persist_run/__init__.py) para guardar la ejecución en la tabla `VisionPipelineLog`. El cliente puede consultar el estado a través de los endpoints de Durable Functions y descargar resultados mediante SAS de lectura.

El diagrama conceptual se resume en:
```
Cliente → get_sas (upload) → Azure Storage (input)
       → http_start → Orchestrator
           ├─ enhance_focus
           ├─ adjust_contrast_brightness
           ├─ to_grayscale
           ├─ analyze_barcode
           ├─ run_ocr
           └─ validate_extracted_data → persist_run → PostgreSQL
       → get_sas (read) → Azure Storage (output)
```

## Componentes principales
- **`http_start`** ([código](./http_start/__init__.py)) valida el payload entrante, exige la identidad del operador y arranca una nueva instancia Durable con el contexto completo, registrando entradas y respuestas para auditoría.【F:http_start/__init__.py†L1-L107】
- **`orchestrator`** ([código](./orchestrator/__init__.py)) procesa la imagen aplicando actividades en cadena, monitoriza el avance con `set_custom_status` y agrega resultados de OCR, código de barras y validación antes de persistirlos.【F:orchestrator/__init__.py†L1-L82】
- **Actividades de imagen**:
  - [`enhance_focus`](./enhance_focus/__init__.py): aplica unsharpening adaptativo y CLAHE sobre el canal de luminancia para recuperar nitidez.【F:enhance_focus/__init__.py†L1-L53】
  - [`adjust_contrast_brightness`](./adjust_contrast_brightness/__init__.py): utiliza CLAHE en espacio LAB para mejorar contraste local configurable por variables de entorno.【F:adjust_contrast_brightness/__init__.py†L1-L52】
  - [`to_grayscale`](./to_grayscale/__init__.py): convierte eficientemente a escala de grises generando un nuevo blob intermedio.【F:to_grayscale/__init__.py†L1-L23】
- **Análisis y extracción**:
  - [`analyze_barcode`](./analyze_barcode/__init__.py) decodifica códigos con `zxingcpp`, genera overlays y regiones de interés para trazabilidad.【F:analyze_barcode/__init__.py†L1-L118】
  - [`run_ocr`](./run_ocr/__init__.py) consume Azure Computer Vision (2023-10-01) para OCR, replica la imagen final en `output/final/` y crea overlays con bounding boxes de líneas detectadas.【F:run_ocr/__init__.py†L1-L94】
  - [`validate_extracted_data`](./validate_extracted_data/__init__.py) contrasta OCR y código de barras con los datos esperados, admite el marcador `N/A` para omitir campos y devuelve un resumen booleano por campo y total.【F:validate_extracted_data/__init__.py†L1-L123】
- **Servicios de infraestructura**:
  - [`get_sas`](./get_sas/__init__.py) genera enlaces firmados temporales con políticas específicas para carga o lectura.【F:get_sas/__init__.py†L1-L69】
  - [`persist_run`](./persist_run/__init__.py) realiza un `UPSERT` idempotente en PostgreSQL, almacenando tanto campos normalizados como payloads JSONB completos y referencias a blobs derivados.【F:persist_run/__init__.py†L1-L116】
  - [`shared_code/storage_util.py`](./shared_code/storage_util.py) centraliza descargas y subidas a Blob Storage reutilizando un único `BlobServiceClient`.【F:shared_code/storage_util.py†L1-L27】

## Persistencia y auditoría
La tabla `VisionPipelineLog` definida en [./scripts/create_table_VisionPipelineLog.sql](./scripts/create_table_VisionPipelineLog.sql) captura:
- Identificadores de ejecución (`instanceId`), marcas de tiempo y estado.
- Identidad del usuario y metadatos del cliente que inició el flujo.
- Información esperada del producto (código, descripción, orden, lote, caducidad).
- Flags de validación individuales y resumen final.
- Referencias a blobs generados (imagen procesada, overlays, ROI) y payloads JSONB para inspección posterior.【F:scripts/create_table_VisionPipelineLog.sql†L1-L94】

## Variables de entorno requeridas
Configura estos parámetros en la Function App o en `local.settings.json` antes de ejecutar:
- `BLOB_ACCOUNT_URL`, `BLOB_ACCOUNT_KEY`: credenciales de Azure Storage usadas por [`shared_code/storage_util.py`](./shared_code/storage_util.py).【F:shared_code/storage_util.py†L1-L27】
- `ADJ_CLAHE_CLIP`, `ADJ_CLAHE_TILE`: ajustes opcionales para `adjust_contrast_brightness` (por defecto 2.0 y 8).【F:adjust_contrast_brightness/__init__.py†L6-L12】
- `AZURE_OCR_ENDPOINT`, `AZURE_OCR_KEY`: endpoint y clave del servicio Azure Computer Vision para [`run_ocr`](./run_ocr/__init__.py).【F:run_ocr/__init__.py†L1-L47】
- `POSTGRES_URL`: cadena de conexión para almacenar logs mediante [`persist_run`](./persist_run/__init__.py).【F:persist_run/__init__.py†L1-L11】

## Dependencias
Las bibliotecas necesarias se documentan en [requirements.txt](./requirements.txt). Destacan `azure-functions`, `azure-functions-durable`, `opencv-python-headless`, `numpy`, `zxing-cpp` para visión por computador, `requests` para el OCR remoto y `psycopg` para PostgreSQL.【F:requirements.txt†L1-L37】

## Despliegue sugerido
El script [./scripts/environment.txt](./scripts/environment.txt) detalla un procedimiento paso a paso en PowerShell para:
1. Crear el grupo de recursos, cuenta de almacenamiento y Function App (Python 3.11, región `westus3`).
2. Habilitar contenedores `input`, `work`, `output`, `erp` y características opcionales de seguridad en Blob Storage.
3. Registrar las `App Settings` necesarias (Storage, parámetros de CLAHE, credenciales OCR).
4. Publicar la Function App con Azure Functions Core Tools y preparar la base de datos PostgreSQL (incluyendo ejecución del script SQL).
5. Consultar y administrar la tabla de auditoría mediante `psql`.
【F:scripts/environment.txt†L1-L84】

## Prueba de extremo a extremo
Utiliza [./scripts/test_pipeline.ps1](./scripts/test_pipeline.ps1) para validar el servicio tras el despliegue. El script:
1. Obtiene un SAS de subida (`get_sas`).
2. Carga una imagen local al contenedor `input`.
3. Ejecuta `http_start` con datos esperados y contexto de usuario.
4. Consulta periódicamente el estado Durable hasta completar.
5. Guarda la respuesta JSON, solicita un SAS de lectura y descarga la imagen final procesada.
【F:scripts/test_pipeline.ps1†L1-L90】

## Buenas prácticas operativas
- **Observabilidad**: todas las funciones registran eventos detallados con `logging`, facilitando el seguimiento en Application Insights.【F:http_start/__init__.py†L23-L105】【F:analyze_barcode/__init__.py†L52-L109】
- **Idempotencia**: el `UPSERT` de [`persist_run`](./persist_run/__init__.py) evita duplicados por reintentos del orquestador.【F:persist_run/__init__.py†L42-L110】
- **Seguridad**: `get_sas` impone políticas diferenciadas para subida/lectura y fuerza el contenedor apropiado, reduciendo riesgos de exposición de blobs sensibles.【F:get_sas/__init__.py†L32-L64】
- **Flexibilidad en validación**: la función [`validate_extracted_data`](./validate_extracted_data/__init__.py) admite el marcador `N/A` para omitir campos que no se deban comprobar en determinadas campañas.【F:validate_extracted_data/__init__.py†L34-L80】

## Recursos adicionales
- [host.json](./host.json) define configuración básica de logging y el uso del extension bundle v4.【F:host.json†L1-L13】
- Imágenes de ejemplo y respuestas capturadas (`samplePicture.png`, `resp.json`, `final_image.png`) están disponibles en [./scripts](./scripts) para referencia rápida.

---
Para contribuciones futuras, se recomienda mantener la separación de responsabilidades de cada actividad, asegurar que todos los blobs generados residan en contenedores `work` u `output`, y actualizar los scripts de despliegue si se añaden nuevos parámetros de configuración.
