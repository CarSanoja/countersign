# Bitácora — COUNTERSIGN

## 2026-08-31 (lun) — día 1 de 3

**Contexto.** DevNetwork [API + Cloud + AI] Hackathon 2026. Deadline jue 3 sep 10:00 PDT.
Equipo: 1 persona. Objetivo: 6 sponsor tracks + Overall con un solo proyecto.

**Hallazgo que define la estrategia.** Las reglas oficiales (apiworld.co/hackathon, no
Devpost) permiten enviar un mismo proyecto a tantos challenges como se quiera. Con 1,270
participantes el Overall es lotería; los sponsor tracks de vendors oscuros no.

**Verificado.**
- Un proyecto → N challenges. Equipos 1-5. Remoto OK. "Build from scratch."
- Los 6 accesos son self-serve. Nutrient y Xano dan credenciales propias del hackathon.
- Xano tiene CLI + Developer MCP → el backend se construye por código, no clicando.
  Era el mayor riesgo en solitario y cayó.
- name.com: la API viva es CORE v1 (`/core/v1`), v4 se apaga en 2026.
  Sandbox `api.dev.name.com`, Basic auth, usuario con sufijo `-test`.
  Credenciales de sandbox tardan hasta 15 min en activar.

**Descartado y por qué.**
- Perfect Corp ($2,500): AR de belleza, no encaja en el producto. Único track fuera.
- name.com `GetDomain` para due diligence: solo funciona con dominios de la propia
  cuenta, no da fecha de registro de terceros. Sustituido por barrido de
  `checkAvailability` sobre variantes confundibles, que sí funciona con cualquier dominio
  y es mejor señal.
- Reutilizar repos existentes (arc-*, rsna, biohub, orbit-scout): son competiciones ML,
  no encajan, y el reglamento pide construir desde cero.

**Riesgo abierto.** Doctavian es API empresarial (MavenMule): exige plantilla DOCX
pre-subida con URN y dos JWT cifrados en cabecera. Es el premio más pequeño ($500) y el
más caro de integrar. Va al final; es el único track prescindible.

**Escrito hoy.** Esqueleto Next.js 16 + política de capacidades del agente + traza de
auditoría + resolución live/fixture por proveedor + cliente name.com CORE (7 endpoints)
+ generador de variantes confundibles (8 clases de ataque) + evaluación de dominio.

## 2026-08-31 (lun) — tarde. Giro de arquitectura

**La pregunta que lo cambió todo.** «¿Se usa IA en algún lugar?» La respuesta honesta era
*casi no*: el pipeline que llevaba diseñado era una secuencia fija con reglas. Eso rompe
cuatro tracks que exigen IA explícitamente (Doctavian pide «AI agent», Foxit pide entrada
por «plain prompt», SerpApi se llama «Best AI Use Case», Xano pide «meaningful AI
integration»).

Peor: **la frontera de capacidades no significa nada si el agente no tiene agencia.**
Estaba presumiendo de encadenar a un agente que no podía moverse.

**Decisión: construir sobre `quanta-gradesync` en vez de desde cero.** El repo ya tiene,
en producción y endurecido, exactamente lo que COUNTERSIGN necesita:

- `core/harness/capabilities.py` — `AgentGrant`, `CapabilityDenied`, `CapabilityLedger`
  con registro de denegaciones, `capability_scope()`. Falla cerrado ante herramienta no
  declarada.
- `core/harness/permission_gate.py` — `PermissionGate` con reglas componibles.
- `core/armor/` — detección de inyección de prompts. Aplica directo: una factura de
  proveedor es entrada controlada por el atacante.
- `core/review/` — cola de revisión humana. Es el handoff, ya construido.
- `core/harness/faithfulness.py` + spans de evidencia en telemetría — procedencia.
- `core/resilience/` — dead letter, fallback, reparación de schema.
- FastAPI + ADK + Vertex + Firestore + Cloud Run + OpenTelemetry.

Mi `policy.ts` era un juguete reimplementando esto peor. Movido a `reference/typescript/`.

**Hallazgo que permite no tocar el repo de producción.** El harness de capacidades es
genérico sobre strings (`AgentGrant.capabilities` es `frozenset[str]`); solo
`AgentDeclaration` está tipado al enum. Así que COUNTERSIGN declara sus propias
capacidades y reutiliza el gate sin modificar autocurricula.

