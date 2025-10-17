# OCR con Azure Durable Functions (pipeline de visión)

## Problema

## Definición

Se necesita procesar una imagen (caja de medicamento) aplicando una secuencia automática:

- Mejorar el enfoque.
- Convertir a blanco y negro.
- Enviar al OCR de Azure y obtener el texto en JSON junto con la imagen final.

## Solución

Usar **Azure Durable Functions (Python)** para crear un pipeline serverless:

- enhance_focus → mejora la nitidez (OpenCV).
- to_grayscale → convierte a B/N.
- run_ocr → invoca Azure Computer Vision (recurso agm-first-ocr).

El orquestador ejecuta las tres en secuencia y devuelve {ocrResult, processedImage}.
Funciona dentro del plan gratuito de estudiante, región: canadacentral.

## Paso 0: entorno local

```powershell
node -v
# Debe ser v18 o v20 (LTS)
# winget install OpenJS.NodeJS.LTS

python --version
# Debe ser 3.11 (recomendado)

func --version
# Debe mostrar algo como 4.x.x
# npm install -g azure-functions-core-tools@4 --unsafe-perm true

az --version
# Debe responder sin error
# winget install Microsoft.AzureCLI
# Mi usuario de unir tiene las regiones ["canadacentral","chilecentral","westus3","southcentralus","southafricanorth"]
# Para desarrollo estoy usando esta región porque algunas de las otras no funcionan: canadacentral

# Durable Functions requiere Azure Storage para manejar colas internas.
# Para ejecutar el proyecto localmente, se utiliza Azurite, el emulador oficial de Azure Storage.
npm install -g azurite

# Ejecutar azurite en otra terminal (no cerrarla)
azurite --silent --location C:\Alvaro\dev\tfm-dev\azure\.azurite --debug C:\Alvaro\dev\tfm-dev\azure\.azurite\debug.log
```

## Paso 1 — Creación del proyecto Durable Functions (Python)

Objetivo: crear la estructura base del proyecto Azure Durable Functions para el pipeline de procesamiento de imágenes.

### Navegar al directorio de trabajo

```powershell
cd C:\Alvaro\dev\tfm-dev\azure
```

### Inicializar el proyecto de Azure Functions

```powershell
func init vision-pipeline --python
```

> Crea la carpeta `vision-pipeline` con la estructura base de un proyecto Azure Functions en Python.

### Ingresar al directorio del proyecto

```powershell
cd vision-pipeline
```

### Crear y usar un entorno virtual del proyecto (recomendado)

```powershell
cd C:\Alvaro\dev\tfm-dev\azure\vision-pipeline
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python --version
# Debe mostrar 3.11.x
```

### Instalar dependencias necesarias

```powershell
pip install azure-functions
pip install azure-functions-durable
pip freeze > requirements.txt
```

> Se instala el SDK principal de Azure Functions y el paquete para Durable Functions.
> El archivo `requirements.txt` guardará las dependencias para el despliegue en Azure.

### Resultado esperado

La carpeta `vision-pipeline` debe contener al menos los siguientes archivos:

```text
host.json
requirements.txt
```

El archivo `local.settings.json` se agregará más adelante para la configuración local.

## Paso 2 — Crear manualmente el orquestador Durable Function

Objetivo: definir la función que orquesta las tres actividades: `enhance_focus`, `to_grayscale` y `run_ocr`.

### Crear la carpeta y los archivos del orquestador

Desde PowerShell, dentro del proyecto:

```powershell
cd C:\Alvaro\dev\tfm-dev\azure\vision-pipeline
mkdir orchestrator
cd orchestrator
New-Item -Path . -Name "__init__.py" -ItemType "file"
New-Item -Path . -Name "function.json" -ItemType "file"
```

### Editar `__init__.py`

Abrir el archivo recién creado (`C:\Alvaro\dev\tfm-dev\azure\vision-pipeline\orchestrator\__init__.py`)
y pegar el siguiente código:

```python
import azure.functions as func
import azure.durable_functions as df

def orchestrator_function(context: df.DurableOrchestrationContext):
    # Entrada: imagen original (bytes o base64)
    image_data = context.get_input()

    # Paso 1: mejorar enfoque
    focused_image = yield context.call_activity("enhance_focus", image_data)

    # Paso 2: convertir a blanco y negro
    bw_image = yield context.call_activity("to_grayscale", focused_image)

    # Paso 3: ejecutar OCR
    ocr_result = yield context.call_activity("run_ocr", bw_image)

    # Resultado final
    return {
        "ocrResult": ocr_result,
        "processedImage": bw_image
    }

# Punto de entrada del orquestador
main = df.Orchestrator.create(orchestrator_function)
```

