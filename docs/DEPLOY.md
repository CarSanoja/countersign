# Despliegue en Cloud Run

## Antes de nada: qué se despliega hoy

La superficie HTTP es **solo el renderizador**. `api/dossier.py` no importa el runner —
lo dice su propio docstring — así que el servicio desplegado expone cinco rutas:

| Ruta | Qué hace | ¿Token? |
|---|---|---|
| `GET /healthz` | sonda de vida | no |
| `GET /` | redirige a `/demo` | no |
| `GET /demo` | el ejemplo empaquetado, renderizado | **sí** |
| `GET /demo.json` | el mismo ejemplo como datos | **sí** |
| `POST /dossier` | renderiza un `AssessmentResult` que le pasan en el cuerpo | **sí** |

De ahí se sigue algo que conviene decir en voz alta: **el servicio tal y como está hoy
necesita exactamente una variable**, `COUNTERSIGN_API_TOKEN`. No llama a Nutrient, ni a
SerpApi, ni a Vertex. La tabla de credenciales de proveedor de más abajo es la lista que
hará falta *cuando se conecte el runner*, no la que hace falta para que esto arranque.
Desplegarlo con las veinte variables puestas hoy no lo haría más capaz; solo pondría
veinte secretos en un sitio donde todavía no hacen nada.

## Requisitos previos

```bash
export PROJECT=<tu-proyecto>
export REGION=europe-west1
export REPO=countersign

gcloud services enable \
  run.googleapis.com \
  artifactregistry.googleapis.com \
  secretmanager.googleapis.com \
  aiplatform.googleapis.com \
  --project="$PROJECT"
```

## 1. La imagen

```bash
gcloud artifacts repositories create "$REPO" \
  --repository-format=docker --location="$REGION" --project="$PROJECT"

gcloud auth configure-docker "${REGION}-docker.pkg.dev"

export TAG=$(git rev-parse --short HEAD)
export IMAGE="${REGION}-docker.pkg.dev/${PROJECT}/${REPO}/api:${TAG}"

docker build --platform linux/amd64 -t "$IMAGE" .
docker push "$IMAGE"
```

`--platform linux/amd64` no es opcional desde un Mac con Apple Silicon: Cloud Run ejecuta
amd64, y una imagen arm64 subida sin más falla al arrancar la revisión con un error que no
menciona la arquitectura.

La etiqueta es el SHA del commit y no `:latest` a propósito. Una revisión de Cloud Run
guarda el digest, pero el registro de despliegues solo es legible si la etiqueta identifica
qué código se subió; con `:latest` la pregunta "qué había desplegado el martes" no tiene
respuesta.

## 2. Una cuenta de servicio propia para el runtime

```bash
gcloud iam service-accounts create countersign-run \
  --display-name="Countersign Cloud Run runtime" --project="$PROJECT"

export RUNTIME_SA="countersign-run@${PROJECT}.iam.gserviceaccount.com"

gcloud projects add-iam-policy-binding "$PROJECT" \
  --member="serviceAccount:${RUNTIME_SA}" \
  --role=roles/aiplatform.user
```

Cloud Run usa por defecto la cuenta de servicio de Compute Engine, que en muchos proyectos
sigue teniendo `roles/editor`. Un renderizador de HTML con permiso de editor sobre el
proyecto entero es una escalada de privilegios esperando a que alguien encuentre una
inyección en el dossier. La cuenta dedicada empieza sin nada y solo recibe lo que use.

## 3. Los secretos

```bash
printf '%s' "$(openssl rand -base64 32)" \
  | gcloud secrets create countersign-api-token --data-file=- --project="$PROJECT"

gcloud secrets add-iam-policy-binding countersign-api-token \
  --member="serviceAccount:${RUNTIME_SA}" \
  --role=roles/secretmanager.secretAccessor --project="$PROJECT"
```

`printf '%s'` en vez de `echo`: `echo` añade un salto de línea y ese salto forma parte del
secreto. `api/auth.py` hace `.strip()` sobre el valor leído precisamente por esto, así que
un secreto creado con `echo` seguiría funcionando — pero el que se apoya en nuestro
`strip()` para sobrevivir se rompe el día que alguien compare el token en otro sitio.

## 4. El despliegue

```bash
gcloud run deploy countersign \
  --image="$IMAGE" \
  --region="$REGION" \
  --project="$PROJECT" \
  --service-account="$RUNTIME_SA" \
  --allow-unauthenticated \
  --set-env-vars="GOOGLE_CLOUD_PROJECT=${PROJECT},GOOGLE_CLOUD_LOCATION=global,GOOGLE_GENAI_USE_VERTEXAI=True" \
  --set-secrets="COUNTERSIGN_API_TOKEN=countersign-api-token:latest" \
  --cpu=1 --memory=1Gi --concurrency=40 --max-instances=3 --timeout=300
```

No hace falta `--port`: Cloud Run inyecta `PORT=8080` y el `CMD` del Dockerfile lo expande.

`--max-instances=3` está puesto porque el proyecto GCP es de una persona y no de una
empresa. Sin cota, una ráfaga contra `/demo` escala hasta el límite de la región y la
factura la paga el dueño del proyecto.