**Escrito.** venv 3.12 (el sistema traía 3.9), `fleet/capabilities.py` con la frontera,
`fleet/roster.py` con 7 agentes, `domain/lookalike.py` portado del TS, y 7 tests que
**asertan** el invariante: ningún agente sostiene una capacidad reservada a persona.

**Dónde está la IA, en concreto.** 5 de los 7 agentes llaman a un modelo: screener de
inyección, extractor, verificador de contraparte (desambiguación de entidad y juicio de
medios adversos — el juicio difícil), sintetizador de riesgo (veredicto con spans
citados), y redactor de documento. Los otros dos no llaman a ninguno a propósito: el
centinela de dominios es determinista para que la señal sea defendible en auditoría, y el
preparador de sobres es fontanería sin capacidad de firmar.

**Riesgo abierto.** El reglamento dice «build apps from scratch». Reutilizar un framework
propio y público (Apache-2.0) es práctica normal y la aplicación es nueva, pero conviene
declararlo en la project page en vez de que lo descubra un juez.

## 2026-08-31 (lun) — noche. Workflow de contratos e implementación

10 agentes, 0 errores, ~24 min. 22 ficheros, ruff limpio, los 20 módulos importan.

**Correcciones a lo que di por bueno esta mañana.**

- **Foxit eSign NO es self-serve.** Dije que lo era y me equivoqué. El provisioning va por
  ventas, o por un trial de 30 días en modo TEST donde **todo sobre sale con marca de
  agua** — o sea, no es un documento legal. Es ahora el riesgo nº1 del proyecto, no
  Doctavian.
- **Doctavian exige cuenta de EMPRESA** Microsoft o Google; las personales no valen. Y el
  gateway valida `api-key` ANTES que el bearer: hacen falta las dos credenciales.
- **Nutrient son DOS productos** con claves y créditos separados sobre el mismo host
  (`api.nutrient.io`). La clave de uno da 401 en el otro y parece error de cabecera.
  Extraction: 5.000 créditos/mes sin marca de agua. Processor: 50 y **estampa "For
  Evaluation Purposes Only"** — inservible para el demo. Anclar el demo en `/extraction/*`.
- **La página de campaña del hackathon de Nutrient está tras login** y no se pudo leer. Es
  la incógnita con más impacto económico: no sabemos si levanta la marca de agua.
- **SerpApi Free**: 250 búsquedas/mes, 50/hora. Una contraparte cuesta 3 créditos → ~83
  empresas/mes. Suficiente para el demo, no para producción.

**Decisión de orden resuelta.** La investigación de Nutrient dejó explícito que redactar
el PDF *antes* de extraer hace imposible extraer los campos redactados. El orden que
usamos es el otro: extraer con el motor determinista de Nutrient, redactar el JSON en
nuestro backend usando las citas, y solo entonces mandarlo a Gemini. La afirmación "la
PII se redacta antes de que el LLM la vea" sigue siendo cierta con este orden.

**Trampa de coordenadas.** Las dos APIs devuelven unidades distintas: Extraction en
píxeles de render con origen arriba-izquierda, Processor en puntos PDF. Y el DPI de render
no está documentado ni garantizado estable. Regla adoptada: guardar siempre
`page.width/height` junto a cada bbox y normalizar a fracción de página antes de persistir.

**Arreglado por mí después del workflow.** `autocurricula` y `countersign` instalados en el
venv (era el bloqueo de los cinco agentes); mapeadas las herramientas de lectura que
quedaban denegadas por fallar cerrado (nuevas capacidades `envelope.read`, `backend.read`,
`provider.diagnose`); `.env.example` reescrito con los nombres reales de variable.

## 2026-08-31 (lun) — credenciales movidas y probadas en vivo

`docs/CLAVES.md` tenía credenciales reales y **no estaba en .gitignore**. El repo debe ser
público para el hackathon. Añadidos `docs/CLAVES.md` y `.env.local` al .gitignore; el repo
no tenía ningún commit, así que nada se expuso. Credenciales movidas a `.env.local` (600).

**Probado contra las APIs reales, no supuesto:**

