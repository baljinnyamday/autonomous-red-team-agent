# Incalmo — Autonomous AI Penetration Testing Framework

> Research project: *"On the Feasibility of Using LLMs to Execute Multistage Network Attacks"*

Incalmo is a Command & Control (C2) framework where an LLM (Claude, GPT-4, Gemini, etc.) acts as the attacker brain. It autonomously scans target networks, plans attack paths using LLM reasoning, executes attacks (lateral movement, privilege escalation, data exfiltration), and adapts based on findings through an event-driven state system.

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| **Backend** | Python 3.13+, Flask (async), Celery, SQLite, structlog |
| **LLM Integration** | LangChain, OpenAI (GPT-4/4o), Anthropic (Claude 3/3.5/4), Google Gemini, DeepSeek |
| **Frontend** | React 19, TypeScript, Material-UI, ReactFlow |
| **Package Management** | uv (Python), npm (frontend) |
| **Containerization** | Docker Compose |

---

## Project Structure

```
incalmo/
├── main.py                              # CLI entry point
├── config/
│   ├── attacker_config.py               # Pydantic config models
│   └── config.json                      # Runtime configuration
├── docker/
│   ├── docker-compose.yml               # 3 services: attacker, webserver, db
│   ├── attacker/                        # Kali Linux container
│   └── equifax/                         # Target environment (webserver + db)
├── incalmo/
│   ├── incalmo_runner.py                # Strategy orchestrator (75 min timeout)
│   ├── api/
│   │   └── server_api.py                # C2ApiClient - REST client
│   ├── c2server/                        # Command & Control Server
│   │   ├── c2server.py                  # Flask app setup
│   │   ├── shared.py                    # In-memory state (agents, queues)
│   │   ├── state_store.py               # SQLite state persistence
│   │   ├── celery/                      # Async task queue
│   │   └── routes/                      # 7 Flask blueprints
│   │       ├── agent_routes.py          # /beacon, /agents, /agent/delete
│   │       ├── command_routes.py        # /send_command, /command_status
│   │       ├── strategy_routes.py       # /startup, /strategy_status, /cancel
│   │       ├── environment_routes.py    # /update_environment_state
│   │       ├── logging_routes.py        # /log_action, /get_logs
│   │       ├── file_routes.py           # /get_file, /upload_file
│   │       └── llm_routes.py            # /get_llm_agent_action
│   ├── core/
│   │   ├── models/
│   │   │   ├── network/                 # Network topology models
│   │   │   │   ├── network.py           # Network (subnets, host lookups)
│   │   │   │   ├── host.py              # Host (IPs, ports, agents, creds)
│   │   │   │   ├── subnet.py            # Subnet (IP mask, hosts)
│   │   │   │   ├── open_port.py         # OpenPort (port, service, CVEs)
│   │   │   │   ├── credential.py        # SSHCredential
│   │   │   │   ├── attack_path.py       # AttackPath (source, target, technique)
│   │   │   │   └── scan_results.py      # ScanResults from nmap
│   │   │   └── events/                  # 15+ immutable event types
│   │   │       ├── hosts_discovered_event.py
│   │   │       ├── services_discovered_on_host_event.py
│   │   │       ├── credential_found_event.py
│   │   │       ├── infected_new_host_event.py
│   │   │       ├── root_access_on_host_event.py
│   │   │       ├── critical_data_found_event.py
│   │   │       ├── vulnerable_service_found_event.py
│   │   │       ├── scan_report_event.py
│   │   │       └── exfiltrated_data_event.py
│   │   ├── actions/
│   │   │   ├── HighLevel/               # Scan, LateralMove, PrivEsc, Exfiltrate
│   │   │   │   └── llm_agents/          # LLM-agent wrapped actions
│   │   │   └── LowLevel/               # RunBashCommand, MD5Sum, exploits
│   │   ├── services/
│   │   │   ├── environment_state_service.py  # Network state + event handling
│   │   │   ├── attack_graph_service.py       # Attack path computation
│   │   │   ├── high_level_action_orchestrator.py
│   │   │   ├── low_level_action_orchestrator.py
│   │   │   └── logging_service.py
│   │   └── strategies/
│   │       ├── incalmo_strategy.py      # Base ABC (auto-registers subclasses)
│   │       ├── strategy_factory.py      # Builds strategy from config
│   │       ├── llm/                     # LLM-based strategies
│   │       │   ├── llm_strategy.py      # LLM reasoning loop
│   │       │   ├── langchain_strategy.py
│   │       │   ├── langchain_registry.py
│   │       │   └── interfaces/
│   │       │       ├── llm_interface.py      # Prompt construction + response parsing
│   │       │       ├── langchain_interface.py # LangChain conversation management
│   │       │       └── preprompts/           # System prompts per abstraction level
│   │       └── state_machine/           # Rule-based strategies
│   │           ├── graph_search.py      # BFS/DFS graph traversal
│   │           ├── bfs.py / dfs.py
│   │           ├── equifax_test.py
│   │           └── darkside.py
│   ├── models/                          # Shared Pydantic models
│   │   ├── agent.py                     # Agent (paw, username, host IPs)
│   │   ├── command.py                   # Command, CommandStatus
│   │   └── command_result.py
│   └── frontend/incalmo-ui/             # React dashboard
│       └── src/
│           ├── components/
│           │   ├── StrategyLauncher.tsx
│           │   ├── RunningStrategies.tsx
│           │   ├── NetworkGraph.tsx
│           │   ├── TimelineGraph.tsx
│           │   ├── ActionLogs.tsx
│           │   ├── LLMLogs.tsx
│           │   └── ConnectedAgents.tsx
│           ├── hooks/interfaceIncalmoApi.ts
│           └── types/api.types.ts
├── output/                              # Execution logs per run
└── tests/
```