### Editar `function.json`

Abrir el archivo `function.json` y pegar:

```json
{
  "bindings": [
    {
      "name": "context",
      "type": "orchestrationTrigger",
      "direction": "in"
    }
  ],
  "scriptFile": "__init__.py"
}
```

---

### Verificar estructura resultante

```text
vision-pipeline/
 ├── orchestrator/
 │   ├── __init__.py
 │   └── function.json
 ├── host.json
 └── requirements.txt
```

## Paso 3 — Crear las funciones de actividad

Objetivo: implementar las tres funciones que serán llamadas por el orquestador. Cada función realiza una etapa del pipeline de visión artificial.

---

### Crear la función `enhance_focus`

Desde PowerShell, en la raíz del proyecto:

```powershell
cd C:\Alvaro\dev\tfm-dev\azure\vision-pipeline
mkdir enhance_focus
cd enhance_focus
New-Item -Path . -Name "__init__.py" -ItemType "file"
New-Item -Path . -Name "function.json" -ItemType "file"
```

#### Contenido de `enhance_focus/__init__.py`

```python
import base64
import cv2
import numpy as np

def _var_laplacian(img_gray: np.ndarray) -> float:
    return cv2.Laplacian(img_gray, cv2.CV_64F).var()

def _gaussian_psf(shape, sigma):
    h, w = shape
    y, x = np.indices((h, w))
    cy, cx = h // 2, w // 2
    psf = np.exp(-((x - cx) ** 2 + (y - cy) ** 2) / (2 * sigma ** 2))
    psf /= psf.sum()
    return psf

def _wiener_deconv(img, psf, k=0.01):
    # img, psf en float32 [0..1]
    eps = 1e-7
    G = np.fft.fft2(img)
    H = np.fft.fft2(np.fft.ifftshift(psf), s=img.shape)
    H_conj = np.conj(H)
    denom = (np.abs(H) ** 2) + k
    F_hat = (H_conj / (denom + eps)) * G
    rec = np.fft.ifft2(F_hat).real
    rec = np.clip(rec, 0.0, 1.0).astype(np.float32)
    return rec

def main(image_data: str) -> str:
    # 1) decode
    image_bytes = base64.b64decode(image_data)
    npimg = np.frombuffer(image_bytes, np.uint8)
    bgr = cv2.imdecode(npimg, cv2.IMREAD_COLOR)

    # 2) a gris + medir blur
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    blur_metric = _var_laplacian(gray)

    # 3) estimar sigma del PSF (mayor blur_metric => mejor enfoque => sigma más chico)
    # rangos empíricos para fotos de móvil
    # si var<20 está MUY desenfocado
    if blur_metric < 20:
        sigma = 3.0
        k = 0.02
    elif blur_metric < 60:
        sigma = 2.2
        k = 0.015
    elif blur_metric < 120:
        sigma = 1.6
        k = 0.01
    else:
        sigma = 1.2
        k = 0.008

    # 4) deconvolución Wiener en FFT
    img_f32 = gray.astype(np.float32) / 255.0
    psf = _gaussian_psf(img_f32.shape, sigma)
    rec = _wiener_deconv(img_f32, psf, k=k)

    # 5) unsharp mask suave
    blurred = cv2.GaussianBlur(rec, (0, 0), 1.0)
    sharpen = cv2.addWeighted(rec, 1.6, blurred, -0.6, 0)

    # 6) CLAHE para contraste local
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    out_u8 = (np.clip(sharpen, 0, 1) * 255).astype(np.uint8)
    out_u8 = clahe.apply(out_u8)

    # 7) re-encode a PNG base64 (dejamos 8-bit gris; tu paso to_grayscale sigue siendo idempotente)
    _, buffer = cv2.imencode('.png', out_u8)
    return base64.b64encode(buffer).decode('utf-8')
```

#### Contenido de `enhance_focus/function.json`

```json
{
  "bindings": [
    {
      "name": "image_data",
      "type": "activityTrigger",
      "direction": "in"
    }
  ],
  "scriptFile": "__init__.py"
}
```

---

### Crear la función `to_grayscale`

Desde PowerShell:

