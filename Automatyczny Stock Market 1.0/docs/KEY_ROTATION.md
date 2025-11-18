# Key Rotation and Secret Handling

## Overview

Private and public key material must never be stored in the Git repository. The
`private_key.pem` and `public_key.pem` files now contain placeholder notes only.
Deployments must load signing keys via a secure channel at runtime (for example,
HashiCorp Vault, AWS Secrets Manager, Azure Key Vault, or encrypted environment
variables).

## Rotation Procedure

1. Generate a new key pair in your secure environment.
2. Update the secret in your chosen secret manager.
3. Redeploy the trading backend so that it picks up the new secret value.
4. Invalidate the old keys in all dependent systems.

## Local Development

For local testing, export the key material through environment variables, e.g.:

```bash
export SIGNING_PRIVATE_KEY="$(cat /secure/location/private.pem)"
export SIGNING_PUBLIC_KEY="$(cat /secure/location/public.pem)"
```

Never commit the actual key files to source control.
