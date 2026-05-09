"""Declarative provider registry and lookup."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from axiom.providers import connectors, llm, oauth
from axiom.providers.errors import UnknownProvider
from axiom.providers.models import CredentialField, ProviderMetadata, VerifyResult

VerifyFn = Callable[[str | dict], VerifyResult]


@dataclass(frozen=True, slots=True)
class ProviderRecord:
    meta: ProviderMetadata
    verify_key: VerifyFn


_REGISTRY: dict[str, ProviderRecord]


def _shape_api_key(label: str = "API Key") -> tuple[CredentialField, ...]:
    return (CredentialField(name="api_key", label=label, secret=True),)


def _shape_oauth() -> tuple[CredentialField, ...]:
    return (
        CredentialField(name="client_id", label="Client ID", secret=False),
        CredentialField(name="client_secret", label="Client Secret", secret=True),
    )


def _build_registry() -> dict[str, ProviderRecord]:
    items: list[ProviderRecord] = [
        ProviderRecord(
            meta=ProviderMetadata(
                id="anthropic",
                display_name="Anthropic",
                kind="llm",
                credential_shape=_shape_api_key(),
                docs_url="https://docs.anthropic.com/en/api/getting-started",
                verify_endpoint="POST https://api.anthropic.com/v1/messages",
            ),
            verify_key=llm.verify_anthropic_key,
        ),
        ProviderRecord(
            meta=ProviderMetadata(
                id="openai",
                display_name="OpenAI",
                kind="llm",
                credential_shape=_shape_api_key(),
                docs_url="https://platform.openai.com/docs/api-reference",
                verify_endpoint="GET https://api.openai.com/v1/models",
            ),
            verify_key=llm.verify_openai_key,
        ),
        ProviderRecord(
            meta=ProviderMetadata(
                id="mistral",
                display_name="Mistral AI",
                kind="llm",
                credential_shape=_shape_api_key(),
                docs_url="https://docs.mistral.ai/api/",
                verify_endpoint="GET https://api.mistral.ai/v1/models",
            ),
            verify_key=llm.verify_mistral_key,
        ),
        ProviderRecord(
            meta=ProviderMetadata(
                id="groq",
                display_name="Groq",
                kind="llm",
                credential_shape=_shape_api_key(),
                docs_url="https://console.groq.com/docs/quickstart",
                verify_endpoint="GET https://api.groq.com/openai/v1/models",
            ),
            verify_key=llm.verify_groq_key,
        ),
        ProviderRecord(
            meta=ProviderMetadata(
                id="github",
                display_name="GitHub",
                kind="connector",
                credential_shape=_shape_api_key("Personal access token"),
                docs_url="https://docs.github.com/en/rest",
                verify_endpoint="GET https://api.github.com/user",
            ),
            verify_key=connectors.verify_github_key,
        ),
        ProviderRecord(
            meta=ProviderMetadata(
                id="linear",
                display_name="Linear",
                kind="connector",
                credential_shape=_shape_api_key("API key"),
                docs_url="https://developers.linear.app/docs/graphql/working-with-the-graphql-api",
                verify_endpoint="POST https://api.linear.app/graphql viewer{id}",
            ),
            verify_key=connectors.verify_linear_key,
        ),
        ProviderRecord(
            meta=ProviderMetadata(
                id="notion",
                display_name="Notion",
                kind="connector",
                credential_shape=_shape_api_key("Integration token"),
                docs_url="https://developers.notion.com/reference",
                verify_endpoint="GET https://api.notion.com/v1/users/me",
            ),
            verify_key=connectors.verify_notion_key,
        ),
        ProviderRecord(
            meta=ProviderMetadata(
                id="slack",
                display_name="Slack",
                kind="connector",
                credential_shape=_shape_api_key("Bot token"),
                docs_url="https://api.slack.com/authentication/basics",
                verify_endpoint="POST https://slack.com/api/auth.test",
            ),
            verify_key=connectors.verify_slack_key,
        ),
        ProviderRecord(
            meta=ProviderMetadata(
                id="google",
                display_name="Google",
                kind="oauth",
                credential_shape=_shape_oauth(),
                docs_url="https://developers.google.com/identity/protocols/oauth2",
                verify_endpoint="oauth2 (Phase 5.13.5)",
            ),
            verify_key=oauth.verify_google_key,
        ),
        ProviderRecord(
            meta=ProviderMetadata(
                id="microsoft",
                display_name="Microsoft",
                kind="oauth",
                credential_shape=_shape_oauth(),
                docs_url="https://learn.microsoft.com/en-us/graph/auth/",
                verify_endpoint="oauth2 (Phase 5.13.5)",
            ),
            verify_key=oauth.verify_microsoft_key,
        ),
    ]
    return {r.meta.id: r for r in items}


_REGISTRY = _build_registry()


def _get_record(provider_id: str) -> ProviderRecord:
    try:
        return _REGISTRY[provider_id]
    except KeyError:
        raise UnknownProvider(provider_id) from None


def get_provider(provider_id: str) -> ProviderMetadata:
    return _get_record(provider_id).meta


def list_providers() -> list[ProviderMetadata]:
    return sorted((r.meta for r in _REGISTRY.values()), key=lambda m: m.id)
