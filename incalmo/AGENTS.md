## Learned User Preferences
- Prefers quick architectural explanations of specific code folders/classes before deep implementation work.
- Often asks for visual architecture/main-loop diagrams to understand system behavior.
- Expects continual-learning updates to use strict incremental transcript processing with the workspace index.
- Asks for plain-language re-explanations when a technical answer does not land.

## Learned Workspace Facts
- Strategy selection is config-driven via `StrategyFactory`, with both LLM (`LLMStrategyConfig`) and state-machine (`StateMachineStrategy`) paths.
- The LLM path relies on tag-parsed responses (`<query>`, `<action>`, `<mediumAction>`, `<bash>`, `<finished>`) rather than native LangChain tool calling.
- Runtime topology and compromise state are tracked in `EnvironmentStateService`/`Network` and mirrored to C2 for UI/state reporting.
- At startup, `EnvironmentInitializer` maps `AttackerConfig.environment` to the initial `Network`: known subnet CIDRs only (empty of hosts until discovery); ICS/Ring start with none.
