# jumpbox-provision

Provisions a RHEL9 jumpbox VM on OpenStack via a GitLab CI pipeline using cloud-init.

---

## Prerequisites

- GitLab project with a registered runner
- OpenStack cluster with an existing RHEL9 image, flavor, and network
- OpenStack application credential (see [Authentication](#authentication))

---

## Project Structure

```
jumpbox-provision/
├── config.yaml              # VM and cloud parameters
├── provision_vm.py          # Provisioning script
├── generate_api_key.sh      # Creates an OpenStack application credential via CLI
├── make_dotenv.sh           # Installs clouds.yaml to ~/.config/openstack/
├── test_auth_password.py    # Test password-based auth
├── test_auth_appcred.py     # Test application credential auth
├── requirements.txt         # Python dependencies
├── .gitlab-ci.yml           # Pipeline definition
├── .env.example             # Example env file for SSH key and GitHub token
├── TROUBLESHOOT.md          # Auth error reference
└── .gitignore
```

---

## Configuration

### 1. Install your clouds.yaml locally

Download your `clouds.yaml` from the OpenStack Horizon UI and run:

```bash
bash make_dotenv.sh ~/Downloads/clouds.yaml
```

This copies it to `~/.config/openstack/clouds.yaml` where the OpenStack SDK and CLI will find it automatically.

### 2. Edit config.yaml

Set the cloud name and VM parameters to match your environment:

```yaml
cloud: openstack    # must match the cloud name in your clouds.yaml

vm:
  name: "jumpbox"
  image: "rhel9"           # image name as it appears in OpenStack
  flavor: "m1.medium"
  network: "your-network"
  security_groups:
    - "default"
    - "ssh-access"
  availability_zone: "nova"
  floating_ip_pool: ""     # external network name for floating IP, or leave empty

ssh:
  baremetal_user: "baremetal"
  public_key: "ssh-rsa AAAA... user@host"

packages:
  - mtr
```

---

## Authentication

This project supports two authentication methods. Application credentials are strongly recommended for CI pipelines.

### Option A — Application Credentials (recommended)

Application credentials bypass MFA and are safe to store in CI variables.

#### If your cluster uses standard password auth

Generate a credential using the CLI:

```bash
bash generate_api_key.sh ~/.config/openstack/clouds.yaml openstack
```

#### If your cluster uses federated identity / MFA (external auth provider)

You cannot generate credentials via the CLI directly. Use one of these approaches:

**Via Horizon UI:**
1. Log in to the OpenStack web console (MFA handled by browser)
2. Go to **Identity → Application Credentials → Create Application Credential**
3. Enter a name (e.g. `jumpbox-provision`)
4. In the **Roles** field, explicitly select `member`
5. Click **Create Application Credential** and copy the ID and secret

**Via admin (if Horizon fails):**
Ask your OpenStack admin to run:
```bash
openstack application credential create \
  --user <your-username> \
  --user-domain <your-domain> \
  --role member \
  --description "jumpbox-provision CI credential" \
  jumpbox-provision
```

Once you have the credential, update your `clouds.yaml`:

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

Test it:
```bash
python test_auth_appcred.py --clouds ~/.config/openstack/clouds.yaml
```

### Option B — Password Auth

For non-federated clusters only. Ensure your `clouds.yaml` has `username` and `password` set, then test:

```bash
python test_auth_password.py --clouds ~/.config/openstack/clouds.yaml
```

> See [TROUBLESHOOT.md](TROUBLESHOOT.md) if authentication fails.

---

## Setting Up GitLab CI Variables

All secrets are stored in GitLab and never committed to the repository.

Go to **Settings → CI/CD → Variables → Add variable** and add:

### clouds.yaml (required)

| Key | Type | Masked | Value |
|-----|------|--------|-------|
| `CLOUDS_YAML` | File | No | Full contents of your `clouds.yaml` |
| `CLOUD_NAME` | Variable | No | Cloud name (e.g. `openstack`) |

### SSH Public Key (required)

| Key | Type | Masked | Value |
|-----|------|--------|-------|
| `SSH_PUBLIC_KEY` | Variable | Yes | Contents of `~/.ssh/id_rsa.pub` |

To get your public key:
```bash
cat ~/.ssh/id_rsa.pub
```

---

## Running the Pipeline

The `provision_vm` job is manual to prevent accidental deployments.

1. Go to **CI/CD → Pipelines → Run pipeline** on `main`
2. The `dry_run_vm` job runs automatically — check its log to validate config and see the cloud-init payload
3. If the dry run looks correct, click the **play button** next to `provision_vm`

### Pipeline Jobs

| Job | Trigger | Purpose |
|-----|---------|---------|
| `generate_api_key` | Manual (web trigger) | Creates an application credential — run once to bootstrap |
| `dry_run_vm` | Automatic on push to `main` | Validates config, resolves resources, prints cloud-init — no VM created |
| `provision_vm` | Manual | Creates the VM, waits for ACTIVE, polls SSH port 22, prints connect command |

### Successful Deployment Output

```
Auth mode: application credential (abc12345...)
Creating VM 'jumpbox' ...
  Image:   rhel9 (xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx)
  Flavor:  m1.medium (xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx)
  Network: your-network (xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx)
VM 'jumpbox' is ACTIVE (id: xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx)
Floating IP: 203.0.113.10
Waiting for SSH on 203.0.113.10:22 (up to 120s) ...
SSH is ready on 203.0.113.10.

Connect with: ssh baremetal@203.0.113.10
Provisioning complete.
```

### Idempotency

Re-running the pipeline when a VM with the same name already exists is safe — the script detects it and exits without making changes.

---

## Connecting to the VM

```bash
ssh baremetal@<ip-from-pipeline-log>
```

The `mtr` package is installed automatically via cloud-init on first boot.
