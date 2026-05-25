# Behavior, Environment, and Interaction Boundary

> Status: **specification and guardrail doctrine** for `v0.4.3 / BEHAVIOR-SPEC-1`.
> This document defines future architecture. It does **not** describe implemented
> runtime capability. No interaction or environment package is implemented in
> `v0.4.3`.

## 1. Purpose

This document is the authoritative boundary doctrine for SightStalker's future
behavior, environment-profile, context-initialization, and interaction-activation
work. It is written before implementation so that `ENVIRONMENT-1`,
`CONTEXT-INITIALIZER-1`, `INTERACTION-1`, and `INTERACTION-WIRING-1` can proceed
through the accepted `sightstalker.ops` composition boundary without polluting
engines, sessions, persistence, or CLI modules, and without re-litigating
activation defaults or resolver precedence.

It specializes — and does not contradict — the broader package architecture
described in `README.md`. Where the README and this document both discuss the
engine, session, and ops boundaries, the README is the broader source and this
document is the behavior/environment/interaction specialization. This document
is the single source for behavior/environment/interaction doctrine; other
documents should cite it rather than restating its rules.

## 2. Current status in v0.4.3

> Update (v0.4.4 / ENVIRONMENT-1): the `environment` package, `EnvironmentProfile`
> / `NavigatorProfile` contracts, programmatic null/in-memory stores, selectors,
> the default applicator, and the `ContextConfigResolver` (with binding
> precedence `run override > selected environment profile > session default >
> package default`) are now implemented and composed optionally through `ops`
> before engine launch. `ContextInitializer`, the interaction package, CLI
> activation flags, file-backed profile stores, and a persistent profile
> registry remain future. No fingerprint generation, proxy rotation, navigator
> injection, or behavior simulation is implemented. The internal
> `FingerprintProfile` alias is non-public legacy naming debt; `FingerprintProfileId`
> / `fp_` prefixes are legacy accepted ID naming, not fingerprint capability.
> `user_agent` and `environment_profile_id` are identity-adjacent, non-secret
> metadata now persisted in `config_json` (flagged for SECURITY-REVIEW-1).

> Update (v0.4.5 / CONTEXT-INITIALIZER-1): `ContextInitializer`,
> `ContextInitializationScope`, and `ContextInitializerChain` are now implemented
> in `sightstalker.ops` as the ordered post-context/pre-page initializer seam. It
> is a trusted programmatic extension seam, not a sandbox. It ships no
> package-provided concrete initializer and provides no file/CLI/DB/remote
> initializer loading. It does not implement concrete browser mutation behavior,
> does not apply `NavigatorProfile` metadata, and does not create pages,
> navigate, inject scripts, start tracing, capture storage state, or persist
> metadata. The chain runs after `BrowserRuntime.new_context()` returns a
> `BrowserContextHandle` and before the plan is invoked; the empty chain is a
> no-op that preserves v0.4.4 behavior exactly. Concrete context initializers,
> `NavigatorProfile` application / script injection, the interaction package, and
> CLI activation flags remain future.

As of `v0.4.3`, the following are true:

- No `sightstalker.interaction` package exists.
- No `sightstalker.environment` package exists.
- No interaction simulator, environment profile model, context resolver, or
  context initializer exists as a production symbol.
- No CLI flag activates behavior, interaction, seeds, or environment selection.
- Engines remain browser launch/runtime/context/page adapters only.
- `sightstalker.ops` remains the managed-run composition root established by
  `OPS-BOUNDARY-1`.
- The names in the status matrix below are **documentation-only future
  concepts** and are intentionally not importable production symbols.

## 3. Current-vs-future status matrix

