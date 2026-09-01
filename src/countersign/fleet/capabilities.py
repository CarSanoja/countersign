"""The boundary between what the agent may do and what only a person may do.

The forbidden capabilities are declared here on purpose. They exist so that
every tool resolves to a capability and the gate can deny an attempt on the
record, rather than the attempt being impossible to express and therefore
impossible to audit.
"""

from enum import StrEnum


class CountersignCapability(StrEnum):
    DOC_EXTRACT = "doc.extract"
    WEB_SEARCH = "web.search"
    DOMAIN_QUERY = "domain.query"
    DOMAIN_REGISTER = "domain.register"
    DOC_GENERATE = "doc.generate"
    ENVELOPE_PREPARE = "envelope.prepare"
    BACKEND_PERSIST = "backend.persist"
    BACKEND_READ = "backend.read"
    ENVELOPE_READ = "envelope.read"
    PROVIDER_DIAGNOSE = "provider.diagnose"
    SIGNATURE_EXECUTE = "signature.execute"
    PAYMENT_RELEASE = "payment.release"


AGENT_CAPABILITIES: frozenset[str] = frozenset(
    {
        CountersignCapability.DOC_EXTRACT,
        CountersignCapability.WEB_SEARCH,
        CountersignCapability.DOMAIN_QUERY,
        CountersignCapability.DOC_GENERATE,
        CountersignCapability.ENVELOPE_PREPARE,
        CountersignCapability.BACKEND_PERSIST,
        CountersignCapability.BACKEND_READ,
        CountersignCapability.ENVELOPE_READ,
        CountersignCapability.PROVIDER_DIAGNOSE,
    }
)

HUMAN_ONLY_CAPABILITIES: frozenset[str] = frozenset(
    {
        CountersignCapability.SIGNATURE_EXECUTE,
        CountersignCapability.PAYMENT_RELEASE,
    }
)

APPROVAL_REQUIRED_CAPABILITIES: frozenset[str] = frozenset(
    {CountersignCapability.DOMAIN_REGISTER}
)

TOOL_CAPABILITY: dict[str, str] = {
    "nutrient_extract_fields": CountersignCapability.DOC_EXTRACT,
    "extract_invoice": CountersignCapability.DOC_EXTRACT,
    "fetch_layout": CountersignCapability.DOC_EXTRACT,
    "price_request": CountersignCapability.PROVIDER_DIAGNOSE,
    "nutrient_redact_pii": CountersignCapability.DOC_EXTRACT,
    "serpapi_find_official_site": CountersignCapability.WEB_SEARCH,
    "serpapi_adverse_media": CountersignCapability.WEB_SEARCH,
    "serpapi_verify_address": CountersignCapability.WEB_SEARCH,
    "namecom_hello": CountersignCapability.PROVIDER_DIAGNOSE,
    "namecom_account_balance": CountersignCapability.PROVIDER_DIAGNOSE,
    "namecom_check_availability": CountersignCapability.DOMAIN_QUERY,
    "namecom_list_records": CountersignCapability.DOMAIN_QUERY,
    "namecom_register_domain": CountersignCapability.DOMAIN_REGISTER,
    "namecom_create_txt_record": CountersignCapability.DOMAIN_REGISTER,
    "doctavian_generate_document": CountersignCapability.DOC_GENERATE,
    "foxit_generate_document": CountersignCapability.DOC_GENERATE,
    "foxit_prepare_envelope": CountersignCapability.ENVELOPE_PREPARE,
    "foxit_envelope_status": CountersignCapability.ENVELOPE_READ,
    "foxit_list_prepared_envelopes": CountersignCapability.ENVELOPE_READ,
    "foxit_execute_signature": CountersignCapability.SIGNATURE_EXECUTE,
    "xano_persist_vendor": CountersignCapability.BACKEND_PERSIST,
    "xano_append_audit": CountersignCapability.BACKEND_PERSIST,
    "read_audit_page": CountersignCapability.BACKEND_READ,
    "discover_instance_domain": CountersignCapability.PROVIDER_DIAGNOSE,
    "doctavian_check_credentials": CountersignCapability.PROVIDER_DIAGNOSE,
    "nutrient_credit_balance": CountersignCapability.PROVIDER_DIAGNOSE,
    "serpapi_account_quota": CountersignCapability.PROVIDER_DIAGNOSE,
    "release_payment": CountersignCapability.PAYMENT_RELEASE,
}


def capability_for_tool(tool: str) -> str | None:
    """Resolve a tool to its capability. An unmapped tool resolves to None so
    the gate fails closed instead of granting an unnamed power."""
    return TOOL_CAPABILITY.get(tool)


def is_human_only(capability: str) -> bool:
    return capability in HUMAN_ONLY_CAPABILITIES


def agent_holds(capability: str) -> bool:
    return capability in AGENT_CAPABILITIES