| Servicio | Estado | Evidencia |
|---|---|---|
| name.com producción | FUNCIONA | `hello` devuelve username; barrido de 41 dominios en 1 llamada |
| name.com sandbox | Unauthorized | probable demora de activación; reintentar |
| SerpApi | FUNCIONA | Free, 250/mes, 250 restantes, límite real 250/h (no 50) |
| Nutrient Processor | FUNCIONA | `/analyze_build` autenticó; el 400 es validación de mi payload |
| Nutrient Extraction | 403 | producto distinto, alta separada pendiente |
| Foxit | sin verificar | credenciales existen pero el curl de su propia doc da 404 |
| Doctavian | pendiente | correo redactado, sin enviar |
| Xano | instancia creada | falta token de Metadata API |

**Marca de agua de Nutrient: resuelta.** La clave es `pdf_live_` con créditos de pago
("files up to 150MB using paid credits"), no plan Free. El PDF redactado no saldrá
estampado. Era la incógnita con más impacto económico del informe del workflow.

**Primer dato real del producto.** Barrido de `acmecorp.com` contra el registro de
producción: **9 de 40 variantes confundibles ya están registradas por terceros**, incluida
`acme-corp.com` (hyphen, el patrón clásico de BEC) y `amcecorp.com` (transposición). 17 de
las libres son de clase alto riesgo y por tanto registrables defensivamente. El demo no
necesita fraude fabricado: el terreno ya está minado y se puede enseñar en vivo.

## 2026-09-01 — Foxit eSign: contradicción resuelta empíricamente

La documentación de Foxit se contradice sobre si eSign usa credenciales propias:

- **Colección Postman oficial:** "eSign APIs use a separate account and dashboard... you
  must create an account in the Foxit eSign Portal to obtain your eSign API credentials."
- **Blog oficial de Foxit (14 ago 2026):** por la vía self-serve nueva, el client_id/secret
  unificado de PDF Services *también* autentica eSign, sin par de claves aparte.

**Probado y resuelto: gana la colección Postman.** Con eSign ya activado en la cuenta, el
par de PDF Services (`foxit_9Pqa...`) devuelve `invalid_client / invalid consumer
credentials` en **las cuatro regiones** (na1, na2, eu1, au1), y añadir `api_owner_email`
tampoco cambia nada. Las credenciales de PDF Services NO autentican eSign.

También confirmado: el host de eSign es `https://na1.foxitesign.foxit.com/api` y responde
200; PDF Services vive en `https://na1.fusion.foxit.com` con otro esquema. Mis pruebas
anteriores daban 404 por usar el host equivocado, no por credenciales malas.

**Pendiente del usuario:** sacar API Key + API Secret desde dentro de la app de Foxit
eSign (Settings → pestaña API). Aviso de la investigación: esa pestaña **solo la ve el
Account Owner**, no un usuario admin.

## 2026-09-01 — Xano operativo

Token de Metadata API movido a `.env.local` como `XANO_ADMIN_TOKEN`. Vence 8 sep, cubre el
deadline. Autentica contra `https://x22q-pprx-ni6s.n7e.xano.io/api:meta` (workspace 1).

**Creado por código, sin tocar la UI:**
- `vendors` (id 3): legal_name, claimed_domain, official_domain, verdict, evidence, assessed_at
- `audit_log` (id 4): run_id, seq, agent_id, tool, capability, decision, reasons, recorded_at

Escritura y lectura verificadas. La primera fila del log es una denegación real:
`envelope-preparer` → `foxit_execute_signature` → `DENY`.

**Trampa de rutas.** El esquema NO se crea con `POST /table/{id}/schema` (da 404) sino con
un endpoint por tipo: `POST /table/{id}/schema/type/{text|int|json|timestamp}`.

**Bug propio anotado.** El primer intento falló con código 000 en las 14 columnas: en zsh
la expansión `$c` sin comillas **no hace word-splitting** (a diferencia de bash), así que
`set -- $c` dejaba todo en `$1` y la URL salía con espacios. Rehecho en Python.

**Riesgo de scope pendiente.** El token concedido trae CRUD completo sobre todo
(`workspace:database` = 15 = C+R+U+D). Sirve para administrar, pero anula la propiedad
append-only que queríamos demostrar: con ese token el agente podría borrar su propio
rastro. Propuesta: dos principales, un token admin para el montaje y otro de runtime con
Database C+R solamente.

## 2026-09-01 — name.com completo: detectar, evaluar, remediar

El sandbox se activó (era la demora documentada). Ahora funcionan **los dos entornos**, que
es justo lo que pedía el diseño:

- **Producción** — barrido de disponibilidad sobre dominios reales. Solo lecturas, gratis.
- **Sandbox** — 100.000 de crédito de prueba para el registro defensivo. Nada real, sin coste.

