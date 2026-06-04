# MHBench on CloudLab — Deployment Findings

Investigation of deploying MHBench v3 onto the CloudLab OpenStack cluster
`mhbench-pg0` (profile `large`). Read-only recon; no changes made to the cloud
or the benchmark. Date: 2026-06-03.

---

## 1. Cluster topology

CloudLab **OpenStack profile** (controller + 3 compute). All nodes Ubuntu 22.04,
SSH user `dayan` with **passwordless sudo**.

| Role | CloudLab node | SSH host | Notes |
|---|---|---|---|
| Controller | `ctl` | `c220g2-010819.wisc.cloudlab.us` | all OpenStack APIs + admin creds + KVM here |
| Compute | `cp-1` | `c220g2-010826.wisc.cloudlab.us` | |
| Compute | `cp-2` | `c220g2-010825.wisc.cloudlab.us` | |
| Compute | `cp-3` | `c220g2-010829.wisc.cloudlab.us` | |

**MHBench should run on `ctl`** — it has the OpenStack APIs locally, KVM for image
compilation, and the admin credentials.

## 2. OpenStack facts

- Admin creds (CloudLab-generated): `/root/setup/admin-openrc.sh`
  - user `adminapi`, project `admin`, auth `http://ctl:5000/v3`
  - (CloudLab regenerates these per experiment — never hardcode the password)
