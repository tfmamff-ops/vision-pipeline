# Vision Pipeline (Azure Functions)

## Resumen ejecutivo
Este proyecto implementa una canalización de análisis de imágenes farmacéuticas sobre Azure Functions utilizando Durable Functions para orquestar actividades de visión por computadora. El flujo recibe una imagen subida al contenedor `input`, la mejora, extrae texto y códigos de barras, valida los datos contra referencias esperadas y persiste el resultado para auditoría y trazabilidad.

## Arquitectura general
- **Funciones HTTP**
  - `http_start`: expone el punto de entrada REST que valida la solicitud, inicia la orquestación y devuelve las URL de seguimiento generadas por Durable Functions.
  - `get_sas`: genera SAS temporales para subir imágenes al contenedor `input` o leer resultados desde `output` o `erp`.
- **Orquestación Durable**
  - `orchestrator`: coordina las actividades en serie, controla el estado personalizado y finalmente guarda la corrida en PostgreSQL.
- **Actividades**
  - `enhance_focus`: aplica *adaptive unsharp masking* y CLAHE en el canal de luminancia para mejorar el enfoque.
  - `adjust_contrast_brightness`: mejora contraste y brillo con CLAHE configurable por variables de entorno.
  - `to_grayscale`: convierte la imagen a escala de grises optimizando memoria y rendimiento.
  - `analyze_barcode`: detecta y decodifica códigos de barras usando `zxing-cpp`, generando superposiciones y recortes.
  - `run_ocr`: envía la imagen al servicio Azure Computer Vision, genera una copia final y un overlay con las regiones leídas.
  - `validate_extracted_data`: compara OCR y código de barras contra los valores esperados, con reglas tolerantes y un centinela `N/A` para omitir campos.
  - `persist_run`: consolida la ejecución en la tabla `VisionPipelineLog` sobre PostgreSQL, incluyendo metadatos de usuario, cliente y blobs resultantes.
- **Código compartido**
  - `shared_code/storage_util`: envuelve operaciones de Azure Blob Storage para descargar y subir bytes con `BlobServiceClient`.

Las funciones se describen en los archivos `function.json` correspondientes para integrarse con el runtime de Azure Functions.

## Flujo de procesamiento
1. El cliente solicita un SAS de subida mediante `get_sas` y coloca la imagen en `input/uploads/<uuid>.png`.
2. Inicia la ejecución llamando a `http_start`, proporcionando la referencia del blob, los datos esperados y el contexto del solicitante.
3. `orchestrator` encadena las actividades de mejora de imagen, OCR y código de barras, propagando estados personalizados para telemetría.
4. Los artefactos intermedios se almacenan en el contenedor `work`, y los resultados finales (imagen procesada y overlays) en `output`.
5. `validate_extracted_data` produce banderas booleanas para cada campo y un resumen global.
6. `persist_run` guarda la corrida en PostgreSQL, permitiendo auditoría completa y reejecución idempotente.

## Esquema de datos y almacenamiento
- **Blob Storage**
  - Contenedores: `input` (ingesta), `work` (intermedios), `output` (resultados) y `erp` (solo lectura para integración externa).
  - Los helpers de `storage_util` controlan el tipo de contenido (`image/png`) y el sobreescrito seguro.
- **Base de datos**
  - La tabla `VisionPipelineLog` almacena identidad del operador, contexto del cliente, referencias a blobs y payloads JSONB de OCR/barcode.
  - El script [`scripts/create_table_VisionPipelineLog.sql`](./scripts/create_table_VisionPipelineLog.sql) crea la tabla con índices para trazabilidad y análisis.

## Variables de entorno clave
| Variable | Descripción |
| --- | --- |
| `BLOB_ACCOUNT_URL`, `BLOB_ACCOUNT_KEY` | Credenciales para `BlobServiceClient` usados por todas las actividades de almacenamiento. |
| `ADJ_CLAHE_CLIP`, `ADJ_CLAHE_TILE` | Parámetros opcionales para ajustar CLAHE en `adjust_contrast_brightness`. |
| `AZURE_OCR_ENDPOINT`, `AZURE_OCR_KEY` | Configuración del servicio Azure Computer Vision utilizado por `run_ocr`. |
| `POSTGRES_URL` | Cadena de conexión a PostgreSQL consumida por `persist_run`. |