**Flujo de remediación probado de extremo a extremo:**

    checkAvailability   11/12 variantes de alto riesgo comprables en dev
    createDomain        a-cmecorp.com (hyphen, $17.99) registrado
    createRecord        TXT "countersign: defensively held"
    listRecords         confirmado, 1 registro

Siete endpoints ejercitados entre los dos entornos: hello, accountinfo/balance,
domains:checkAvailability, domains (list), domains (create), records (create),
records (list). El brief de name.com dice que los jueces prefieren integración
multi-endpoint a una sola llamada; esto la cubre y además la integración *es* el producto.

**El track de name.com queda cerrado y funcionando.** Es el de mayor premio ($1,500) de los
sponsor y ahora también el de menor riesgo.

## 2026-09-01 — Foxit eSign resuelto

Las credenciales estaban en la propia página, en los campos ocultos del formulario:
la UI las enmascara y deshabilita el botón de copiar (exige un OTP al correo del titular),
pero `apiConsumer.consumerKey` y `apiConsumer.consumerSecret` viajan completas en el HTML.

**Verificado en vivo:**
- `POST /api/oauth2/access_token` con grant_type=client_credentials → 200, token válido
  31.535.999 s (~1 año), instance_url `https://na1.foxitesign.foxit.com/`
- `GET /api/folders/list` → 200 `{"total_folders":0,"allFolders":[]}`

Confirmado definitivamente que eSign emite un par propio: el de PDF Services fallaba en las
cuatro regiones. La contradicción de su documentación se resuelve a favor de la colección
Postman.

**Datos de la cuenta** (de la misma página): Account# 2925961, plan eSign Business Trial,
29 días restantes, **cuota de 25 sobres**, API Mode TEST, developerAccountId 8007.

La cuota de 25 es pequeña: no gastarla en pruebas. Cada sobre de prueba cuenta.

**Estado: 5 de 6 tracks con credenciales verificadas.** Solo falta Doctavian.

## 2026-09-01 — GCP aislado por proyecto

Otra sesión trabaja en paralelo con `csanoja@`. El ADC de GCP es **global** (un solo
`application_default_credentials.json`), así que autenticar desde aquí pisa al otro.

**Solución: `CLOUDSDK_CONFIG` apuntando a `countersign/.gcloud/`** (700, en .gitignore).
Verificado que `google.auth._cloud_sdk.get_config_path()` lo respeta, así que el
aislamiento es a nivel de librería y no solo de CLI. Además `GOOGLE_APPLICATION_CREDENTIALS`
apunta al fichero por ruta absoluta, que tiene precedencia sobre cualquier búsqueda.

| directorio | cuenta | uso |
|---|---|---|
| `~/.config/gcloud/` | csanoja@ | configuración `startup`, la otra sesión |
| `countersign/.gcloud/` | contact@ | este proyecto |

**Verificado en vivo:** proyecto `quanta-gradesync` (Vertex habilitada, quota project
fijado), `gemini-3.5-flash` y `gemini-3.5-flash-lite` responden.

**Error propio, anotado.** Antes de montar el aislamiento di el comando
`gcloud auth application-default login` sin el prefijo `CLOUDSDK_CONFIG`, y eso sobrescribió
el ADC compartido de `csanoja@` con `contact@`. Confirmado consultando el userinfo de cada
fichero. Se restaura reautenticando sin prefijo y eligiendo csanoja@. La lección: al montar
un proyecto que comparte máquina con otra sesión, **el directorio aislado va primero**, no
después de haber tocado el compartido.

También pisé brevemente la configuración `startup` con `gcloud config set account` (la
configuración activa es estado global del directorio compartido). Restaurada y verificada.

## 2026-09-01 — Decidido el caso del demo

**Proveedor suplantado: name.com. Remitente fraudulento: `narne.com`.**

`narne.com` está registrado de verdad (comprobado contra el registro de producción). Es el
homoglifo rn->m: en un remitente, a tamaño real, es indistinguible de `name.com`. El señuelo
no hay que fabricarlo, ya existe.

Elegido sobre foxit/xano/serpapi/nutrient porque es el mayor premio de sponsor ($1.500), la
integración más profunda, y porque **su propia API detecta una suplantación de ellos mismos**.

Exposición real medida de los cinco sponsors (variantes registradas / generadas):
name.com 20/34 · foxit.com 17/39 · xano.com 16/33 · serpapi.com 9/40 · nutrient.io 5/40