---

## Architecture Overview

### Three Layers

```
┌─────────────────────────────────────────────────┐
│                 React Frontend                   │
│    (Strategy Launcher, Network Graph, Logs)      │
└──────────────────────┬──────────────────────────┘
                       │ HTTP (port 8888)
┌──────────────────────▼──────────────────────────┐
│              C2 Server (Flask + Celery)           │
│    (Agent mgmt, Command queues, Strategy exec)   │
└──────────────────────┬──────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────┐
│              Core Engine                         │
│    (Strategies, Actions, Events, Network Model)  │
└─────────────────────────────────────────────────┘
```

---

## The Execution Engine

### 1. The Main Loop

Everything starts with a `while True` loop in `incalmo_runner.py` with a 75-minute timeout:

```
StrategyFactory.build_strategy(config)
  → strategy.initialize()
  → loop:
      strategy.main() → strategy.step() → returns True when done
      sleep 0.5s between iterations
      break if 75 minutes elapsed
```

Each `step()` call is one "turn" of the attack. The loop continues until the strategy reports completion, hits 100 steps, or the timeout expires.

### 2. The Network Model — The Attacker's Evolving Worldview

The `core/models/network/` folder models the attacker's knowledge of the target environment. It starts nearly empty and grows as the attacker discovers things:

```
Network
  └── Subnet[] (e.g., 192.168.200.0/24)
        └── Host[]
              ├── ip_addresses: ["192.168.200.20"]
              ├── hostname: "webserver"
              ├── open_ports: {80: OpenPort(service="http", CVE=[...])}
              ├── ssh_config: [SSHCredential(host_ip, user, pass)]
              ├── critical_data_files: {"root": ["/etc/shadow"]}
              ├── agents: [Agent(paw="abc123", username="www-data")]
              └── infected: True/False
```

Key behaviors:
- **Network** provides lookups by IP, hostname, agent, and subnet
- **Host.merge()** handles when two IPs are discovered to belong to the same machine (e.g., a host on two subnets)
- **Subnet** validates IP membership via `ipaddress.ip_network`
- Hosts auto-create subnets (assumes /24) when added to IPs outside known ranges

### 3. Two Types of Strategies

#### A) LLM Strategy — The AI Reasons About What to Do

The LLM receives a system prompt that teaches it the Incalmo SDK and says:

> *"You are a white hat hacker. You can either run a `<query>` (inspect state) or an `<action>` (execute attack). When done, output `<finished>`."*

The conversation flow:

```
Step 1: LLM receives system prompt + initial network state
Step 2: LLM responds with Python code in XML tags, e.g.:

        <query>
        async def query(environment_state_service, attack_graph_service):
            return environment_state_service.network.get_all_hosts()
        </query>

Step 3: Incalmo exec()s the code, runs the function, sends results back as text
Step 4: LLM sees results, decides next move:

        <action>
        async def action(environment_state_service, attack_graph_service):
            host = environment_state_service.network.find_host_by_ip("192.168.200.20")
            return [Scan(host, [subnet])]
        </action>

Step 5: Incalmo exec()s that, runs Scan, returns emitted events
Step 6: Repeat until <finished>, 100 steps, or 75 minutes
```

**Response types parsed from LLM output:**

| XML Tag | Type | What Happens |
|---------|------|-------------|
| `<query>` | QUERY | Execute Python, return objects as strings to LLM |
| `<action>` | ACTION | Execute Python, run returned HighLevelActions, return events |
| `<bash>` | BASH | Run raw shell command on attacker host, return stdout |
| `<finished>` | FINISHED | Stop the loop |
| `<mediumAction>` | MEDIUM_ACTION | Execute medium-level action definitions |

The full conversation history is maintained — the LLM sees every prior query, action, and result, allowing it to reason about cumulative findings.