Las variables adicionales requeridas por Azure Functions (por ejemplo claves de función) se gestionan mediante `local.settings.json` o las configuraciones de la Function App.

## Desarrollo local
1. Crear un entorno virtual y activar:
   ```bash
   python -m venv .venv
   source .venv/bin/activate
   ```
2. Instalar dependencias:
   ```bash
   pip install -r requirements.txt
   ```
3. Configurar `local.settings.json` con las variables anteriores (usar valores de prueba para Blob Storage, Computer Vision y PostgreSQL).
4. Ejecutar el host de Azure Functions:
   ```bash
   func start
   ```
5. Usar herramientas como `curl` o `Postman` para invocar `http://localhost:7071/api/process` siguiendo el payload de ejemplo.

> Nota: `run_ocr` realiza llamadas reales a Azure Computer Vision; para pruebas locales sin acceso al servicio se puede simular la respuesta modificando la actividad.

## Despliegue en Azure
El archivo [`scripts/environment.txt`](./scripts/environment.txt) contiene un procedimiento detallado en PowerShell para:
- Crear grupo de recursos, Storage Account y Function App (Python 3.11, plan de consumo).
- Configurar contenedores y políticas de retención de blobs.
- Registrar parámetros de CLAHE y credenciales en la Function App.
- Aprovisionar Azure Computer Vision y cargar su clave.
- Publicar la aplicación (`func azure functionapp publish`).
- Crear la base de datos PostgreSQL y ejecutar el script SQL.

## Pruebas manuales de extremo a extremo
El script [`scripts/test_pipeline.ps1`](./scripts/test_pipeline.ps1) automatiza la validación desde un entorno con Azure CLI:
1. Solicita SAS de subida a `get_sas`.
2. Carga una imagen local al contenedor `input`.
3. Lanza la ejecución vía `http_start` con datos esperados y contexto de usuario.
4. Hace *polling* del estado Durable hasta completar.
5. Genera SAS de lectura para la imagen procesada y descarga el resultado (`final_image.png`).

El archivo [`scripts/resp.json`](./scripts/resp.json) es un ejemplo de salida serializada de la orquestación.

## Estructura del repositorio
```
├── adjust_contrast_brightness/    # Actividad para mejorar contraste
├── analyze_barcode/               # Actividad de detección/decodificación de códigos de barras
├── enhance_focus/                 # Actividad de enfoque adaptativo
├── function_app.py                # Registro de la Function App
├── get_sas/                       # Función HTTP para generar SAS
├── http_start/                    # Función HTTP que inicia la orquestación
├── orchestrator/                  # Función Durable que coordina el pipeline
├── persist_run/                   # Actividad que persiste resultados en PostgreSQL
├── run_ocr/                       # Actividad que consume Azure Computer Vision
├── shared_code/                   # Utilitarios compartidos (Blob Storage)
├── to_grayscale/                  # Actividad de conversión a escala de grises
├── scripts/                       # Scripts de despliegue, pruebas y recursos de ejemplo
└── requirements*.txt              # Dependencias de Python
```

## Buenas prácticas y consideraciones
- **Validaciones estrictas**: `http_start` exige `requestContext.user.id` para mantener coherencia con las restricciones de base de datos y auditoría.
- **Tolerancia a errores**: `analyze_barcode` devuelve una estructura consistente aunque no detecte códigos; `validate_extracted_data` ignora campos marcados como `N/A`.
- **Idempotencia**: `persist_run` hace *upsert* sobre `instanceId`, permitiendo reintentos sin duplicar registros.
- **Monitoreo**: la orquestación publica `custom_status` en cada etapa, útil para dashboards en Application Insights o portal de Durable Functions.
- **Seguridad**: `get_sas` restringe los SAS de subida al contenedor `input` y los SAS de lectura a `output`/`erp`, reduciendo el riesgo de exfiltración.

## Recursos adicionales
- [Documentación de Durable Functions](https://learn.microsoft.com/azure/azure-functions/durable/durable-functions-overview)
- [Computer Vision Image Analysis](https://learn.microsoft.com/azure/ai-services/computer-vision/)
- [Azure Blob Storage SAS](https://learn.microsoft.com/azure/storage/common/storage-sas-overview)