- `openstack` CLI 6.0.0 present on `ctl`.
- Deploys land in the **`admin`** project (that's what `adminapi` authenticates as).

## 3. Capacity & quotas — ✅ no blocker

- **Quotas: all `-1` (unlimited)** for instances, cores, ram, floating-ips,
  secgroups, secgroup-rules, networks, subnets, ports, routers.
- **Hypervisor capacity (3 nodes combined): 120 vCPUs, ~483 GB RAM, ~3.4 TB disk.**
- `m1.small` = 1 vCPU / 2 GB / 20 GB disk.
- Largest benchmark `equifax_large` (51 VMs × m1.small) ≈ 51 vCPU / 102 GB / ~1 TB
  → fits comfortably on **compute** quota. Every shipped topology fits on vCPU/RAM/disk.
- ⚠️ **But the public-IP pool is the real ceiling, not compute** — see §4.1. Only **one**
  MHBench named benchmark can be deployed at a time.

## 4. Networks

| Network | Type | MTU | Role |
|---|---|---|---|
| `ext-net` | (external) | — | floating-IP / external gateway pool |
| `flat-lan-1-net` | flat | 1500 | provider flat net |
| `tun0-net` | **gre** | **1458** | tenant overlay sample |

- ML2: `tenant_network_types = flat,gre,vxlan`, mechanism `openvswitch`.
- MHBench creates tenant networks with **no provider attrs** → Neutron allocates
  **gre, MTU 1458** (flat is already consumed by `flat-lan-1-net`).
- **MTU note:** 1458 is advertised to instances via DHCP (option 26); Ubuntu cloud
  images honor it automatically, so no manual MTU fix is expected. **Verify at
  deploy time** with a large-packet ping between two VMs
  (`ping -M do -s 1430 <peer>`) — fragmentation here would silently stall SSH/TCP.

### ⚠️ External-network name mismatch (must reconcile before deploy)
MHBench **hardcodes** `find_network("external")` in two places:
- `src/deployment/network_deployer.py:27`
- `src/deployment/host_deployer.py:114`

This cloud's external network is named **`ext-net`**. The config model *already* has
an unused `external_network` field (`config/config.py:33`).

**Decision (chosen): patch the code** to read `config.openstack.external_network`
(default `"external"`), set `external_network: ext-net` in `config.yaml`.
Rationale: CloudLab recreates `ext-net` every experiment, so renaming the live
network is a *recurring* mutation of shared infra (and CloudLab's own
`setup-*-network`/`add-node` scripts reference it by name). The patch is ~3 lines,
lives in the repo, and needs zero cloud mutation.

### 4.1 ⚠️ Public-IP pool exhaustion — only ONE deployment at a time
Although `ext-subnet` advertises a huge CIDR (`REDACTED_INFRA_IP/22`), its Neutron **allocation
pool is tiny** — observed exactly **4 IPs** (`REDACTED_INFRA_IP–156`). Two are permanently held
by CloudLab infra routers (`tun0-router` `.153`, `flat-lan-1-router` `.154`), leaving **only 2
free**. Each MHBench deployment consumes **2**: one for its `<project>-router` external gateway
and one for the management-host floating IP. So a **second** named benchmark fails at router
creation with `ConflictException: 409 ... No more IP addresses available on network <ext-net>`.

**Implication:** only one MHBench benchmark fits at a time. Teardown the prior project to free
its 2 IPs before deploying another. Do **not** expand the pool into the rest of the /22 — those
public IPs are assigned to other CloudLab nodes/experiments.

**Preflight:** `openstack --os-cloud openstack port list --network ext-net` → need ≥2 free.
Reused IPs also leave stale `~/.ssh/known_hosts` keys on ctl (blocks manual SSH via the
jumpbox) → clear with `ssh-keygen -R <ip>` or `-o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null`.

## 5. Images & flavors

- Glance images present: `bionic-server`, `focal-server`, `jammy-server`,
  `manila-service-image`. **No Ubuntu 24.04 / no Kali.**
- Flavors present: `m1.tiny`(512/1/1), `m1.small`(2048/1/20), `m1.medium`(4096/2/40),
  `m1.large`(8192/4/80), `m1.xlarge`(16384/8/160). *(RAM MB / vCPU / disk GB)*
- ⚠️ **`m2.large` is ABSENT** but every benchmark's attacker requires it.
  Must create, e.g. `openstack flavor create m2.large --vcpus 4 --ram 8192 --disk 40`
  (exact specs TBD — pick to match original MHBench attacker sizing).

## 6. Tooling on `ctl`

| Tool | State | Action |
|---|---|---|
| Python | **3.10** (MHBench needs ≥3.12) | `uv` will manage a 3.12 toolchain |
| `uv` | ❌ missing | install (`pip install uv` or astral installer) |
| `genisoimage` | ❌ missing (needed by image compiler) | `apt-get install -y genisoimage` |
| `/dev/kvm` | ✅ present (80 vmx/svm) | image compilation will be fast |
| `qemu-system-x86_64`, `qemu-img` | ✅ present | |

## 7. MHBench code findings (gaps to handle)

1. **Root base images are NOT in the repo.** Offline registry roots
   `ubuntu24.qcow2` and `kali.qcow2` (`src/registry/offline_registry.yaml`) have no
   source — must be downloaded/built:
   - `ubuntu24` → Ubuntu 24.04 (noble) cloud image qcow2.
   - `Kali` → Kali cloud qcow2 with cloud-init (non-trivial; only needed for attacker).
2. **`UploadManager` is dead code in the CLI flow.** `cli.py` and the orchestrator
   never call it (`grep` confirms it's only defined). `HostDeployer` does
   `find_image(base_image_name)` expecting the image to **already be in Glance**.
   → After compiling, baked qcow2s must be **manually uploaded** to Glance with names
   matching the offline base image (`ubuntu_base`, `webserver`, `Kali`):
   ```
   openstack image create ubuntu_base --file src/compilation/images/ubuntu_base.qcow2 \
       --disk-format qcow2 --container-format bare
   ```
   This multi-GB upload is the only genuinely slow "image" step — once per image.
3. The external-network hardcode (see §4).
4. **Kali attacker image is missing tools `bake_attacker.yml` assumes** → aborts the deploy at
   the *last* host on every topology. Two missing deps found (eqlarge deploy, 2026-06-04):
   `nikto -Version` needs Perl modules **`JSON`** + **`XML::Writer`** (`libjson-perl`,
   `libxml-writer-perl`), and the sandcat download uses **`curl`** (`rc 127: curl: not found`).
   **Fix applied:** `bake_attacker.yml` now `apt install`s `git curl perl libjson-perl
   libxml-writer-perl` (`update_cache: true`). **Better permanent fix:** bake these (+nikto)
   into the `Kali` image at compile time so there's no deploy-time apt/repo dependency.
   NB: MHBench `configure` has no resume — a single missing package costs a full ~20-min
   per-host replay before the attacker plays re-run; re-run `configure` (not `deploy`) and/or
   pre-install the package on the live attacker via the jumpbox to unblock fast.

## 8. Port / firewall analysis  (answers the 4444 question)

**CloudLab is NOT hiding ports at the host level.** On `ctl`:
- iptables `INPUT`/`FORWARD`/`OUTPUT` policies are all **ACCEPT**; no emulab/CloudLab
  REJECT/DROP rules beyond OpenStack's own security-group machinery.

The only gate on benchmark traffic is **OpenStack security groups**, and MHBench
configures them favorably:
- For each internal subnet it creates ingress rules from its own CIDR + each
  connected peer CIDR + the management CIDR, **with no port restriction** (rules pass
  only `remote_ip_prefix` → all protocols/ports). So **4444 (and any port) is open
  between hosts in connected subnets.**
- `netcat_shell.yml` additionally opens 4444 in-guest (`iptables -A INPUT ... 4444
  ACCEPT`) and runs the ncat listener on 4444.
- `external: true` subnets get full 0.0.0.0/0 ingress+egress.

**Implication for 4444:** works attacker↔target as long as their subnets are listed
in `subnet_connections`. No CloudLab-level unblocking needed.

**The real external-firewall risk is Caldera C2C (port 8888), not 4444.**
`start_attacker.yml` makes the agent beacon to `http://{caldera_ip}:8888`. If Caldera
runs **off-cluster**, the attacker's traffic must traverse CloudLab's external path on
8888 — that's where filtering *could* bite.
→ **Recommendation: host Caldera on-cluster** (on `ctl` or the management host, which
is reachable from every tenant subnet via the router + mgmt SG). This sidesteps
CloudLab's external firewall entirely.

## 9. "Snapshot" analysis

There is **no OpenStack snapshot anywhere in MHBench's deploy/provision/configure
path.** The only `snapshot` references in the repo are:
- A **misleading comment** in `setup_struts.yml:122` ("Forces openstack snapshot…")
  on a harmless `touch ~/.ssh/config` task — it does not trigger any snapshot.
- Unrelated mentions in the bundled `falco.yaml` defaults.

So nothing in the deploy flow takes a slow snapshot. The slow image step is the
one-time **Glance upload** of baked qcow2s (§7.2). No CloudLab node snapshot will be
taken to persist setup — **`host.md` is the persistence mechanism** instead.

## 10. Prerequisite checklist for a full deploy

- [ ] Install `uv` + `genisoimage` on `ctl`
- [ ] Get MHBench repo onto `ctl` (clone vs rsync — decision pending)
- [ ] Patch `external_network` config field; set `external_network: ext-net`
- [ ] Write `config/config.yaml` + `~/.config/openstack/clouds.yaml` (from admin creds)
- [ ] Create an `mhbench` keypair + private key on `ctl`
- [ ] Download `ubuntu24.qcow2` (noble cloud image)
- [ ] `mhbench compile ubuntu_base` (and `webserver`)
- [ ] **Upload** `ubuntu_base` / `webserver` qcow2s to Glance (UploadManager gap)
- [ ] *(attacker)* create `m2.large` flavor
- [ ] *(attacker)* source/build `kali.qcow2`, compile + upload `Kali`
- [ ] *(attacker)* stand up Caldera C2C **on-cluster**, pass `--c2c-url`
- [ ] **Preflight ext-net IPs ≥ 2** (`port list --network ext-net`); teardown prior project if not (§4.1)
- [ ] Deploy `equifax_small` as smoke test; verify MTU + intra-topology 4444