| Concept | v0.4.3 Status | Future Owner | First Allowed PR |
|---|---|---|---|
| `ContextConfigResolver` | Implemented (ENVIRONMENT-1) | `environment` + `ops` wiring | `ENVIRONMENT-1` |
| `ContextInitializer` | Implemented (CONTEXT-INITIALIZER-1) | `ops` | `CONTEXT-INITIALIZER-1` |
| `ContextInitializerChain` | Implemented (CONTEXT-INITIALIZER-1); ships no concrete initializer | `ops` | `CONTEXT-INITIALIZER-1` |
| `EnvironmentProfile` | Implemented (ENVIRONMENT-1) | `environment` | `ENVIRONMENT-1` |
| `FingerprintProfile` | Internal non-public alias only | `environment` | `ENVIRONMENT-1` |
| `InteractionProfile` | Not implemented | `interaction` | `INTERACTION-1` |
| `InteractionActivation` | Not implemented | `interaction` | `INTERACTION-1` |
| `InteractionSimulator` | Not implemented | `interaction`; wired by `ops` | `INTERACTION-1` / `INTERACTION-WIRING-1` |
| `PageInteractionTarget` | Not implemented | `interaction` | `INTERACTION-1` |
| CLI activation flags | Not implemented | `cli` parses; `ops` wires | `CLI-OPT-IN-1` |

## 4. Package boundary contract

```text
engines:
  Browser launch, runtime, context, and page adapter behavior only.
  Must not import ops, interaction, environment, cli, persistence, or diagnostics.
  Engine protocols (BrowserEngine, BrowserRuntime, BrowserContextHandle,
  PageHandle) must not gain interaction/profile/initialization methods.

sessions:
  Lifecycle, profile locks, storage-state snapshots, and managed context
  cleanup only. Must not import interaction, environment, or cli. Must not
  select profiles or construct future behavior objects.

ops:
  Composition root for future resolvers, initializers, factories, and run
  execution. ops is the composition root, not the implementation home. ops
  wires accepted implementations from the environment and interaction packages
  into managed runs only after those packages exist.

environment:
  Future package for environment/fingerprint profile definitions, stores,
  selectors, applicators, and pre-launch config resolution.

interaction:
  Future package for deterministic, opt-in interaction simulation against a
  narrow page-shaped protocol.

cli:
  Operator command parsing and rendering only. CLI must not directly construct
  environment/interaction implementation objects; it delegates construction and
  wiring to ops.

persistence:
  Metadata/provenance storage only. Persistence never resolves, applies,
  merges, or activates behavior/environment profiles.
```

## 5. Behavior vs environment profile separation

Interaction profiles are not environment profiles. They are distinct concepts
owned by distinct future packages:

- An **environment profile** describes *what the browser context looks like* —
  fingerprint-shaped and context/launch configuration resolved before launch.
  Environment/fingerprint profiles are owned by the future `environment`
  package.
- An **interaction profile** describes *how a plan interacts with a page* —
  deterministic, opt-in timing and movement behavior. Interaction profiles are
  owned by the future `interaction` package.

These must never be merged into a single model, and neither may be owned by
engines, sessions, persistence, or cli.

## 6. Behavior activation doctrine

```text
Behavior is opt-in.
Behavior is disabled by default.
Presence of an InteractionProfile alone does not activate behavior.
Activation requires an explicit activation field (a future InteractionActivation),
  never mere profile presence.
Interaction simulator construction happens only in ops, only when activation is
  explicitly requested, and only after the interaction package exists.
```

## 7. Seed determinism doctrine

```text
Deterministic behavior requires an explicit seed.
Missing seed in deterministic mode is a validation error.
The default interaction mode is seeded deterministic only.
Nondeterministic interaction mode is deferred and out of scope until a concrete
  operator requirement justifies it.
```

## 8. Future ContextConfigResolver contract

`ContextConfigResolver` is a future pre-launch resolver. It is documentation-only
in `v0.4.3`.

```text
Environment profiles are resolved before engine launch by a future
  ContextConfigResolver.
ContextConfigResolver precedence is:
  run override > selected environment profile > session default > package default.
Resolver output is an immutable effective BrowserLaunchConfig and
  BrowserContextConfig copy.
Engines receive already-resolved BrowserLaunchConfig and BrowserContextConfig;
  engines never perform environment resolution themselves.
```

The resolver is composed through `ops`; its implementation belongs to the future
`environment` package.

## 9. Future ContextInitializer contract

`ContextInitializer` is a future post-context/pre-page chain. It is
documentation-only in `v0.4.3`.