`--allow-unauthenticated` es deliberado y no contradice el punto 3. Hay dos capas
distintas: IAM de Cloud Run decide quién puede *hablar con el servicio* y exige una
identidad de Google; nuestro token decide quién puede *leer un dossier*. Un jurado con un
enlace y un token no tiene cuenta en este proyecto GCP, así que la protección tiene que
vivir en la aplicación. Si el servicio deja de ser una demo, lo correcto es
`--no-allow-unauthenticated` **además** del token, no en su lugar.

### Comprobación después de desplegar

```bash
URL=$(gcloud run services describe countersign --region="$REGION" \
        --project="$PROJECT" --format='value(status.url)')

curl -s -o /dev/null -w '%{http_code}\n' "$URL/healthz"                       # 200
curl -s -o /dev/null -w '%{http_code}\n' "$URL/demo"                          # 401
curl -s -o /dev/null -w '%{http_code}\n' -H "Authorization: Bearer $TOKEN" \
     "$URL/demo"                                                              # 200
```

Un `503` en la segunda línea significa que `--set-secrets` no llegó: el servicio está vivo
y cerrado, que es como debe fallar.

## 5. Las variables de entorno

La lista sale de `orchestration/stages.py`, que es donde cada etapa declara la credencial
sin la que no puede correr. Una variable ausente **no** tumba el arranque: la etapa se
marca `skipped` con el nombre de la variable en el motivo, y la corrida sigue.

| Variable | Etapa | ¿Secreto? |
|---|---|---|
| `COUNTERSIGN_API_TOKEN` | la API entera | **sí** |
| `NUTRIENT_PROCESSOR_KEY` | ingest | **sí** |
| `SERPAPI_API_KEY` | identity | **sí** |
| `NAMECOM_USERNAME` | domain | no |
| `NAMECOM_TOKEN` | domain | **sí** |
| `DOCTAVIAN_API_KEY` *o* `FOXIT_PDF_CLIENT_ID` | generation | **sí** |
| `DOCTAVIAN_ACCESS_TOKEN` *o* `DOCTAVIAN_SERVICE_TOKEN` *o* `FOXIT_PDF_CLIENT_SECRET` | generation | **sí** |
| `FOXIT_ESIGN_ACCESS_TOKEN` *o* `FOXIT_ESIGN_CLIENT_ID` | delivery | **sí** |
| `FOXIT_ESIGN_ACCESS_TOKEN` *o* `FOXIT_ESIGN_CLIENT_SECRET` | delivery | **sí** |
| `XANO_TOKEN` | persistence | **sí** |
| `XANO_INSTANCE_DOMAIN` | persistence | no |
| `XANO_WORKSPACE_ID` | persistence | no |
| `XANO_AUDIT_TABLE_ID` | persistence | no |
| `GOOGLE_CLOUD_PROJECT` | ingest, identity, risk | no |
| `GOOGLE_CLOUD_LOCATION` | ingest, identity, risk | no |

Las que las alternativas separadas por *o* comparten fila son intercambiables: satisfacer
cualquiera satisface el requisito, tal y como lo modela `STAGE_CREDENTIALS`.

### Las que `stages.py` no vigila

Este es el sitio donde una lista copiada del `.env.example` engaña, así que van aparte.
Ninguna de estas aparece en `STAGE_CREDENTIALS`, de modo que la etapa **no** se marcará
`skipped` si faltan: fallará más adentro, o funcionará con un valor por defecto.

- `GOOGLE_GENAI_USE_VERTEXAI` — `risk_model.py` la exige en `REQUIRED_VARS` y
  `stages.py` no la comprueba. Sin ella, la etapa `risk` pasa el filtro de credenciales y
  luego revienta al llamar. Ponla a `True`.
- `NUTRIENT_DATA_EXTRACTION_KEY` — Extraction y Processor son **dos productos con claves y
  créditos separados** sobre el mismo host. `stages.py` solo mira la de Processor.
- `XANO_VENDOR_TABLE_ID` — la usan `baseline.py` y `baseline_store.py`; el filtro de la
  etapa `persistence` solo exige la tabla de auditoría.
- `DOCTAVIAN_BASE_URL`, `FOXIT_ESIGN_BASE_URL` — tienen valor por defecto en el cliente.
  Solo hacen falta para apuntar a un entorno distinto del de producción.

## 6. Por qué los secretos van en Secret Manager y no en variables del servicio

Es tentador meterlo todo en `--set-env-vars` y acabar antes. Las razones para no hacerlo no
son de estilo:

1. **Un valor en `--set-env-vars` es texto plano para cualquiera que pueda leer el
   servicio.** `gcloud run services describe` y la consola muestran el valor entero, y basta
   `roles/viewer` sobre el proyecto. Con `--set-secrets` lo que se ve es el nombre del
   secreto y la versión, no el contenido.
2. **Queda escrito en más sitios de los que uno controla.** El comando de despliegue vive en
   el historial del shell, en el log de la CI y en el registro de auditoría de admin. El
   secreto no se puede "desdecir" de ahí.