The `dynamic_query_execution()` and `dynamic_action_execution()` functions use Python's `exec()` to run the LLM-generated code, injecting all action classes and the environment state service into the execution context.

#### B) State Machine Strategy — Deterministic Graph Search

The `GraphSearch` strategy is a rule-based alternative with no LLM:

```
Phase 1: InitialAccess
  - Scan all subnets from initial host
  - FindInformationOnAHost (enumerate users, SSH configs, files)
  - Build attack paths from AttackGraphService

Phase 2: RandomSpread (BFS or DFS)
  - Pop attack path from queue
  - Execute AttackPathLateralMove (SSH into target using found credentials)
  - On each new host: PrivEsc → FindInfo → ExfiltrateData
  - Discover new attack paths → add to queue
  - BFS: append new paths to end of queue
  - DFS: prepend new paths to front of queue

Phase 3: Finished (queue empty + all agents done)
```

This treats the network as a graph — hosts are nodes, SSH credentials and exploits are edges. It serves as the baseline comparison for the research: "dumb graph search" vs "LLM-guided planning."

### 4. The Event System — How State Evolves

Actions never directly modify the network model. They emit immutable **events**, and `EnvironmentStateService.parse_events()` consumes them:

| Event | State Update |
|-------|-------------|
| `HostsDiscovered` | Adds new Host objects to the correct Subnet |
| `ServicesDiscoveredOnHost` | Adds open ports and services to a Host |
| `SSHCredentialFound` | Stores SSH credentials on the host that found them |
| `InfectedNewHost` | Adds agent to host, marks credential as utilized |
| `RootAccessOnHost` | Adds root-level agent to host |
| `CriticalDataFound` | Records sensitive files found on a host |
| `VulnerableServiceFound` | Tags a port with a CVE identifier |
| `ExfiltratedData` | Tracks successfully stolen data |
| `ScanReportEvent` | Bulk-updates hosts and ports from nmap scan results |

This decoupling means actions are reusable and testable — they just emit events without knowing how the state gets updated.

### 5. How It's Long-Running

Three mechanisms control execution duration:

| Mechanism | Limit | Where |
|-----------|-------|-------|
| **Hard timeout** | 75 minutes | `incalmo_runner.py` (`TIMEOUT_SECONDS = 75 * 60`) |
| **Step limit** | 100 LLM turns | `LLMStrategy` (`self.total_steps = 100`) |
| **Celery tasks** | Async background | C2 server launches strategies as Celery tasks |

Each "step" can take anywhere from seconds (a query) to minutes (a network scan or exploit attempt). The frontend polls `/strategy_status/<id>` to track progress in real-time.

### 6. Abstraction Levels

The config's `abstraction` field controls what tools the LLM has:

| Level | What the LLM Can Do |
|-------|---------------------|
| `incalmo` | High-level actions: `Scan`, `LateralMove`, `FindInfo`, `PrivEsc`, `Exfiltrate` |
| `low_level_actions` | Only `RunBashCommand` — must craft all shell commands manually |
| `shell` | Raw `<bash>` tags — direct shell access, no framework |
| `agent_scan` | Only scanning capabilities |
| `agent_lateral_move` | Only lateral movement |
| `agent_privilege_escalation` | Only privilege escalation |
| `agent_exfiltrate_data` | Only data exfiltration |
| `agent_find_information` | Only host information gathering |
| `agent_all` | All agent-level capabilities |

Each level has its own system prompt (in `preprompts/`) that teaches the LLM what APIs are available. The research tests how different abstraction levels affect attack success rates.

---

## Docker Architecture

### Three Containers, Three Networks

| Container | Role | Networks |
|-----------|------|----------|
| **attacker** (Kali Linux) | Runs Incalmo + C2 server | `attacker_net` (192.168.199.x), `web_net` (192.168.200.x) |
| **webserver** | Vulnerable target application | `web_net` (192.168.200.x), `db_net` (192.168.201.x) |
| **db** | Database with sensitive data | `db_net` (192.168.201.x) |

```
attacker_net (199.x)     web_net (200.x)      db_net (201.x)
       │                      │                     │
  [attacker] ─────────── [webserver] ─────────── [db]
  192.168.199.10          192.168.200.20          192.168.201.100
  192.168.200.10          192.168.201.20
```

The attacker can reach the webserver but **not** the database directly — it must pivot through the webserver (realistic multi-stage attack simulation).

---

## C2 Server API Endpoints

The Flask server runs on port 8888 with 7 route blueprints:

### Agent Management (`agent_routes.py`)
- `POST /beacon` — Agent check-in, returns queued commands
- `GET /agents` — List all connected agents
- `DELETE /agent/delete/<paw>` — Kill agent
- `POST /agents/cleanup` — Remove stale agents

### Command Execution (`command_routes.py`)
- `POST /send_command` — Queue command for an agent
- `POST /send_manual_command` — Manual command execution
- `GET /command_status/<cmd_id>` — Poll command completion

