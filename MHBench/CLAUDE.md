# CLAUDE.md

MHBench v3 — builds VM images, then provisions and configures multi-host
cybersecurity benchmark topologies onto an **OpenStack** cloud from JSON specs.

## Read these first (project docs)

This repo is deployed onto a **CloudLab OpenStack** cluster. Before any deployment
work, read these — they hold the operational truth this CLAUDE.md only summarizes:

- **[host.md](host.md)** — the step-by-step deployment runbook. CloudLab is ephemeral
  per experiment, so this file (not a node snapshot) is the source of truth for setup.
- **[findings.md](findings.md)** — environment analysis + every CloudLab gotcha:
  quotas, host firewall / port behavior (incl. 4444 / Caldera 8888), GRE MTU 1458, the
  `external_network` hardcode, the unwired `UploadManager`, missing root images / flavor.
- **[table.md](table.md)** — benchmark catalogue: 44 specs, the canonical Incalmo set
  (Equifax / ICS / PEChain / EnterpriseA / EnterpriseB), host counts, prerequisites.

## Where it runs

MHBench runs **on the `ctl` controller node** (it has the OpenStack APIs, KVM for image
compilation, and CloudLab's admin creds locally). SSH in as the cluster user; the working
tree lives at `~/MHBench`. The local workstation copy is pushed to `ctl` via `rsync`.

## Long-running remote commands MUST be detached (use tmux)

SSH sessions to `ctl` are short-lived and tool/Bash calls time out, so any multi-minute
MHBench command (`compile`, `deploy`, `teardown`) **must** run in a session that survives
disconnects — otherwise SIGHUP kills it mid-run and you lose the work. Use **tmux**:

```bash
tmux new -d -s mh 'cd ~/MHBench && export PATH="$HOME/.local/bin:$PATH" && \
  uv run python cli.py -v compile ubuntu_base webserver 2>&1 | tee /tmp/mh.log'
# watch it:  tmux capture-pane -pt mh   |   tail -f /tmp/mh.log   |   tmux attach -t mh
```

`nohup … > /tmp/mh.log 2>&1 < /dev/null & disown` is an acceptable lightweight equivalent.
**Never** run a long MHBench command in a plain foreground SSH — it will be killed.

## Running the CLI

Use **`uv run python cli.py …`** — NOT `mhbench`. `pyproject.toml` has no `[build-system]`,
so uv treats this as a virtual project and the `mhbench` console script is not installed.

Commands: `compile` · `provision` · `configure` · `deploy` · `teardown`
(`--config` defaults to `config/config.yaml`; `-v` for debug logs).

## Non-obvious must-knows (full detail in findings.md / host.md)

- The cluster user must be in the **`kvm` group** or image compile fails as a confusing
  300s SSH timeout (`sudo usermod -aG kvm $USER`, then reconnect SSH).
- **Pin Python 3.12** (`uv python pin 3.12`) — Ansible 2.17 isn't built for uv's newest
  default (3.14).
- The external network is **`ext-net`**, not the hardcoded `"external"`. The deployers are
  patched to honor `openstack.external_network` in config; keep `external_network: ext-net`.
- `compile` does **NOT** upload to Glance (`UploadManager` is unwired). After compiling,
  manually `openstack image create` the baked qcow2s named exactly `ubuntu_base`,
  `webserver`, `Kali`.
- **Every** benchmark needs an attacker: a `Kali` image + an `m2.large` flavor + a Caldera
  C2C server. Host Caldera **on-cluster** (port 8888) so it never hits CloudLab's external
  firewall.
- OpenStack creds rotate every experiment — regenerate `clouds.yaml` from
  `/root/setup/admin-openrc.sh` (never hardcode the password).

## Architecture (`src/`)

- `compilation/` — offline image compiler (boots a QEMU/KVM VM, bakes via Ansible, shuts down).
- `deployment/` — OpenStack orchestrator: `network_deployer`, `host_deployer`,
  `ansible_runner`, `openstack_client`, `orchestrator`.
- `registry/` — `offline_registry.yaml` (baked images) → `online_registry.yaml` (runtime
  `vm_type`s) → `playbook_registry.yaml` (named Ansible plays).
- `playbooks/plays/` — the Ansible plays. `abstractions/` — pydantic topology models.

Topology specs live in `environments/{non-generated,generated}/*.json`.
