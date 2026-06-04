# Literature Review — LLM-based Agentic AI for Offensive Security

**Scope:** Autonomous LLM agents that plan and execute offensive-security tasks — penetration testing, vulnerability exploitation, and CTF solving — including their agent architectures (single-agent loops, multi-agent orchestration, tool use), reported capabilities, and limitations.

**Compiled:** 2026-05-30 · **Mode:** ARS `deep-research` lit-review · **Total sources:** 13 (8 independently verified against arXiv, 5 search-corroborated)

> **Referencing note:** `task.md` specifies **Vancouver** for the Background Report, but `main.tex` currently sets `\bibliographystyle{apa}`. Entries below give author–year *and* a suggested BibTeX key so they drop into either scheme. Reconcile the style before submission.

---

## 1. Search Strategy (for reproducibility)

| Parameter | Value |
|-----------|-------|
| Databases / sources | arXiv, Semantic Scholar, USENIX, ICLR/OpenReview, ScienceDirect, MDPI, ACL Anthology |
| Date range | 2022–2026 (justification: the agentic-LLM offensive-security literature is almost entirely post-GPT-4) |
| Primary keywords | "LLM agent" · "autonomous penetration testing" · "exploit vulnerabilities" · "CTF" · "red teaming" · "multi-agent" · "offensive security" · "dangerous capability evaluation" |
| Boolean pattern | (LLM OR "language model") AND (agent OR multi-agent) AND (pentest* OR exploit* OR "capture the flag" OR "red team*" OR "offensive security") |
| Document types | Peer-reviewed papers, arXiv preprints, frontier-lab/government evaluation reports |
| Inclusion | Directly addresses autonomous/agentic LLMs performing offensive tasks; reports capability or evaluation evidence |
| Exclusion | LLM *defensive* use only; prompt-injection-of-agents (orthogonal); non-agentic single-prompt LLM use; predatory venues |
| Verification | arXiv abstract pages fetched for the 8 core sources; authors/title/year/venue confirmed |

**Verification legend:** ✓ = metadata independently confirmed via source page · ◐ = corroborated by search result only (treat as provisional until you open it).

---

## 2. Annotated Bibliography

### Theme A — Single-agent penetration-testing pipelines

**✓ Deng, G., Liu, Y., Mayoral-Vilches, V., Liu, P., Li, Y., Xu, Y., Zhang, T., Liu, Y., Pinzger, M., & Rass, S. (2023). *PentestGPT: An LLM-empowered Automatic Penetration Testing Tool.* arXiv:2308.06782.** `[deng2023pentestgpt]`
The foundational work. Finds vanilla LLMs excel at isolated sub-tasks but lose context across a full engagement, then introduces a three-module design (Reasoning / Generation / Parsing self-interacting modules) to preserve testing state. Reports a 228.6% task-completion improvement over a GPT-3 baseline. Widely treated as the reference baseline that subsequent agents benchmark against.

**◐ Muzsai, L., Imolai, D., & Lukács, A. (2024). *HackSynth: LLM Agent and Evaluation Framework for Autonomous Penetration Testing.* arXiv:2412.01778.** `[muzsai2024hacksynth]` *(✓ verified)*
A minimal **Planner + Summarizer** loop that iteratively issues commands and digests feedback. Contributes two CTF-based benchmarks (200 challenges over PicoCTF / OverTheWire) and an evaluation harness — notable for foregrounding *reproducible evaluation* rather than just a new agent.

**◐ Liu, et al. (2024). *PentestAgent: Incorporating LLM Agents into Automated Penetration Testing.* arXiv:2411.05185.** `[pentestagent2024]`
Claims to outperform PentestGPT in both effectiveness and efficiency while removing the human-in-the-loop assistance PentestGPT still required. *(Metadata search-corroborated; open the PDF to confirm author list before citing.)*