```powershell
cd ..
mkdir to_grayscale
cd to_grayscale
New-Item -Path . -Name "__init__.py" -ItemType "file"
New-Item -Path . -Name "function.json" -ItemType "file"
```

#### Contenido de `to_grayscale/__init__.py`

```python
import azure.functions as func
import cv2
import numpy as np
import base64

def main(image_data: str) -> str:
    image_bytes = base64.b64decode(image_data)
    npimg = np.frombuffer(image_bytes, np.uint8)
    img = cv2.imdecode(npimg, cv2.IMREAD_COLOR)

    # Convertir a escala de grises
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    _, buffer = cv2.imencode('.png', gray)
    return base64.b64encode(buffer).decode('utf-8')
```

#### Contenido de `to_grayscale/function.json`

```json
{
  "bindings": [
    {
      "name": "image_data",
      "type": "activityTrigger",
      "direction": "in"
    }
  ],
  "scriptFile": "__init__.py"
}
```

---

### Crear la función `run_ocr`

Desde PowerShell:

```powershell
cd ..
mkdir run_ocr
cd run_ocr
New-Item -Path . -Name "__init__.py" -ItemType "file"
New-Item -Path . -Name "function.json" -ItemType "file"
```

#### Contenido de `run_ocr/__init__.py`

```python
import azure.functions as func
import base64
import requests
import os

def main(image_data: str) -> dict:
    endpoint = os.environ["AZURE_OCR_ENDPOINT"].rstrip("/")
    key = os.environ["AZURE_OCR_KEY"]

    image_bytes = base64.b64decode(image_data)

    # Image Analysis 4.0 (Read)
    url = (
        f"{endpoint}/computervision/imageanalysis:analyze"
        f"?api-version=2023-10-01&features=read"
    )

    headers = {
        "Ocp-Apim-Subscription-Key": key,
        "Content-Type": "application/octet-stream"
    }

    resp = requests.post(url, headers=headers, data=image_bytes, timeout=30)
    try:
        data = resp.json()
    except Exception:
        data = {"error": {"code": str(resp.status_code), "message": resp.text}}

    # Devuelve siempre JSON útil
    return {
        "statusCode": resp.status_code,
        "endpointUsed": url,
        "ocrRaw": data
    }
```

#### Contenido de `run_ocr/function.json`

```json
{
  "bindings": [
    {
      "name": "image_data",
      "type": "activityTrigger",
      "direction": "in"
    }
  ],
  "scriptFile": "__init__.py"
}
```

---

### Dependencias adicionales

Desde la raíz del proyecto, instalar las librerías requeridas:

```powershell
pip install opencv-python requests numpy
pip freeze > requirements.txt
```

---

### Variables de entorno (OCR de Azure)

Crear o editar el archivo `local.settings.json` en la raíz del proyecto:

```json
{
  "IsEncrypted": false,
  "Values": {
    "AzureWebJobsStorage": "UseDevelopmentStorage=true",
    "FUNCTIONS_WORKER_RUNTIME": "python",
    "AZURE_OCR_ENDPOINT": "https://agm-first-ocr.cognitiveservices.azure.com",
    "AZURE_OCR_KEY": "<TU_API_KEY_AQUI>"
  }
}
```

## Paso 4 — Crear la función HTTP Starter (inicio del orquestador)

Objetivo: crear una función HTTP que reciba una imagen, la convierta a base64 (si es binaria) y dispare el orquestador `orchestrator`.

### Crear la carpeta y los archivos

Desde PowerShell, en el directorio del proyecto:

```powershell
cd C:\Alvaro\dev\tfm-dev\azure\vision-pipeline
mkdir http_start
cd http_start
New-Item -Path . -Name "__init__.py" -ItemType "file"
New-Item -Path . -Name "function.json" -ItemType "file"
```

### Contenido de `http_start/__init__.py`

```python
import azure.functions as func
import azure.durable_functions as df
import base64

async def main(req: func.HttpRequest, starter: str) -> func.HttpResponse:
    client = df.DurableOrchestrationClient(starter)

    # get_body() es síncrono → NO usar await
    body = req.get_body()
    content_type = (req.headers.get("content-type") or "").lower()

    # Si viene texto (json/plain), asumimos base64 en el body; si no, binario y lo pasamos a b64
    if "application/json" in content_type or "text/plain" in content_type:
        image_b64 = body.decode("utf-8")
    else:
        image_b64 = base64.b64encode(body).decode("utf-8")

    # start_new SÍ es async → usar await
    instance_id = await client.start_new("orchestrator", None, image_b64)

    return client.create_check_status_response(req, instance_id)
```