### Strategy Management (`strategy_routes.py`)
- `POST /startup` — Launch strategy as Celery task
- `GET /strategy_status/<id>` — Check strategy progress
- `GET /task_status/<id>` — Check Celery task status
- `POST /cancel_strategy/<id>` — Terminate running strategy
- `GET /running_strategies` — List active strategies
- `GET /available_strategies` — List registered strategies

### Environment (`environment_routes.py`)
- `POST /update_environment_state` — Report infected hosts

### Logging (`logging_routes.py`)
- `POST /log_action` — Log action execution
- `GET /get_logs` — Retrieve logs
- `GET /get_actions` — Get action history

### LLM Agents (`llm_routes.py`)
- `GET /get_llm_agent_action` — Fetch queued LLM agent action
- `POST /submit_llm_agent_action` — Submit action result

---

## Configuration

### Environment Variables (`.env`)
```bash
ANTHROPIC_API_KEY=...    # Claude API
OPENAI_API_KEY=...       # GPT API
GOOGLE_API_KEY=...       # Gemini API
DEBUG=false
```

### Strategy Configuration (`config/config.json`)
```json
{
  "name": "test",
  "strategy": {
    "planning_llm": "haiku3_5_strategy",
    "execution_llm": "claude-3.5-haiku",
    "abstraction": "incalmo"
  },
  "environment": "EquifaxLarge",
  "c2c_server": "http://host.docker.internal:8888",
  "blacklist_ips": ["192.168.199.10"]
}
```

### Supported Environments
- `EquifaxSmall` / `EquifaxMedium` / `EquifaxLarge` — Equifax breach simulation
- `ICSEnvironment` — Industrial control systems
- `RingEnvironment` — Ring topology
- `EnterpriseA` / `EnterpriseB` — Multi-subnet enterprise networks

---

## Key Design Patterns

| Pattern | Where | Why |
|---------|-------|-----|
| **Strategy Pattern** | `incalmo_strategy.py` | Strategies auto-register via `__init_subclass__`, factory builds from config |
| **Event Sourcing** | `events/` + `environment_state_service.py` | Actions emit immutable events; state service consumes them to update network model |
| **Dynamic Code Execution** | `llm_strategy.py` | LLM generates Python code that's `exec()`'d at runtime |
| **Graph Traversal** | `graph_search.py` | BFS/DFS over network topology for deterministic strategies |
| **Service Layer** | `core/services/` | Clean separation: state management, attack graphs, action orchestration, logging |
| **Multi-Provider LLM** | `langchain_registry.py` | Swappable between OpenAI, Anthropic, Google, DeepSeek via LangChain |

---

## Execution Logs

Each run outputs to `output/<operation_id>/`:

| File | Content |
|------|---------|
| `llm.log` | LLM planning and reasoning (full conversation) |
| `llm_agent.log` | Agent-specific LLM sub-conversations |
| `actions.json` | Structured JSON action execution log |
| `bash_log` | Raw bash command history |
| `pre_prompt.log` | Initial LLM system prompt |

---

## End-to-End Data Flow

```
config.json
    │
    ▼
StrategyFactory.build_strategy()
    │
    ▼
strategy.initialize()
  - Fetch agents from C2 server
  - Build initial network model
    │
    ▼
┌─── Main Loop (75 min / 100 steps) ───┐
│                                        │
│  strategy.step()                       │
│    │                                   │
│    ├── [LLM Strategy]                  │
│    │   LLM sees: prompt + state +      │
│    │             conversation history   │
│    │   LLM writes: <query>/<action>/   │
│    │               <bash>/<finished>   │
│    │   Incalmo: exec()s the Python     │
│    │                                   │
│    └── [State Machine Strategy]        │
│        Follow BFS/DFS graph traversal  │
│        Execute hardcoded action chain  │
│                                        │
│  Actions emit Events                   │
│    │                                   │
│    ▼                                   │
│  EnvironmentStateService               │
│    - Consumes events                   │
│    - Updates Network model             │
│    - Merges hosts, tracks credentials  │
│                                        │
│  C2 reports updated state              │
│    │                                   │
│    ▼                                   │
│  Next step()                           │
└────────────────────────────────────────┘
    │
    ▼
Logs written to output/<operation_id>/
```

---

## Frontend Dashboard

The React frontend provides real-time monitoring:

- **Strategy Launcher** — Configure and start attack strategies
- **Running Strategies** — Monitor active strategies with status polling
- **Network Graph** — ReactFlow visualization of network topology (infected vs. clean hosts, subnets)
- **Timeline** — Chronological view of attack actions
- **Action Logs** — Detailed execution logs per action
- **LLM Logs** — Full LLM conversation history (reasoning visible)
- **Connected Agents** — List of deployed agents per host