**◐ *AutoPentest: Enhancing Vulnerability Management with Autonomous LLM Agents.* (2025). arXiv:2505.10321** `[autopentest2025]` **and *AutoPentester: An LLM Agent-based Framework for Automated Pentesting.* (2025). arXiv:2510.05605** `[autopentester2025]`
Two distinct 2025 systems (note the near-identical names). AutoPentest builds black-box testing on GPT-4o + LangChain; AutoPentester reports +27.0% subtask completion and +39.5% vulnerability coverage over PentestGPT with fewer steps and less human interaction. Useful as the "current frontier" of the single-agent line.

### Theme B — Autonomous vulnerability discovery & exploitation

**✓ Fang, R., Bindu, R., Gupta, A., & Kang, D. (2024). *LLM Agents can Autonomously Exploit One-day Vulnerabilities.* arXiv:2404.08144.** `[fang2024oneday]`
Benchmark of 15 real-world one-day CVEs (websites, container software, Python packages). **GPT-4 exploits 87%** *with* the CVE description vs **0%** for GPT-3.5, open-source LLMs, and scanners (ZAP, Metasploit); drops to **7%** *without* the description. The key empirical evidence that *exploitation* is far easier for current agents than *discovery*.

**✓ Zhu, Y., Kellermann, A., Gupta, A., Li, P., Fang, R., Bindu, R., & Kang, D. (2024). *Teams of LLM Agents can Exploit Zero-Day Vulnerabilities.* arXiv:2406.01637.** `[zhu2024zeroday]`
Introduces **HPTSA** — a hierarchical planner that spawns specialised sub-agents — to overcome the long-horizon-planning and exploration limits of single agents. Hacks >50% of a 14-vuln zero-day benchmark and improves over prior single-agent frameworks by up to **4.3×**. The pivotal "multi-agent beats single-agent" result.

**◐ *CVE-Bench: A Benchmark for AI Agents' Ability to Exploit Real-World Web Application Vulnerabilities.* (2025). arXiv:2503.17332.** `[cvebench2025]`
A reproducible, sandboxed benchmark of real web-app CVEs — addresses the criticism that earlier exploitation results used small, ad-hoc datasets.

### Theme C — Multi-agent orchestration for offensive security

**✓ Udeshi, M., Shao, M., Xi, H., Rani, N., Milner, K., Putrevu, V. S. C., Dolan-Gavitt, B., Shukla, S. K., Krishnamurthy, P., Khorrami, F., Karri, R., & Shafique, M. (2025). *D-CIPHER: Dynamic Collaborative Intelligent Multi-Agent System with Planner and Heterogeneous Executors for Offensive Security.* arXiv:2502.10931.** `[udeshi2025dcipher]`
Models a CTF *team*: a Planner plus heterogeneous Executor agents and an auto-prompter. State-of-the-art across three benchmarks (+2.5–8.5%) and exercises **65% more MITRE ATT&CK techniques** than prior work — evidence that role specialisation broadens behavioural coverage, not just success rate.

**◐ *Co-RedTeam: Orchestrated Security Discovery and Exploitation with LLM Agents.* (2026). arXiv:2602.02164.** `[coredteam2026]`
Security-aware multi-agent framework separating **discovery** and **exploitation** stages with execution-grounded iterative reasoning and long-term memory; reports >60% exploitation success. *(Future-dated arXiv ID — verify it resolves before relying on it.)*

### Theme D — Benchmarks & capability evaluation

**✓ Zhang, A. K., Perry, N., Dulepet, R., … Boneh, D., Ho, D. E., & Liang, P. (2024). *Cybench: A Framework for Evaluating Cybersecurity Capabilities and Risks of Language Models.* arXiv:2408.08926. (ICLR 2025 Oral).** `[zhang2024cybench]`
The most rigorous open evaluation: **40 professional CTF tasks** with human-annotated subtasks across all six CTF categories, run over eight models (GPT-4o, Claude family, etc.). Top models autonomously solve tasks that take humans hours. Its open-source nature is positioned explicitly against the closed evals of OpenAI / AI Safety Institutes.

**◐ *Towards Effective Offensive Security LLM Agents: Hyperparameter Tuning, LLM-as-a-Judge, and a Lightweight CTF Benchmark.* (2025). arXiv:2508.05674.** `[offsec2025tuning]`
Argues much of the measured capability variance is from *harness/hyperparameter* choices rather than the base model — an important methodological caveat for anyone comparing agent results.

