# Deploying MHBench on a CloudLab OpenStack cluster

Runbook for standing up MHBench v3 on a fresh **CloudLab "OpenStack" profile**
experiment (1 controller `ctl` + N compute `cp-*`). Everything runs **on the `ctl`
controller**, which has the OpenStack APIs, KVM (for image compilation), and the
CloudLab-generated admin credentials locally.

> See [findings.md](findings.md) for the why behind each step (quotas, firewall,
> MTU, the `external_network` patch, the `UploadManager` gap, etc.).
> See [table.md](table.md) for the benchmark catalogue.

CloudLab is **ephemeral per experiment** — none of this survives re-allocation, so
this file (not a node snapshot) is the source of truth.

---

## 0. Prereqs

- A running CloudLab OpenStack experiment; SSH as your user (e.g. `dayan`) with
  passwordless sudo. All steps below run on **`ctl`**.
- This repo's working tree on `ctl` (we `rsync` it from a workstation so local
  patches travel):
  ```bash
  # from the workstation, repo root:
  rsync -az --delete \
    --exclude '.git' --exclude '*.qcow2' --exclude 'incalmo.pdf' \
    --exclude '.venv' --exclude '__pycache__' --exclude '*.pyc' \
    ./ <user>@<ctl-host>:MHBench/
  ```

## 1. Host tooling (on ctl)

```bash
sudo DEBIAN_FRONTEND=noninteractive apt-get install -y genisoimage   # image compiler needs it
curl -LsSf https://astral.sh/uv/install.sh | sh                       # uv (manages Python)
export PATH="$HOME/.local/bin:$PATH"

# IMPORTANT: image compilation boots a QEMU VM with -enable-kvm, but your user is
# NOT in the kvm group by default -> qemu fails with "Could not access KVM kernel
# module: Permission denied" and the bake times out after 300s.
sudo usermod -aG kvm $USER          # then RECONNECT SSH so the new login picks up the group
#   verify after reconnect:  id -nG | grep -qw kvm && echo ok

cd ~/MHBench
uv python pin 3.12                  # Ansible 2.17 isn't built for 3.14 (uv's newest); pin 3.12
uv sync                             # py3.12 + ansible + openstacksdk
```

> **Note:** `pyproject.toml` has no `[build-system]`, so uv treats it as a *virtual*
> project and the `mhbench` console script is **not** installed. Run every command as
> **`uv run python cli.py …`** (not `mhbench`).

## 2. OpenStack credentials → clouds.yaml (on ctl)

CloudLab writes admin creds to `/root/setup/admin-openrc.sh` (regenerated every
experiment — the password changes, so extract it on-node, never hardcode it):

```bash
mkdir -p ~/.config/openstack ~/.ssh
PW=$(sudo grep -m1 OS_PASSWORD /root/setup/admin-openrc-newcli.sh | cut -d= -f2)
printf 'clouds:\n  openstack:\n    auth:\n      auth_url: http://ctl:5000/v3\n      username: adminapi\n      password: %s\n      project_name: admin\n      project_domain_name: default\n      user_domain_name: default\n    region_name: RegionOne\n    identity_api_version: 3\n' "$PW" > ~/.config/openstack/clouds.yaml
chmod 600 ~/.config/openstack/clouds.yaml

# sanity check (as your user, no sudo):
openstack --os-cloud openstack image list -f value -c Name
```

## 3. Keypair (on ctl)

```bash
openstack --os-cloud openstack keypair create mhbench > ~/.ssh/mhbench.pem
chmod 600 ~/.ssh/mhbench.pem
```

## 4. config/config.yaml

Already in the repo (`config/config.yaml`). Key fields for CloudLab:

```yaml
openstack:
  clouds_yaml: ~/.config/openstack/clouds.yaml
  cloud: openstack
  keypair_name: mhbench
  ssh_key_path: ~/.ssh/mhbench.pem
  ssh_user: ubuntu
  external_network: ext-net      # <-- CloudLab names it ext-net, not "external"
management:
  cidr: 10.0.1.0/24
  host_ip: 10.0.1.10
  vm_type: ubuntu_base
  flavor: m1.small
```

> **Patch required for stock MHBench:** the deployers hardcode `find_network("external")`.
> This tree is already patched to honor `openstack.external_network`
> (`network_deployer.py`, `host_deployer.py`, default `"external"`). If you ever start
> from an unpatched clone, re-apply that, or rename the network instead:
> `openstack --os-cloud openstack network set --name external ext-net`.

## 5. Compile + upload base images

The root images are **not** in the repo. Download Ubuntu 24.04:

```bash
mkdir -p ~/MHBench/src/compilation/images
wget -q https://cloud-images.ubuntu.com/noble/current/noble-server-cloudimg-amd64.img \
     -O ~/MHBench/src/compilation/images/ubuntu24.qcow2
```

Compile (boots a QEMU/KVM VM per layer, bakes via Ansible, shuts down). It's
long-running — run it detached and tail the log:

```bash
cd ~/MHBench && export PATH="$HOME/.local/bin:$PATH"
nohup uv run python cli.py -v compile ubuntu_base webserver > /tmp/compile.log 2>&1 &
tail -f /tmp/compile.log    # ubuntu_root_ssh -> ubuntu_base -> webserver, ~15-25 min
```

**Upload to Glance** — `cli.py` does NOT do this automatically (`UploadManager` is not
wired up). The deployer looks up images by the offline base name, so names must match
exactly (`ubuntu_base`, `webserver`, `Kali`):

```bash
for img in ubuntu_base webserver; do
  openstack --os-cloud openstack image show "$img" >/dev/null 2>&1 || \
  openstack --os-cloud openstack image create "$img" \
    --file ~/MHBench/src/compilation/images/$img.qcow2 \
    --disk-format qcow2 --container-format bare
done
```

## 6. Attacker prerequisites (Kali / Caldera) — needed by EVERY shipped benchmark

Every spec puts the attacker on `vm_type: kali_running` + `flavor: m2.large` and beacons
to a Caldera C2C server. On a fresh cluster none of these exist:

```bash
# 6a. m2.large flavor (sizing to taste; matches m1.large here)
openstack --os-cloud openstack flavor create m2.large --vcpus 4 --ram 8192 --disk 40

# 6b. Kali image: source/build a Kali cloud qcow2 with cloud-init, place at
#     src/compilation/images/kali.qcow2, then:
uv run python cli.py -v compile Kali
openstack --os-cloud openstack image create Kali \
  --file ~/MHBench/src/compilation/images/Kali.qcow2 \
  --disk-format qcow2 --container-format bare

# 6c. Caldera C2C: host it ON-CLUSTER (ctl or the mgmt host) so attacker->C2 traffic
#     stays on the tenant overlay and never hits CloudLab's external firewall.
#     Pass its URL at deploy time via --c2c-url http://<caldera_ip>:8888
```

## 7. Deploy a benchmark

```bash
cd ~/MHBench && export PATH="$HOME/.local/bin:$PATH"

# validate first (no cloud calls):
uv run python cli.py deploy environments/non-generated/equifax_small.json --validate-only

# full deploy (provision + Ansible configure):
uv run python cli.py -v deploy environments/non-generated/equifax_small.json \
    --project-name exp1 \
    --c2c-url http://<caldera_ip>:8888
```

- `--project-name` prefixes every OpenStack resource (use a unique value per experiment;
  must match at teardown).
- Start with **`equifax_small`** (7 hosts) as a smoke test, then your full set
  (`equifax_*`, `ics`, `chain_pe`, `enterprise_a`, `enterprise_b`).

## 8. Teardown

```bash
uv run python cli.py teardown environments/non-generated/equifax_small.json \
    --project-name exp1 --yes
```

---

## Gotchas (CloudLab-specific)

- **`kvm` group:** your user isn't in it by default → image compilation's QEMU VM fails
  with "Permission denied" and times out at 300s. Fix in step 1 (`usermod -aG kvm` +
  reconnect).
- **Python:** pin **3.12** (step 1) — uv otherwise grabs 3.14, which Ansible 2.17 wasn't
  built against.
- **`uv run mhbench` fails** — use `uv run python cli.py` (no `[build-system]`).
- **Ports / 4444:** CloudLab does NOT filter ports at the host (iptables all-ACCEPT).
  MHBench's security groups open **all ports between connected subnets**, and
  `netcat_shell` opens 4444 in-guest — so reverse shells work attacker↔target. The only
  port that can hit CloudLab's *external* firewall is Caldera's **8888** if C2C is
  off-cluster → keep Caldera on-cluster (step 6c).
- **MTU:** tenant networks are **GRE, MTU 1458** (auto-advertised via DHCP). If
  intra-topology SSH/TCP stalls, verify with `ping -M do -s 1430 <peer-vm>` from a VM.
- **Quotas/capacity:** admin project quotas are unlimited; the cluster has plenty of
  vCPU/RAM for even `equifax_large` (51 VMs).
- **Credentials rotate** every experiment — always regenerate `clouds.yaml` (step 2).