3. **Se queda en las revisiones viejas para siempre.** Cloud Run conserva las revisiones
   anteriores con su configuración. Un secreto puesto una vez como variable es recuperable
   desde una revisión de hace meses aunque el servicio actual ya no lo use.
4. **La rotación deja de ser un despliegue.** Con `:latest`, añadir una versión nueva del
   secreto y desplegar una revisión la recoge; la versión vieja se puede deshabilitar y
   dejar de servir. Con variables de entorno hay que reeditar y redesplegar cada servicio, y
   el valor antiguo sigue vivo en la revisión anterior.
5. **El acceso deja rastro.** Secret Manager registra cada acceso en Cloud Audit Logs: qué
   identidad leyó qué versión y cuándo. Una variable de entorno no tiene traza de lectura,
   así que después de un incidente no hay forma de saber si el secreto se usó.
6. **Se puede revocar.** Quitar `secretAccessor` a la cuenta de servicio hace que la
   siguiente revisión falle al arrancar — falla cerrada. Una variable ya inyectada en una
   revisión viva no se revoca; hay que redesplegar.

El criterio práctico: si el valor filtrado le da a alguien la capacidad de actuar en tu
nombre, va a Secret Manager. Si solo dice *dónde* está algo (`GOOGLE_CLOUD_PROJECT`,
`XANO_INSTANCE_DOMAIN`, una región), es configuración y va como variable.

## 7. Vertex no lleva fichero de clave

En Cloud Run, la cuenta de servicio del servicio *es* la credencial: `google-genai` la
recoge por Application Default Credentials sin que haya nada que montar. **No** generes un
JSON de cuenta de servicio ni lo metas en un secreto. Una clave descargada es un
credencial de larga vida que no caduca, no se rota sola y solo hace falta cuando no hay ADC
— que no es este caso.

Por eso `GOOGLE_CLOUD_PROJECT` y `GOOGLE_CLOUD_LOCATION` van como variables normales: dicen
a qué proyecto y a qué endpoint hablar, no autorizan nada. Quien autoriza es
`roles/aiplatform.user` sobre `$RUNTIME_SA`.

`GOOGLE_CLOUD_LOCATION=global` es lo que usamos en local para el endpoint global de Vertex.
Si lo cambias a una región, tiene que ser una donde el modelo de `risk_model.py` esté
disponible.

## 8. La consecuencia incómoda del token

Proteger las rutas del dossier rompe el gesto que `main.py` describe en su docstring: "un
jurado que pega la URL desnuda aterriza en el ejemplo". Ahora `/` sigue redirigiendo sin
token, pero `/demo` responde 401, y un navegador no manda cabecera `Authorization`.

Es un intercambio consciente: no hay forma de dejar `/demo` abierta sin dejar abierta la
ruta que mañana servirá expedientes reales, y las alternativas son peores — un `?token=` en
la URL acaba en los logs de acceso y en la cabecera `Referer`. Para enseñarlo:

```bash
curl -H "Authorization: Bearer $TOKEN" "$URL/demo" > dossier.html && open dossier.html
```

Si el demo en navegador es un requisito, la decisión correcta es una ruta de ejemplo
separada que sirva un fixture y **nunca** toque el renderizador de datos reales — no
quitarle el token a `/demo`.

## 9. Lo que no hemos probado

Honestidad sobre el alcance de esta guía: **nada de este documento se ha ejecutado contra
GCP.** El proyecto es del usuario, un despliegue cuesta dinero, y no se ha hecho.

Verificado de verdad, en local:

- `docker build` termina con éxito, en `linux/arm64` y en `linux/amd64`.
- El contenedor respeta `$PORT` (probado con `PORT=9090`).
- Corre como `uid=10001(countersign)`, no como root.
- Sin `COUNTERSIGN_API_TOKEN`: `/healthz` da 200 y `/demo` da 503 nombrando la variable.
- Con el token puesto: sin cabecera 401, con cabecera mala 401, con cabecera buena 200.
- Un secreto con salto de línea final sigue autenticando.
- El contexto de build solo contiene `pyproject.toml`, `README.md` y `src/`: cero ficheros
  de credenciales (comprobado listando el contexto dentro de una imagen desechable).

No verificado, y por tanto no prometido:

- Ningún comando `gcloud` de este documento se ha ejecutado. Los flags están transcritos de
  la documentación, no de una corrida.
- La imagen nunca se ha subido a Artifact Registry ni ha arrancado en Cloud Run.
- No sabemos el tiempo de arranque en frío. La imagen pesa ~100 MB y arrastra `google-adk`
  entero; el `import` de `google.genai` no es barato y `--min-instances=0` puede dar una
  primera petición lenta.
- Vertex nunca se ha llamado desde dentro del contenedor, así que la ruta de ADC en Cloud
  Run está razonada, no comprobada.
- `google-genai` llega **transitivamente** por `autocurricula` → `google-adk`; no está
  declarado en `pyproject.toml`. Si esa cadena cambia aguas arriba, la imagen se queda sin
  el SDK y las etapas de modelo fallan con "google-genai is not installed" sin que ningún
  test de este repo lo vea antes.
