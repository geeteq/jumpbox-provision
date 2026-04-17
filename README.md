# jumpbox-provision

Provisions a RHEL9 jumpbox VM on OpenStack via a GitLab CI pipeline using cloud-init.

---

## Prerequisites

- GitLab project with a registered runner
- OpenStack cluster with an existing RHEL9 image, flavor, and network
- OpenStack application credential (see [Generating an API Key](#generating-an-api-key))

---

## Project Structure

```
jumpbox-provision/
├── config.yaml          # VM and OpenStack parameters
├── provision_vm.py      # Provisioning script
├── generate_api_key.sh  # Generates an OpenStack application credential
├── requirements.txt     # Python dependencies
└── .gitlab-ci.yml       # Pipeline definition
```

---

## Configuration

Edit `config.yaml` to match your OpenStack environment before running the pipeline:

```yaml
openstack:
  auth_url: "https://your-openstack-cluster:5000/v3"
  project_name: "your-project"

vm:
  name: "jumpbox"
  image: "rhel9"          # image name as it appears in OpenStack
  flavor: "m1.medium"
  network: "your-network"
  security_groups:
    - "default"
    - "ssh-access"
  availability_zone: "nova"
  floating_ip_pool: ""    # external network name for floating IP, or leave empty
```

---

## Generating an API Key

Run this once locally to create an OpenStack application credential:

```bash
# Fill in your credentials first
export OS_AUTH_URL=https://your-openstack-cluster:5000/v3
export OS_USERNAME=your-username
export OS_PASSWORD=your-password
export OS_PROJECT_NAME=your-project

bash generate_api_key.sh
```

The script prints the credential ID and secret. Save these — you will add them as GitLab CI variables in the next step.

---

## Setting Up GitLab CI Variables

All secrets are stored in GitLab and never committed to the repository.

### 1. Navigate to CI/CD Variables

In your GitLab project go to:
**Settings → CI/CD → Variables → Add variable**

### 2. Add OpenStack Credentials

Add the following variables. Set all as **Masked** to hide them from job logs.

| Key | Value | Masked |
|-----|-------|--------|
| `OS_AUTH_URL` | `https://your-openstack-cluster:5000/v3` | Yes |
| `OS_USERNAME` | your OpenStack username | Yes |
| `OS_PASSWORD` | your OpenStack password | Yes |
| `OS_PROJECT_NAME` | your OpenStack project name | Yes |
| `OS_PROJECT_DOMAIN_NAME` | `Default` | No |
| `OS_APPLICATION_CREDENTIAL_ID` | ID from `generate_api_key.sh` output | Yes |
| `OS_APPLICATION_CREDENTIAL_SECRET` | Secret from `generate_api_key.sh` output | Yes |

> If `OS_APPLICATION_CREDENTIAL_ID` and `OS_APPLICATION_CREDENTIAL_SECRET` are set, the pipeline will use them instead of username/password.

### 3. Add the SSH Public Key

This is the key that will be injected into the `baremetal` user on the VM.

1. Go to **Settings → CI/CD → Variables → Add variable**
2. Set the following:
   - **Key:** `SSH_PUBLIC_KEY`
   - **Value:** paste the contents of your public key (e.g. `~/.ssh/id_rsa.pub`)
   - **Type:** Variable
   - **Masked:** Yes
   - **Protected:** Yes (if you only deploy from protected branches)
3. Click **Add variable**

To get your public key value:
```bash
cat ~/.ssh/id_rsa.pub
```

---

## Running the Pipeline

### Triggering from GitLab UI

The `provision_vm` job is set to **manual** to prevent accidental deployments.

1. Go to your GitLab project
2. Navigate to **CI/CD → Pipelines**
3. Click **Run pipeline** on the `main` branch
4. Once the pipeline starts, the `dry_run_vm` job runs automatically — check its log to validate your config and see the cloud-init payload
5. If the dry run looks correct, click the **play button** next to `provision_vm` to trigger the deployment

### What Each Job Does

| Job | Trigger | Purpose |
|-----|---------|---------|
| `generate_api_key` | Manual (web trigger only) | Creates an OpenStack application credential — run this once to bootstrap |
| `dry_run_vm` | Automatic on push to `main` | Validates config, resolves image/flavor/network, prints cloud-init — no VM created |
| `provision_vm` | Manual | Creates the VM, waits for ACTIVE, polls SSH port 22, prints the connect command |

### Successful Deployment Output

At the end of the `provision_vm` job log you will see:

```
VM 'jumpbox' is ACTIVE (id: xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx)
Floating IP: 203.0.113.10
Waiting for SSH on 203.0.113.10:22 (up to 120s) ...
SSH is ready on 203.0.113.10.

Connect with: ssh baremetal@203.0.113.10
Provisioning complete.
```

### Idempotency

Re-running the pipeline when the VM already exists is safe — the script detects the existing VM by name and exits cleanly without modifying it.

---

## Connecting to the VM

Once the pipeline completes, SSH in using the `baremetal` user:

```bash
ssh baremetal@<ip-from-pipeline-log>
```

The `mtr` package is installed automatically via cloud-init on first boot.
