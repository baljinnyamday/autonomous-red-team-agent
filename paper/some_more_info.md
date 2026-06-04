35 Prompts to Payloads: Inside LLM-Driven Net- work Attacks
Supervisor(s): hamed haddadi h.hjaddadi@imperial.ac.uk, Al Sadi, Amir <a.al-sadi@imperial.
ac.uk> (PDRA)
Keywords: AI agents , networks, security
Project description: This project explores how large language models (LLMs) can coordinate real-
istic multi-host network attacks by extending existing open-source LLM-agent frameworks. Instead of
modifying the model itself, the work focuses on design- ing a middle layer that separates high-level reason-
ing from low-level execution. In this setup, the LLM proposes actions like reconnaissance, exploitation,
lateral movement, and data exfiltration; a planner reasons over the network’s state and possible attack
paths; and a translation layer turns those plans into concrete tool commands and system interactions.
The student will extend this architecture by experimenting with different planners (rule-based, heuris-
tic, or learning-guided), richer state tracking (confidence, uncertainty, or time-aware updates), and new
types of exploit or network interaction primitives. The goal is to understand which design choices make
the LLM more effective or reliable when operating in complex network environments. Experiments will
include controlled network simulations and ablation studies to measure factors such as success rate, com-
mand accuracy, and adaptability across different attack stages. The project’s main contribution will be
open, reproducible code and data showing how archi- tectural scaffolding – rather than model size alone –
affectsLLM-drivenattackperformance. ThisworkoffersararemixofAIagentengineering, cybersecurity
experimentation, and systems design, giving the student hands-on experience building and analyzing au-
tonomous attack pipelines. The results will deepen understanding of how intelligent agents interact with
real-world systems and what makes them succeed or fail in dynamic networked settings. 2 Internal, what
I expect from this project The student will look at repos like this one: https://github.com/bsinger98/
Incalmo?tab=readme-ov-file and paper: https://arxiv.org/pdf/2501.16466. Here is a breakdown of
what I expect from the project: 1. First step: the student is expected to give a brief presentation about
the code components and how they interact together. 2. Second step: build on top of the repository, e.g.
introduce a defense (firewall) and try and tweak the framework to break the defense. 3. Third step (if
there is time): extend the framework internal (e.g. state representation of attack - Fig. 3 of the paper)
to factor in attributes that the LLM might discover about the defense in place in the system. Ideally,
this will produce a short workshop paper with (hopefully) some practical tips on how to use LLMs in
networked adversarial context, when some defense is in place. There are more repos that the student can
use for code/inspiration:
https://github.com/JuliusHenke/autopentest https://github.com/zhrli324/Corba