### Contenido de `http_start/function.json`

```json
{
  "bindings": [
    {
      "authLevel": "anonymous",
      "type": "httpTrigger",
      "direction": "in",
      "name": "req",
      "methods": [ "post" ],
      "route": "process"
    },
    {
      "type": "http",
      "direction": "out",
      "name": "$return"
    },
    {
      "type": "orchestrationClient",
      "direction": "in",
      "name": "starter"
    }
  ],
  "scriptFile": "__init__.py"
}
```

### Probar localmente (Ojo que ahora que uso un blob no puedo probar localmente porque no lo tengo)

1. Activar el entorno virtual:

```powershell
cd C:\Alvaro\dev\tfm-dev\azure\vision-pipeline
.\.venv\Scripts\Activate.ps1
```

1. Iniciar Azure Functions (Azurite debe estar levantado):

```powershell
func start
```

1. Enviar una imagen de prueba:

```powershell
curl -X POST -H "Content-Type: application/octet-stream" --data-binary "@C:\Alvaro\dev\tfm-dev\azure\vision-pipeline\img\holaMundo.png" http://localhost:7071/api/process
```

El resultado mostrará un JSON con una URL de estado (`statusQueryGetUri`).
Abrí esa URL en el navegador (o se puede usar curl) para verificar el progreso del orquestador y ver el resultado final.

```json
{"id": "283356d8bd604eeba8d12c012d28fd68", "statusQueryGetUri": "http://localhost:7071/runtime/webhooks/durabletask/instances/283356d8bd604eeba8d12c012d28fd68?taskHub=TestHubName&connection=Storage&code=pV7UsyY5ZowC6mg3jakwpOiVMoM6zotJJdwVa8iV6meYAzFuuDTR4w==", "sendEventPostUri": "http://localhost:7071/runtime/webhooks/durabletask/instances/283356d8bd604eeba8d12c012d28fd68/raiseEvent/{eventName}?taskHub=TestHubName&connection=Storage&code=pV7UsyY5ZowC6mg3jakwpOiVMoM6zotJJdwVa8iV6meYAzFuuDTR4w==", "terminatePostUri": "http://localhost:7071/runtime/webhooks/durabletask/instances/283356d8bd604eeba8d12c012d28fd68/terminate?reason={text}&taskHub=TestHubName&connection=Storage&code=pV7UsyY5ZowC6mg3jakwpOiVMoM6zotJJdwVa8iV6meYAzFuuDTR4w==", "rewindPostUri": "http://localhost:7071/runtime/webhooks/durabletask/instances/283356d8bd604eeba8d12c012d28fd68/rewind?reason={text}&taskHub=TestHubName&connection=Storage&code=pV7UsyY5ZowC6mg3jakwpOiVMoM6zotJJdwVa8iV6meYAzFuuDTR4w==", "purgeHistoryDeleteUri": "http://localhost:7071/runtime/webhooks/durabletask/instances/283356d8bd604eeba8d12c012d28fd68?taskHub=TestHubName&connection=Storage&code=pV7UsyY5ZowC6mg3jakwpOiVMoM6zotJJdwVa8iV6meYAzFuuDTR4w==", "restartPostUri": "http://localhost:7071/runtime/webhooks/durabletask/instances/283356d8bd604eeba8d12c012d28fd68/restart?taskHub=TestHubName&connection=Storage&code=pV7UsyY5ZowC6mg3jakwpOiVMoM6zotJJdwVa8iV6meYAzFuuDTR4w==", "suspendPostUri": "http://localhost:7071/runtime/webhooks/durabletask/instances/283356d8bd604eeba8d12c012d28fd68/suspend?reason={text}&taskHub=TestHubName&connection=Storage&code=pV7UsyY5ZowC6mg3jakwpOiVMoM6zotJJdwVa8iV6meYAzFuuDTR4w==", "resumePostUri": "http://localhost:7071/runtime/webhooks/durabletask/instances/283356d8bd604eeba8d12c012d28fd68/resume?reason={text}&taskHub=TestHubName&connection=Storage&code=pV7UsyY5ZowC6mg3jakwpOiVMoM6zotJJdwVa8iV6meYAzFuuDTR4w=="}
```

