# Troubleshooting

## Authentication Issues

### "The request you made needs authentication"

General Keystone 401 error. Work through these in order:

1. **Wrong password** — verify credentials by logging into the Horizon web UI first
2. **Wrong `user_domain_name`** — try `Default` if unsure of the domain name
3. **Both `project_id` and `project_name` set** — remove `project_id`, keep only `project_name`
4. **SSL certificate** — if the cluster uses a self-signed or internal CA cert, the SDK rejects it silently. All scripts in this repo have `verify=False` set to work around this
5. **Port 13000** — this is the public Keystone endpoint in RHOSP deployments. Make sure the `auth_url` ends in `/v3`, e.g. `https://cluster.domain.com:13000/v3`

---

### MFA / Federated Identity (External Auth Provider)

If your OpenStack cluster authenticates via an external identity provider (LDAP, SAML, OIDC) with MFA, password-based API auth will not work. Use application credentials instead.

**Use `test_auth_appcred.py`** — not `test_auth_password.py`.

---

### Creating Application Credentials with Federated Users

#### Error: "invalid application credential — could not find role assignment with role user or group"

This happens because federated users receive roles via group mappings from the IdP, not direct Keystone role assignments. OpenStack cannot inherit those for application credentials.

**Option 1 — Select a role manually in Horizon**

When creating the application credential in **Identity → Application Credentials → Create**:
- Do not leave the Roles field blank
- Explicitly select `member` (or `_member_`, `reader`) from the dropdown

If this still fails, move to Option 2.

**Option 2 — Ask your OpenStack admin to create the credential via CLI**

Provide your admin with:
- Your OpenStack username
- Your user domain name
- Your project name

Admin runs:
```bash
openstack application credential create \
  --user <your-username> \
  --user-domain <your-domain> \
  --role member \
  --description "jumpbox-provision CI credential" \
  jumpbox-provision
```

The output includes an `id` and `secret`. Ask the admin to send these to you securely — the secret is shown only once.

Then build your `clouds.yaml`:

```yaml
clouds:
  openstack:
    auth:
      auth_url: https://your-cluster:13000/v3
      application_credential_id: "<id>"
      application_credential_secret: "<secret>"
    auth_type: v3applicationcredential
    interface: public
    identity_api_version: 3
```

Test with:
```bash
python test_auth_appcred.py --clouds ~/path/to/clouds.yaml
```

**Option 3 — Service account (fallback)**

If application credentials cannot be created for your federated user, ask your admin to create a dedicated local OpenStack user (not federated) with its own password. This service account is used exclusively by the pipeline and bypasses MFA/federation entirely.

Use `test_auth_password.py` with the service account credentials in `clouds.yaml`.

---

### clouds.yaml Structure Reference

**Password auth:**
```yaml
clouds:
  openstack:
    auth:
      auth_url: https://your-cluster:13000/v3
      username: your-username
      password: your-password
      project_name: your-project
      user_domain_name: Default
    interface: public
    identity_api_version: 3
```

**Application credential auth (recommended for CI):**
```yaml
clouds:
  openstack:
    auth:
      auth_url: https://your-cluster:13000/v3
      application_credential_id: "<id>"
      application_credential_secret: "<secret>"
    auth_type: v3applicationcredential
    interface: public
    identity_api_version: 3
```

> `region_name`, `interface`, and `identity_api_version` must be siblings of `auth:`, not nested inside it.