**◐ *CAIBench: A Meta-Benchmark for Evaluating Cybersecurity AI Agents.* (2025). arXiv:2510.24317.** `[caibench2025]`
A "benchmark of benchmarks" attempting to standardise the now-fragmented evaluation landscape.

### Theme E — Frontier-model risk, governance & survey

**✓ Phuong, M., Aitchison, M., Catt, E., … Shah, R., Dafoe, A., & Shevlane, T. (2024). *Evaluating Frontier Models for Dangerous Capabilities.* arXiv:2403.13793. (Google DeepMind).** `[phuong2024dangerous]`
Pre-deployment dangerous-capability evaluations of Gemini 1.0 across four areas including **cyber-offense**. Finds "no strong dangerous capabilities" yet but documents "early warning signs" — the methodological anchor for governance-oriented framing.

**◐ *Dynamic Risk Assessments for Offensive Cybersecurity Agents.* (2025). arXiv:2505.18384.** `[dynamicrisk2025]`
Argues static one-shot audits understate risk because real adversaries have many "degrees of freedom" (retries, tool swaps, fine-tuning) — motivates *adaptive* evaluation.

**◐ Xu, M., Fan, J., Huang, X., et al. (2025). *Forewarned is Forearmed: A Survey on Large Language Model-based Agents in Autonomous Cyberattacks.* arXiv:2505.12786.** `[xu2025survey]` *(✓ verified)*
The most directly relevant survey: taxonomy of agent capabilities (scouting, memory, reasoning, action), attack types across network paradigms, defenses, and the "Cyber Threat Inflation" thesis (AI lowers attacker cost while raising attack scale). **Best single anchor citation for your background chapter's framing.**

---

## 3. Literature Matrix (Source × Theme)

| Source | Year | Type | T-A Single-agent | T-B Exploit | T-C Multi-agent | T-D Eval | T-E Risk/Gov |
|--------|------|------|:---:|:---:|:---:|:---:|:---:|
| PentestGPT (Deng) | 2023 | Method | ✓ core | — | — | ◐ | — |
| HackSynth | 2024 | Method+Bench | ✓ | — | — | ✓ | — |
| PentestAgent | 2024 | Method | ✓ | — | — | — | — |
| AutoPentest(er) | 2025 | Method | ✓ | ✓ | — | — | — |
| Fang — One-day | 2024 | Empirical | — | ✓ core | — | ◐ | ✓ |
| Zhu — Zero-day/HPTSA | 2024 | Method+Empirical | — | ✓ core | ✓ core | ◐ | ✓ |
| CVE-Bench | 2025 | Benchmark | — | ✓ | — | ✓ | — |
| D-CIPHER | 2025 | Method | — | ✓ | ✓ core | ✓ | — |
| Co-RedTeam | 2026 | Method | — | ✓ | ✓ | ◐ | — |
| Cybench | 2024 | Benchmark | — | — | — | ✓ core | ✓ |
| Offsec tuning | 2025 | Methodology | ✓ | — | — | ✓ | — |
| Phuong — Dangerous Caps | 2024 | Evaluation | — | — | — | ✓ | ✓ core |
| Xu — Survey | 2025 | Survey | ✓ | ✓ | ✓ | ✓ | ✓ |

### Evidence-convergence summary

| Theme | Supporting sources | Strength | Confidence |
|-------|:---:|----------|-----------|
| Agentic scaffolding (plan→act→observe loops) beats raw prompting | 7 | **Strong** | High |
| Multi-agent > single-agent for long-horizon offensive tasks | 4 | **Moderate–Strong** | Medium–High |
| Exploiting a *known* vuln ≫ *discovering* an unknown one | 3 | **Strong** | High |
| Measured capability is highly sensitive to harness/hyperparameters | 2 | **Emerging** | Medium |
| Current frontier models show "early warning signs," not full autonomy | 3 | **Moderate** | Medium (recency-sensitive) |

---

## 4. Thematic Synthesis