```text
ContextInitializer runs after BrowserRuntime.new_context() returns a
  BrowserContextHandle and before BrowserContextHandle.new_page() is used by a
  plan.
The initializer chain is composed and ordered through ops, not engines, not
  sessions, and not cli.
```

## 10. Future PageInteractionTarget bounds

`PageInteractionTarget` is a future narrow page-shaped protocol. It is
documentation-only in `v0.4.3` and must be **narrower** than `PageHandle`.

```text
Future PageInteractionTarget does not expose, by default:
  - navigation,
  - raw context/runtime access,
  - storage-state access,
  - network interception,
  - credential handling,
  - engine-specific native objects.
Interaction simulation works against this future narrow page-shaped protocol,
  not against engine-specific types.
```

## 11. Future interaction package contract

The future `sightstalker.interaction` package will own `InteractionProfile`,
`InteractionActivation`, `InteractionSimulator`, timing distributions, seeded
timing strategy, mouse movement strategies, and `PageInteractionTarget`. It must
keep behavior opt-in and seeded-deterministic by default, and must depend only
on a narrow page-shaped protocol rather than engine-specific types. It is first
allowed in `INTERACTION-1`; ops wiring is first allowed in `INTERACTION-WIRING-1`.

## 12. Future environment package contract

The future `sightstalker.environment` package will own `EnvironmentProfile`,
`FingerprintProfile`, profile stores, selectors, applicators, and
`ContextConfigResolver`. It produces immutable effective configuration consumed
by engines via ops; it never mutates engine or session internals directly. It is
first allowed in `ENVIRONMENT-1`.

## 13. Persistence boundary doctrine

```text
Persistence may store metadata/provenance only.
Persistence never resolves, applies, merges, or activates behavior/environment
  profiles.
Future activation/provenance metadata, when added, is recorded as data only and
  carries no resolution or activation logic.
```

## 14. Source-shape guardrails

This doctrine is enforced by guardrail tests under `tests/architecture/`. Each
guard is labeled in its docstring as one of:

```text
PERMANENT
  Durable architecture invariant. A later PR may not relax it without an
  explicit architecture-change PR.

SNAPSHOT-v0.4.3
  Current-state guard. A named future PR may intentionally relax it when
  implementing the projected capability.
```

PERMANENT guards include: engines do not import ops/interaction/environment/
cli/persistence/diagnostics; engine protocols gain no interaction/profile/init
methods; sessions do not import interaction/environment/cli; sessions do not
own future profile/interaction selection; CLI does not directly construct
future environment/interaction implementation objects; ops is the composition
root and not the implementation home.

SNAPSHOT-v0.4.3 guards include: ops does not yet import interaction/environment;
cli does not yet import interaction/environment; the future package directories
are absent; future documentation-only names are not importable production
symbols. These are relaxed by the named future PRs in the status matrix.

Each guard checker carries a synthetic self-test proving it fails when violated.

## 15. Explicit non-goals

```text
- No interaction simulator in v0.4.3.
- No environment/fingerprint profile model in v0.4.3.
- No context resolver or context initializer production symbol in v0.4.3.
- No CLI activation flags in v0.4.3.
- No browser behavior, engine protocol, session lifecycle, RunSurface, or
  persistence schema change in v0.4.3.
- No stealth, evasion, CAPTCHA-solving, anti-fraud bypass, fingerprint
  generation, proxy rotation, or scraping-abuse capability. SightStalker is an
  authorized-use automation toolkit; these are explicit non-goals, not features.
```

## 16. Downstream projected PR sequence

Projected default sequence, subject to future Q0 review:

```text
v0.4.3  BEHAVIOR-SPEC-1          specification and guardrails (this PR)
v0.4.4  ENVIRONMENT-1            environment profile contracts and resolver
v0.4.5  CONTEXT-INITIALIZER-1    post-context/pre-page initializer chain
v0.5.0  INTERACTION-1            deterministic interaction core package
v0.5.1  INTERACTION-WIRING-1     opt-in simulator factory and ops injection
v0.5.2  CLI-OPT-IN-1             narrow operator activation flags
v0.5.3  PROFILE-STORES-1         file-backed custom profile stores
v0.5.4  BOUNDARY-HARDENING-1     broader durable import/policy guardrails
```
