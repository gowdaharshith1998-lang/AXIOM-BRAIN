/** Types aligned with backend Pydantic models — Phase 5.13.3 */

export type ProviderKind = "llm" | "connector" | "oauth";

export type CredentialField = {
  name: string;
  label: string;
  secret: boolean;
};

export type ProviderMetadata = {
  id: string;
  display_name: string;
  kind: ProviderKind;
  credential_shape: CredentialField[];
  docs_url: string;
  verify_endpoint: string;
};

export type SecretStatus = "untested" | "valid" | "invalid" | "expired";

export type SecretMetadata = {
  id: string;
  provider_id: string;
  key_name: string;
  status: SecretStatus;
  last_tested_at: string | null;
  created_at: string;
  updated_at: string;
};

export type VerifyStatus =
  | "ok"
  | "auth_error"
  | "network_error"
  | "rate_limited"
  | "not_implemented";

export type VerifyResult = {
  status: VerifyStatus;
  detail: string | null;
};

export type StoreSecretBody = {
  provider_id: string;
  key_name: string;
  plaintext: string;
};
