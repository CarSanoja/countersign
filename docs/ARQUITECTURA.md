# Arquitectura

## La afirmación central

El agente hace todo el papeleo y **es estructuralmente incapaz de firmar**. No es una
promesa del prompt: es una lista de capacidades que se comprueba en código
(`src/agent/policy.ts`). `execute_signature` y `release_payment` están reservadas a un
principal humano, y cualquier intento del agente lanza `CapabilityDenied`, que la traza
registra como paso `denied` en vez de ocultarlo.

Esto es exactamente lo que pide el challenge de Foxit ("agents should not auto-sign;
demonstrate thoughtful handoff") y lo que pide Nutrient ("human-in-the-loop").

## Etapas y reparto por sponsor

| Etapa | Módulo | Proveedor | Qué hace |
|---|---|---|---|
| ingest | `src/ingest` | Nutrient DWS | parse/OCR/extracción determinista con procedencia; redacta PII antes del LLM |
| identity | `src/identity` | SerpApi | verifica que la contraparte existe: sitio oficial, dirección, litigios |
| domain | `src/domain-intel` | name.com CORE | barrido de variantes confundibles; cuáles ya están registradas |
| risk | `src/risk` | — | funde las señales en un veredicto con procedencia |
| generate | `src/generate` | Doctavian | produce el contradocumento desde datos estructurados |
| handoff | `src/sign` | Foxit eSign | prepara el sobre; la firma la ejecuta un humano |
| persistencia | `src/backend` | Xano | proveedores, estado del flujo y log de auditoría |

## Modo live / fixture

Cada proveedor declara sus variables en `src/lib/env.ts`. Si faltan, ese proveedor corre
en `fixture` y el resto del pipeline sigue funcionando. Con 3 días y 6 claves, esto
significa que una clave que no llegue tumba **un track, no el demo**.

## Por qué el barrido de dominios es la señal, y no el whois

`GetDomain` de name.com solo responde por dominios de la propia cuenta, así que no sirve
para due diligence de un tercero. `checkAvailability` sí responde por cualquier dominio,
y la pregunta que de verdad importa en fraude de proveedor no es "cuándo se registró
esto" sino **"¿quién posee ya las variantes confundibles del dominio real de mi
proveedor?"**. Un `acrnecorp.com` (rn→m) registrado por un tercero es una suplantación
armada y esperando.

Se generan 8 clases de ataque —tld-swap, hyphen, omission, doubling, transposition,
homoglyph, adjacent-key, suffix— repartidas en cuotas para que el barrido no se agote en
una sola clase. 40 variantes entran en una llamada (el límite es 50).