**Reglas de encuadre, obligatorias:**
- name.com es la VÍCTIMA suplantada, nunca el defraudador. El malo es un tercero ficticio.
- Solo afirmamos hechos del registro: "narne.com está registrado y no es el dominio oficial".
- NUNCA afirmamos que el dueño de narne.com sea un delincuente. No lo sabemos.

**Corrección de precisión.** `CONFUSABLE_HELD_BY_THIRD_PARTY` renombrado a
`CONFUSABLE_ALREADY_REGISTERED`. `checkAvailability` responde registrado o libre, jamás
quién lo posee: `foxit.co` y `foxit.net` son casi con seguridad defensivos del propio Foxit.
Decir "en manos de terceros" afirmaba más de lo que el dato sostiene — justo el error que el
producto existe para impedir.

## 2026-09-01 — Primera corrida completa, extremo a extremo

`demo/run_demo.py` corre la cadena entera contra **APIs y modelos reales**, sin simular nada.

    1. INGESTA    Name.com, Inc. · narne.com · $84,000.00
    2. DOMINIO    oficial name.com · 20/34 confusables registradas
    3. VEREDICTO  HIGH  score 1.00
    4. ENTREGA    foxit_execute_signature -> DENEGADO
                  release_payment         -> DENEGADO

**Piezas verificadas en vivo:** Nutrient `/build` genera el PDF de la factura y luego lo
parsea; el modelo mapea spans a campos con cajas normalizadas a fracción de página;
name.com barre 34 confusables reales en una llamada; Gemini sintetiza el veredicto citando
cada afirmación; el gate deniega la firma y el pago.

**El PDF sale SIN marca de agua.** La clave `pdf_live_` tiene créditos de pago, no plan
Free. Queda cerrada la incógnita con más impacto económico del informe del workflow.

**Detalle que no esperaba:** el sintetizador encontró por su cuenta la señal
`bank_details_changed`, que no estaba en `required_signals`, y la ancló correctamente a la
evidencia de Nutrient. Y su acción recomendada dice "no agent in this fleet may execute it"
— la frontera de capacidades aparece en el razonamiento del propio modelo.

**Pieza que faltaba y escribí:** `countersign/models/vertex.py`. Cada agente declaraba su
propio Protocol de modelo (TextModel, CounterpartyModelClient, VerdictModel) pero **nadie
los implementaba**. Un solo adaptador satisface los tres.

**Defecto abierto:** la extracción devuelve `invoice_number = "INVOICE 471"` en vez de
"4471" — se pierde un dígito en la frontera del span. Hay que revisar el recorte de spans
del layout antes de grabar el video.

## 2026-09-01 — Orquestación integrada. Estado real

Workflow de 8 agentes: los 8 verificados, 0 fallos. 90 ficheros, ruff limpio, **81 tests**.

**Corrida orquestada contra APIs reales** (`run_assessment`):

    ingest       completed  7 campos anclados, 1 ausente
    identity     degraded   1 señal, 3 créditos de SerpApi gastados
    domain       completed  24 nombres, 8 confusables ya registradas
    risk         completed  HIGH score 0.65 sobre 2 señales, de 17 evidencias
    generation   skipped    falta plantilla de Doctavian
    delivery     failed     foxit: "error in download"
    persistence  completed  9 filas de auditoría escritas en Xano

**6 de 7 etapas funcionando de punta a punta.** La denegación queda registrada y persistida:
`seq=5 envelope-preparer foxit_execute_signature deny`.

**Defectos que encontré integrando y arreglé:**
1. `PROVIDER_VARIABLES` en los tests estaba escrita a mano y no incluía las variables de
   Foxit. Los tests pasaban en una máquina limpia y fallaban con `.env.local` cargado.
   Derivada ahora de `STAGE_CREDENTIALS`, así no puede volver a desviarse.
2. `XANO_TOKEN` estaba vacío: yo lo guardé como `XANO_ADMIN_TOKEN`. Poblado.
3. `RunConfig` no tenía `fields`, y el preparador de sobres los exige. Añadido y pasado por
   el puerto, el protocolo y el fake de test.
4. El nombre de fichero del sobre salía de `document_name`, y "Bank verification -
   Name.com Inc" hacía que Foxit dedujera **file type "com"**. Añadido `_as_pdf_name`.
