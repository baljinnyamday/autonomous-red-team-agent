# MHBench Benchmark Inventory

Quick-reference catalogue of every topology spec shipped in `environments/`.
**44 specs total: 13 named (`non-generated/`) + 31 generated synthetic (`generated/`).**

> **Host count** = total VMs in the spec **including the single Kali attacker**.
> e.g. `equifax_small` = 7 means 6 target hosts + 1 attacker.

> ⚠️ **Every spec** (named *and* generated) places the attacker on
> `vm_type: kali_running` + `flavor: m2.large`. So all of them share three
> prerequisites that do **not** exist on a fresh CloudLab OpenStack cluster:
> 1. a **Kali base image** (`src/compilation/images/kali.qcow2`)
> 2. the **`m2.large` flavor** (only `m1.tiny/small/medium/large/xlarge` exist)
> 3. a reachable **Caldera C2C server** (the attacker's `start_attacker` play needs `caldera_ip`)

---

## Canonical Incalmo benchmarks (your core set)

These are the published benchmarks from the Incalmo paper (`incalmo.pdf` in the repo root).

| Paper name | File | Hosts | Subnets | Notes |
|---|---|---:|---:|---|
| **Equifax** (small) | `non-generated/equifax_small.json` | 7 | 3 | smallest real benchmark — best smoke test |
| **Equifax** (medium) | `non-generated/equifax_medium.json` | 27 | 3 | |
| **Equifax** (large) | `non-generated/equifax_large.json` | 51 | 3 | largest named benchmark |
| **ICS** | `non-generated/ics.json` | 48 | 4 | industrial control system scenario |
| **PEChainEnvironment** | `non-generated/chain_pe.json` | 26 | 2 | PE = privilege escalation |
| **EnterpriseA** | `non-generated/enterprise_a.json` | 31 | 4 | |
| **EnterpriseB** | `non-generated/enterprise_b.json` | 41 | 5 | |

## Topology stress-test variants (also in `non-generated/`)

Hand-authored shape tests; `_pe` = privilege-escalation variant.

| File | Hosts | Subnets |
|---|---:|---:|
| `chain_2hosts.json` | 3 | 2 |
| `chain.json` | 26 | 2 |
| `chain_pe.json` | 26 | 2 |
| `star.json` | 26 | 2 |
| `star_pe.json` | 26 | 2 |
| `dumbbell.json` | 31 | 3 |
| `dumbbell_pe.json` | 31 | 3 |

---

## Generated synthetic topologies (`generated/`)

31 programmatically-generated specs with randomized topology and mixed
vulnerability types (`webserver` / `netcat` / `sudobaron` / `writeable`).
Best choice for **scaling / variance studies**. Range: **12–46 hosts**.

| File | Hosts | Subnets |
|---|---:|---:|
| `generated_network_7.json` | 12 | 3 |
| `generated_mini.json` | 12 | 5 |
| `generated_network_3.json` | 15 | 3 |
| `generated_network_8.json` | 15 | 3 |
| `generated_network_6.json` | 18 | 3 |
| `generated_network_5.json` | 19 | 3 |
| `generated_network_0.json` | 20 | 3 |
| `generated_network_16.json` | 20 | 3 |
| `generated_network_19.json` | 22 | 4 |
| `generated_network_1.json` | 23 | 5 |
| `generated_network_10.json` | 24 | 4 |
| `generated_network_9.json` | 27 | 4 |
| `generated_network_12.json` | 28 | 3 |
| `generated_network_17.json` | 31 | 4 |
| `generated_network_11.json` | 33 | 4 |
| `generated_network_22.json` | 33 | 4 |
| `generated_network_14.json` | 33 | 5 |
| `generated_network_4.json` | 34 | 5 |
| `generated_network_2.json` | 35 | 5 |
| `generated_network_28.json` | 36 | 4 |
| `generated_network_24.json` | 37 | 5 |
| `generated_network_23.json` | 40 | 5 |
| `generated_network_27.json` | 42 | 4 |
| `generated_network_18.json` | 42 | 5 |
| `generated_network_26.json` | 43 | 5 |
| `generated_network_15.json` | 44 | 5 |
| `generated_network_25.json` | 44 | 5 |
| `generated_network_20.json` | 45 | 5 |
| `generated_network_13.json` | 46 | 5 |
| `generated_network_21.json` | 46 | 5 |
| `generated_network_29.json` | 46 | 5 |

---

## VM types used across all specs

Online-registry `vm_type`s referenced by the benchmarks (→ image that must be compiled):

| vm_type | base image |
|---|---|
| `ubuntu_base_running` | `ubuntu_base` |
| `ubuntu_netcat_running` | `ubuntu_base` |
| `ubuntu_writeable_running` | `ubuntu_base` |
| `ubuntu_sudobaron_running` | `ubuntu_base` |
| `ubuntu_netcat_writeable_running` | `ubuntu_base` |
| `ubuntu_netcat_sudobaron_running` | `ubuntu_base` |
| `webserver_running` | `webserver` |
| `webserver_netcat_running` | `webserver` |
| `webserver_writeable_running` | `webserver` |
| `webserver_sudobaron_running` | `webserver` |
| `webserver_netcat_writeable_running` | `webserver` |
| `webserver_netcat_sudobaron_running` | `webserver` |
| `kali_running` | `Kali` |

So compiling **`ubuntu_base`** + **`webserver`** (+ **`Kali`** for the attacker) covers every benchmark.

---

## Recommended smoke-test order

1. `equifax_small` (7 hosts) — smallest real benchmark, validates the full pipeline.
2. Your core set: `equifax_*`, `ics`, `chain_pe`, `enterprise_a`, `enterprise_b`.
3. `generated_*` for scaling/variance runs.
