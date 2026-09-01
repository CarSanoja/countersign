# Arquitectura

## La afirmación central

El agente hace todo el papeleo y **es estructuralmente incapaz de firmar o de pagar**. No
es una promesa del prompt: es una lista de capacidades comprobada en
`src/countersign/fleet/capabilities.py`. Una herramienta que no está declarada resuelve a
`None` y se deniega, de modo que la puerta **falla cerrada** en vez de conceder un poder
sin nombre.

`tests/test_boundary.py` falla si alguien concede alguna vez a un agente el poder de
firmar.

## Etapas, y quién hace cada una

| Etapa | Módulo | Proveedor | Qué hace |
|---|---|---|---|
| ingest | `agents/document_extractor*.py` | Nutrient DWS | parse determinista; el modelo solo mapea spans existentes a campos con nombre |
| identity | `agents/counterparty_*.py` | SerpApi | desambigua la entidad antes de leer si la cobertura es adversa |
| domain | `agents/domain_sentinel*.py` | name.com | barrido de confusables en ocho clases de ataque |
| risk | `agents/risk_*.py` | — | funde la evidencia; rechaza un veredicto cuya afirmación no cite su span |
| generation | `tools/doctavian*.py` | Doctavian | redacta la verificación bancaria fuera de banda |
| delivery | `agents/envelope_preparer.py` | Foxit eSign | prepara el sobre y **se detiene** |
| persistence | `tools/xano.py` | Xano | proveedores, estado del flujo y log de auditoría |

La orquestación vive en `src/countersign/orchestration/`: `pipeline.py` encadena las
etapas, `gate.py` autoriza cada llamada a herramienta, `evidence.py` construye el paquete
de evidencia y `stages.py` declara qué credencial necesita cada etapa.

## Lo que se decide por regla, y por qué

Cuatro veces durante la construcción el mismo defecto apareció disfrazado: **un hecho que
una regla podía decidir se dejó al modelo, y se decidió distinto entre corridas o no se
decidió**. Estos ya no pasan por un modelo:

- **el dominio del remitente** — lo que sigue al `@`, y un correo pesa más que un logo
- **el cambio de datos bancarios** — el documento lo anuncia con palabras
- **el IBAN** — tiene forma definida, así que lo lee un regex y ningún modelo lo toca
- **la comparación remitente contra oficial** — es una comparación de cadenas

Las señales así establecidas viajan con el paquete de evidencia y **tienen precedencia**
sobre el borrador del modelo, que puede añadir tipos pero no puede quitar los ya resueltos.

## Procedencia

`schemas/evidence.PageBox` guarda **fracciones de página**, validadas a 0..1. Los dos
productos de Nutrient reportan en unidades distintas —píxeles de render y puntos PDF— y el
DPI no está documentado ni garantizado estable, así que una caja absoluta guardada es un
bug esperando otro tamaño de página.

`Claim` exige al menos una `SourceRef`. Un `Verdict` de nivel alto sin señales se rechaza
en construcción.

## PII

El mapeador dice qué span contiene qué campo, y para eso necesita la forma de una línea,
no sus dígitos. `agents/pii_mask.py` enmascara IBAN, BIC, identificadores fiscales y el
buzón de los correos —conservando el dominio, que es la señal— antes de construir el
prompt. El valor real se lee del span después. Ningún identificador de cuenta entra jamás
en el contexto de un modelo.

## Degradación por proveedor

Cada etapa declara sus variables de entorno en `orchestration/stages.py`. Si falta una, la
etapa se registra como omitida nombrando la variable y la corrida continúa. Una clave que
no llega cuesta una etapa, nunca la corrida.

## Cómo verlo correr

    .venv/bin/python demo/run_demo.py            # el pipeline completo
    .venv/bin/python demo/run_from_prompt.py     # lo mismo desde una instrucción
    .venv/bin/python demo/benchmark/measure.py   # el conjunto etiquetado