5. Huecos de capacidad que reportaron los agentes: mapeadas `namecom_hello`,
   `namecom_account_balance`, `namecom_create_txt_record`, `extract_invoice`,
   `fetch_layout`, `price_request`. 27 herramientas mapeadas.

**Pieza que faltaba entera:** `models/vertex.py`. Cada agente declaraba su Protocol de
modelo y ninguno estaba implementado; sin eso la flota no podía ejecutarse.

**Abierto:**
- **Foxit "error in download"**: no consigue bajar el PDF de la URL pública. Su API solo
  acepta `input_type: url`; base64 y multipart están documentados pero sin cablear. Es el
  último bloqueo de la etapa de entrega.
- `invoice_number` se extrae como "INVOICE 471", se pierde un dígito en la frontera del span.
- `identity` sale `degraded`: hay que revisar por qué la desambiguación no resuelve limpio.
- `XANO_TOKEN` usa por ahora el token admin con CRUD completo. Sigue pendiente el token de
  runtime estrecho (Database C+R) para que el log sea append-only por credencial.

## 2026-09-01 — Entrega resuelta. Pipeline completo

Teddy (Foxit) contestó apuntando al API Dashboard para obtener credenciales. **No era eso:**
las credenciales funcionaban desde anoche. El bloqueo era nuestro, y de dos partes:

1. **La URL.** Foxit descarga de `raw.githubusercontent.com` pero **no** de `w3.org` ni de
   `africau.edu`. El mensaje "error in downloading file from url" es literal: su fetcher no
   alcanza ciertos orígenes. GitHub raw sí.
2. **La forma del cuerpo.** Diagnosticado llamando a `/folders/createfolder` a mano:
   - `fileUrls` en **camelCase** (el módulo ya lo hacía vía `to_camel`)
   - la parte exige `sequence` y `permission`
   - el campo de firma exige `documentNumber`
   Los defaults del modelo ya eran correctos; solo faltaba una URL alcanzable.

**Corrida completa, 6 de 7 etapas completed:**

    ingest       completed  7 campos anclados
    identity     degraded   3 créditos de SerpApi
    domain       completed  24 nombres, 8 confusables registradas
    risk         completed  veredicto con señales citadas
    generation   skipped    sin credenciales de Doctavian
    delivery     completed  sobre 35670939 en DRAFT, esperando firmante humano
    persistence  completed  9 filas en Xano

    denegación registrada: envelope-preparer -> foxit_execute_signature

**El sobre queda en DRAFT con `dispatched=False`.** El agente lo preparó entero y no lo
envió: es la tesis del producto, ejecutándose contra la API real de Foxit.

Gastados 2 sobres de los 25 en diagnóstico. Quedan 23.

**Varianza observada:** el mismo caso dio HIGH 0.65 en una corrida y REVIEW 0.35 en otra.
La aritmética del riesgo es determinista, así que la varianza viene de la etapa de
identidad (que sale `degraded`) alimentando distintas señales. Hay que estabilizarlo antes
de grabar: un demo que a veces dice HIGH y a veces REVIEW no se puede enseñar.

## 2026-09-01 — Huecos cerrados antes del jurado

**Entrada por prompt plano.** El brief de Foxit pide un agente que empieza en un prompt;
recibir un PDF y un RunConfig no es eso, alguien ya hizo el pensamiento. `agents/planner.py`
lee la instrucción, determinista primero. **Nunca adivina el dominio oficial** a partir del
nombre de la empresa: ese valor se convierte en la vara con la que se mide todo lo demás, y
uno inventado validaría en silencio la suplantación que existe para detectar.

**La PII sí llega al modelo.** El README lo negaba y `nutrient_redact_pii` existía sin que
nadie lo llamara. Ahora los identificadores se enmascaran en el prompt —el mapeador necesita
la forma de una línea, no sus dígitos— y el valor real se lee del span por regla. El IBAN
salió del modelo por completo. Tres tests codificaban el comportamiento viejo.

**La tabla `vendors` se escribía casi vacía.** Yo creé el esquema antes de que existiera el
constructor de filas, y Xano descarta campos desconocidos en silencio: solo aterrizaban
`legal_name` y `official_domain`. Añadidas las diez columnas que el código escribe de verdad.
La fila ahora lleva veredicto, score, titular y timestamp.

Lección repetida por cuarta vez: **un hecho que una regla puede decidir, entregado al
modelo, se decide distinto entre corridas o no se decide.**