**The field crystallised around one diagnosis.** PentestGPT (2023) framed the core problem that every later paper inherits: LLMs are locally competent but lose the *global state* of a multi-step engagement. Essentially all subsequent architecture — planners, summarizers, memory, sub-agents — is a response to that context-management failure. For a Background chapter, this is the clean narrative spine: *the offensive-agent literature is the story of bolting long-horizon structure onto a strong but stateless reasoner.*

**Capability evidence converges, with one sharp boundary.** Independent results agree that scaffolded agents materially outperform vanilla prompting, and Fang et al. (2024) draw the field's most important line: GPT-4 exploited **87%** of one-day vulnerabilities *with* a CVE description but only **7%** without. Discovery, not exploitation, is the binding constraint. Zhu et al. (2024) then show the constraint is partly architectural — a hierarchical planner-with-subagents (HPTSA) recovers much of the lost ground on zero-days (>50%, up to 4.3× over single agents), a result D-CIPHER (2025) reinforces by tying multi-agent role specialisation to **65% broader ATT&CK technique coverage**. The convergent claim: *division of labour buys both success rate and behavioural breadth.*

**Evaluation is maturing faster than the agents.** Cybench (ICLR 2025) set the methodological bar — open, subtask-annotated, multi-model. But a counter-current (the hyperparameter-tuning paper; the dynamic-risk-assessment paper) warns that headline numbers are fragile: results swing with harness configuration, and static audits understate adversaries who can retry and adapt. This is the most useful *tension* to surface in your review — the field does not yet agree on what a capability measurement even means.

**Governance framing is converging on "not yet, but soon."** DeepMind's dangerous-capability evals (Phuong et al., 2024) and the 2025 survey both land on "early warning signs / threat inflation" rather than present-day autonomous catastrophe. This gives your introduction a defensible, non-alarmist stance: capabilities are rising and cost-asymmetry favours attackers, but end-to-end autonomous compromise of hardened targets is not yet demonstrated.

---

## 5. Research Gaps (candidate openings for your contribution)

1. **Discovery, not exploitation.** The 87%→7% cliff means *autonomous vulnerability discovery* is the open frontier. Most "success" depends on a human-supplied CVE.
2. **Harness-vs-model confound.** Reported gains conflate scaffold engineering with base-model capability; few papers ablate this cleanly. A controlled study isolating loop/tool design from model choice is under-served.
3. **Evaluation realism.** Benchmarks lean on CTFs and curated CVEs; **realistic, multi-host, networked engagements with proper scoping** (exactly your `be/` red-team setup) are rare. Static, single-shot evaluation under-measures adaptive adversaries.
4. **Reproducibility & cost accounting.** Token cost, prompt-cache behaviour, and run-to-run variance are rarely reported — yet your codebase already instruments usage/cache/cost, a natural methodological contribution.
5. **Safe-by-construction authorization.** Almost no work formalises *scope enforcement* (your `AUTHORIZED_ENGAGEMENT` gate). Dual-use governance is discussed abstractly but seldom built into the agent loop.
6. **Multi-agent overhead.** Multi-agent systems win on capability but their *cost/latency/coordination* trade-offs vs a well-tuned single agent are largely unquantified.

---

## 6. Limitations of this review

- **Recency & velocity.** This is a fast-moving area; several entries are 2025–2026 preprints not yet peer-reviewed (Tier 2 evidence). Re-run the search near submission.
- **Verification depth.** Eight sources were confirmed against their source pages (✓); five (◐) rest on search-result metadata and must be opened before citation. Per the review protocol, a ◐ that you cannot open should be dropped, not softened.
- **Search-engine bias.** Results were US-region web search + arXiv-weighted; closed-venue or non-English work may be under-represented.
- **No quantitative meta-analysis.** Heterogeneous benchmarks preclude pooled effect sizes; this is a narrative synthesis.

## 7. AI-use disclosure

This literature review was produced with AI assistance (Claude, via the `academic-research-skills` deep-research pipeline). The AI performed the literature search, source verification against arXiv, and drafting. All sources marked ◐ require human confirmation; all marked ✓ were checked against their arXiv abstract pages during compilation but should still be read in full before citation. The author is responsible for final verification and integration.