Para transformar base64 a imagen podés usar este sitio: [codebeautify.org/base64-to-image-converter](https://codebeautify.org/base64-to-image-converter)

## Paso 5 — Despliegue en Azure (canadacentral, Python 3.11)

Objetivo: crear recursos en Azure y publicar la Function App (Durable) con runtime **Python 3.11**.

> Requisitos: `az` (Azure CLI), `func` (Azure Functions Core Tools) y el proyecto listo en `vision-pipeline`.

### 5.1 — Variables (ajustá nombres únicos)

```powershell
# NOMBRES (cambiá los valores entre <> por los tuyos)
$RG="rg-vision-pipeline"
$LOC="canadacentral"
$STO="stvision$(Get-Random)"      # debe ser único globalmente (solo minúsculas y números)
$APP="func-vision-pipeline-<tu-inicial-o-id>"  # único globalmente, poner "agm"
$OCR_ENDPOINT="https://agm-first-ocr.cognitiveservices.azure.com"
$OCR_KEY="<TU_API_KEY_REAL>"
```

### 5.2 — Login y suscripción

```powershell
az login
# opcional si manejás varias suscripciones:
# az account set --subscription "<NOMBRE_O_ID_DE_TU_SUSCRIPCION>"
```

### 5.3 — Crear grupo de recursos y Storage

```powershell
az group create -n $RG -l $LOC

az storage account create `
  -n $STO -g $RG -l $LOC `
  --sku Standard_LRS --kind StorageV2
```

### 5.4 — Crear Function App (consumption, Linux, v4, Python 3.11)

```powershell
az functionapp create `
  --name $APP `
  --resource-group $RG `
  --consumption-plan-location $LOC `
  --runtime python `
  --runtime-version 3.11 `
  --functions-version 4 `
  --os-type Linux `
  --storage-account $STO
```

Esto configura automáticamente AzureWebJobsStorage y el Task Hub para Durable Functions.

### 5.5 — App Settings (OCR)

```powershell
az functionapp config appsettings set -g $RG -n $APP --settings `
  AZURE_OCR_ENDPOINT=$OCR_ENDPOINT `
  AZURE_OCR_KEY=$OCR_KEY `
  WEBSITE_RUN_FROM_PACKAGE=1
```

### 5.6 — Publicar desde local

Desde la raíz del proyecto (vision-pipeline) y con tu venv activado:

```powershell
cd C:\Alvaro\dev\tfm-dev\azure\vision-pipeline
.\.venv\Scripts\Activate.ps1
func azure functionapp publish $APP
```

Esto empaca el proyecto y lo sube. Si decido cambiar alguna función, basta con cambiar el código local y ejecutar nuevamente esta parte. Siempre y cuando no agregue dependencias nuevas.

La salida muestra la URL base del sitio:
https://$APP.azurewebsites.net

Salida:

```powershell
Remote build succeeded!
[2025-10-15T04:04:15.538Z] Syncing triggers...
Functions in func-vision-pipeline-agm:
    enhance_focus - [activityTrigger]

    http_start - [httpTrigger]
        Invoke url: https://func-vision-pipeline-agm.azurewebsites.net/api/process

    orchestrator - [orchestrationTrigger]

    run_ocr - [activityTrigger]

    to_grayscale - [activityTrigger]
```

Ejecutar prueba remota:

```powershell
curl -X POST -H "Content-Type: application/octet-stream" --data-binary "@C:/Alvaro/dev/tfm-dev/azure/vision-pipeline/img/holaMundo.png" "https://func-vision-pipeline-agm.azurewebsites.net/api/process"
```

### Observaciones

En este proyecto, las funciones **enhance_focus**, **to_grayscale**, **run_ocr** y **orchestrator** no están expuestas a Internet, ya que utilizan bindings de tipo activityTrigger y orchestrationTrigger, siendo invocadas únicamente dentro del flujo interno de **Azure Durable Functions**. En cambio, la función http_start sí queda expuesta mediante un binding httpTrigger, y por defecto la hice pública (authLevel: "anonymous"), permitiendo ser llamada por cualquier cliente HTTP. Para restringir el acceso, se puede modificar el nivel de autorización a "function", de modo que ahora solo pueda invocarse incluyendo la function key en la URL.

#### Contenido de `http_start/function.json` para hacerlo privado

```json
{
  "bindings": [
    {
      "authLevel": "function",
      "type": "httpTrigger",
      "direction": "in",
      "name": "req",
      "methods": [ "post" ],
      "route": "process"
    },
    {
      "type": "http",
      "direction": "out",
      "name": "$return"
    },
    {
      "type": "orchestrationClient",
      "direction": "in",
      "name": "starter"
    }
  ],
  "scriptFile": "__init__.py"
}
```

Luego para invocarlo, hay que incluir la api key:

```powershell
curl -X POST -H "Content-Type: application/octet-stream" --data-binary "@C:/Alvaro/dev/tfm-dev/azure/vision-pipeline/img/holaMundo.png" "https://func-vision-pipeline-agm.azurewebsites.net/api/process?code=<MI_FUNCTION_KEY>"
```

**Durable Functions es una buena solución** para un pipeline de imagen disparado desde un frontend React cuando tenés **múltiples pasos secuenciales/condicionales**, necesitás **estado, reintentos y fan-out/fan-in** sin montar infraestructura. Aun así, lo mejor sería hacer estos **ajustes** para producción:

- **No subir binario por HTTP**: desde React subí la imagen a **Blob Storage** (put con **SAS** o vía API propia) y pasá **la URL/SAS** al orquestador. Evita timeouts y payloads grandes. 

- **Para devolver la imagen lo mismo**: Subír la imagen final a Azure Blob Storage desde la activity final (run_ocr o el orquestador). Retornar en el JSON solo la URL SAS temporal o el nombre del blob.

```json
{
  "ocrResult": {...},
  "processedImageUrl": "https://<storage>.blob.core.windows.net/results/img123.png?sv=..."
}

```

- **Desacople y seguridad**: poné `authLevel=function` o mejor **API Management** delante (rate limiting, keys/JWT, CORS). Si seguís anónimo, solo para pruebas.

- **Patrón async**: el `http_start` inicia la orquestación y devuelve `statusQueryGetUri`; React **polling** (o **SignalR/Web PubSub** para push) hasta “Completed”.

- **Escalado y latencia**: para OpenCV/CPU intensivo considera **Premium plan** (menos cold start) o mover las actividades a **Azure Container Apps Jobs** si crece la carga; si necesitás GPU, contenedores.

- **Observabilidad**: Application Insights (traces por step del orquestador), métricas por tasa de blur/errores OCR.

- **Robustez**: idempotencia por `instanceId`, reintentos por step, límites de tamaño, validación de formato.

### Cuándo lo haría distinto

- Si el flujo es **muy pesado o con SLAs de baja latencia**, usaría **Container Apps** + **Queue/Event Grid** (cada paso como microservicio) y un **coordinador** liviano.
- Si es un “if this then that” simple con conectores, **Logic Apps**.
- Si hay lotes masivos/offline, **Batch** o **Container Apps Jobs** programados.

Con tu caso (3–4 pasos de visión + OCR, respuesta en segundos), **Durable Functions encaja bien**; solo cambiaría la **ingesta** (Blob + URL) y **endurecería** auth/operativa.

## Implementación de storage

Toda Azure Function App necesita una Storage Account para colas, checkpoints y (en Durable) estado del orquestador. Cuando creaste la Function App, Azure te obligó a vincular una. Así que ya existe; solo hay que identificar cuál es.

Cómo identificar tu Storage Account (rápido)
Entrá a tu Function App (ej: func-vision-pipeline-agm).
Luego Settings -> Environment variables: AzureWebJobsStorage

DefaultEndpointsProtocol=https;EndpointSuffix=core.windows.net;AccountName=stvision109330379;AccountKey=RoD7FOl2OnIntuEb2FaTtgxuMKcgiVtdyqLL14A3rnFNLORXdwE+conpFAJajWI+j1yIaAfutbes+AStVcTsAQ==

De ahí obtengo: AccountName=stvision109330379.

Abrir powershell y ejecutar

```powershell
$RG="rg-vision-pipeline"
$STO="stvision109330379"

# Crear contenedores
az storage container create -n input  --account-name $STO --auth-mode login
az storage container create -n work   --account-name $STO --auth-mode login
az storage container create -n output --account-name $STO --auth-mode login

# (Opcional) Activar versionado y soft delete para seguridad
az storage account blob-service-properties update -g $RG -n $STO --enable-versioning true
az storage account blob-service-properties update -g $RG -n $STO --enable-delete-retention true --delete-retention-days 7

# Verificar
az storage container list --account-name $STO --auth-mode login -o table

```

Con esto Ya están creados input, work y output

Paso 2: preparar la Function App para usar Blob Storage (app settings + lib).

```powershell
# Definir variables para seguir
$RG="rg-vision-pipeline"
$APP="func-vision-pipeline-agm"
$STO="stvision109330379"
$BLOB_URL="https://$STO.blob.core.windows.net"

# Obtener una account key del storage
$KEY = az storage account keys list -g $RG -n $STO --query "[0].value" -o tsv

# Guardar en Application settings de la Function App
az functionapp config appsettings set -g $RG -n $APP --settings `
  BLOB_ACCOUNT_URL=$BLOB_URL `
  BLOB_ACCOUNT_KEY=$KEY
```
  
Quedan disponibles como variables de entorno BLOB_ACCOUNT_URL y BLOB_ACCOUNT_KEY.  

Agregar la librería de blobs al proyecto

En tu máquina (carpeta vision-pipeline, con el venv activo):

```powershell
cd C:\Alvaro\dev\tfm-dev\azure\vision-pipeline
.\.venv\Scripts\Activate.ps1
pip install azure-storage-blob
pip freeze > requirements.txt
```

Y republicar:

```powershell
func azure functionapp publish $APP
```

Paso 3 — Crear la función get_sas (emite URLs SAS temporales)

Esta función devuelve una URL SAS para que el frontend pueda:

subir un archivo directo al contenedor input (modo upload)

leer/descargar un archivo del contenedor output (modo read)

Seguridad: authLevel=function (requiere function key).
Usa las app settings que ya configuraste: BLOB_ACCOUNT_URL y BLOB_ACCOUNT_KEY.

SAS = Shared Access Signature (Firma de Acceso Compartido) en Azure Storage.

Es un token que agregás a una URL para delegar acceso temporal y limitado a un blob, contenedor o cuenta, sin exponer la account key.

```powershell
cd C:\Alvaro\dev\tfm-dev\azure\vision-pipeline
mkdir get_sas
cd get_sas
ni __init__.py -it file
ni function.json -it file
```

3.2 Código de get_sas/__init__.py

```python
import os, json, datetime
import azure.functions as func
from datetime import timedelta
from azure.storage.blob import generate_blob_sas, BlobSasPermissions

ACCOUNT_URL = os.environ["BLOB_ACCOUNT_URL"]   # p.ej. https://stvision109330379.blob.core.windows.net
ACCOUNT_KEY = os.environ["BLOB_ACCOUNT_KEY"]

def _account_name_from_url(url: str) -> str:
    # https://<account>.blob.core.windows.net -> <account>
    return url.split("//")[1].split(".")[0]

ACCOUNT_NAME = _account_name_from_url(ACCOUNT_URL)

def _make_upload_sas(container: str, blob_name: str, minutes: int, content_type: str | None) -> str:
    sas = generate_blob_sas(
        account_name=ACCOUNT_NAME,
        container_name=container,
        blob_name=blob_name,
        account_key=ACCOUNT_KEY,
        permission=BlobSasPermissions(write=True, create=True),
        expiry=datetime.datetime.utcnow() + timedelta(minutes=minutes),
        content_type=content_type or "application/octet-stream",
    )
    return f"{ACCOUNT_URL}/{container}/{blob_name}?{sas}"

def _make_read_sas(container: str, blob_name: str, minutes: int) -> str:
    sas = generate_blob_sas(
        account_name=ACCOUNT_NAME,
        container_name=container,
        blob_name=blob_name,
        account_key=ACCOUNT_KEY,
        permission=BlobSasPermissions(read=True),
        expiry=datetime.datetime.utcnow() + timedelta(minutes=minutes),
    )
    return f"{ACCOUNT_URL}/{container}/{blob_name}?{sas}"

def main(req: func.HttpRequest) -> func.HttpResponse:
    try:
        data = req.get_json()
    except Exception:
        return func.HttpResponse("Invalid JSON body", status_code=400)

    container   = data.get("container")   # "input" | "output"
    blob_name   = data.get("blobName")    # p.ej. "uploads/uuid.png"
    mode        = (data.get("mode") or "upload").lower()  # "upload" | "read"
    minutes     = int(data.get("minutes") or 10)
    content_type= data.get("contentType")  # opcional para upload

    # Política mínima: subir solo a input; leer solo de output.
    if mode == "upload" and container != "input":
        return func.HttpResponse("Uploads must target the 'input' container.", status_code=400)
    if mode == "read" and container not in ("output",):
        return func.HttpResponse("Reads are allowed only from the 'output' container.", status_code=400)
    if not blob_name:
        return func.HttpResponse("Missing 'blobName'.", status_code=400)

    if mode == "upload":
        url = _make_upload_sas(container, blob_name, minutes, content_type)
    elif mode == "read":
        url = _make_read_sas(container, blob_name, minutes)
    else:
        return func.HttpResponse("mode must be 'upload' or 'read'", status_code=400)

    return func.HttpResponse(
        json.dumps({"sasUrl": url}),
        status_code=200,
        mimetype="application/json"
    )

```

3.3 get_sas/function.json

```json
{
  "bindings": [
    {
      "authLevel": "function",
      "type": "httpTrigger",
      "direction": "in",
      "name": "req",
      "methods": ["post"],
      "route": "sas"
    },
    {
      "type": "http",
      "direction": "out",
      "name": "$return"
    }
  ],
  "scriptFile": "__init__.py"
}

```

3.4 Publicar

```powershell
cd C:\Alvaro\dev\tfm-dev\azure\vision-pipeline
.\.venv\Scripts\Activate.ps1
func azure functionapp publish func-vision-pipeline-agm

```

3.5 Probar (línea de comando)

Variables

```powershell
$RG="rg-vision-pipeline"
$APP="func-vision-pipeline-agm"
$UPLOAD_NAME="uploads/test-01.png"   # el nombre que quieras usar en input
```

Obtener function key

```powershell
$KEY = az functionapp function keys list -g $RG -n $APP --function-name get_sas --query "default" -o tsv
```

$KEY contiene:
_clxTopeBpw-dEUdRkQ3AtSY6tuIfTKTieNtYdT-z50sAzFuS0qStg==

Pedir SAS de upload (POST /api/sas)

```powershell
$BODY = '{ "container":"input", "blobName":"' + $UPLOAD_NAME + '", "mode":"upload", "minutes": 10, "contentType":"image/png" }'
curl -X POST -H "x-functions-key: $KEY" -H "Content-Type: application/json" -d $BODY https://$APP.azurewebsites.net/api/sas
```

La respuesta es:

```powershell
{"sasUrl": "https://stvision109330379.blob.core.windows.net/input/uploads/test-01.png?se=2025-10-16T18%3A53%3A59Z&sp=cw&sv=2025-11-05&sr=b&rsct=image/png&sig=aL3qF1scqES/kEHlOmIZ8Vh5FTF9awQqcKFo8Ri1QMM%3D"}
```

Subir el archivo usando la SAS URL

Reemplazá <SAS_URL> por el valor recibido.

```powershell
curl -X PUT -H "x-ms-blob-type: BlockBlob" --data-binary "@C:\ruta\a\tu\imagen.png" "<SAS_URL>"
```

En mi caso sería esto:

curl -X PUT -H "x-ms-blob-type: BlockBlob" --data-binary "@C:\Alvaro\dev\tfm-dev\azure\vision-pipeline\img\samplePicture.png" "https://stvision109330379.blob.core.windows.net/input/uploads/test-01.png?se=2025-10-16T18%3A53%3A59Z&sp=cw&sv=2025-11-05&sr=b&rsct=image/png&sig=aL3qF1scqES/kEHlOmIZ8Vh5FTF9awQqcKFo8Ri1QMM%3D"


Si devuelve 201 Created, quedó subido en input/uploads/test-01.png.

Puedo verificar por la consola de azure, yendo a storage accounts y buscar stvision109330379.
Luego Datastorage luego containers luego inputs luego uploads.

Con esto el frontend ya puede:

pedir SAS de upload para input/...,

subir directo al blob,

luego invocar tu starter pasándole { "container":"input", "blobName":"uploads/test-01.png" }.

Ya modifiqué todo el pipeline para que acepte trabajar con blobs.

Una vez hechos los cambios locales hago:

```powershell 
pip install azure-storage-blob opencv-python numpy requests
pip freeze > requirements.txt
func azure functionapp publish func-vision-pipeline-agm
```

Probar la ejecución completa

```powershell 
$RG="rg-vision-pipeline"
$APP="func-vision-pipeline-agm"
$KEY_START = az functionapp function keys list -g $RG -n $APP --function-name http_start --query "default" -o tsv

$BODY = '{ "container":"input", "blobName":"uploads/test-01.png" }'

curl -X POST -H "x-functions-key: $KEY_START" -H "Content-Type: application/json" -d $BODY `
"https://$APP.azurewebsites.net/api/process"
```


**Para probar un ciclo completo ejecutar scripts/text_pipeline.ps1**