Implement a reusable pausable **component** in Cairo for Starknet, plus a contract that embeds it. Everything lives in the single file `src/lib.cairo`.

Package name: `pausable_machine` (already set in Scarb.toml).

## Pausable interface

At the top level of the file, define a public interface trait `IPausable` (annotated with `#[starknet::interface]`) with exactly these functions:

- `fn is_paused(self: @TContractState) -> bool;` — returns whether the contract is currently paused.
- `fn pause(ref self: TContractState);` — pauses. If already paused, panic with the short string `'Pausable: paused'`.
- `fn unpause(ref self: TContractState);` — unpauses. If not paused, panic with `'Pausable: not paused'`.

## Component

Define a component module named `pausable_component` (annotated with `#[starknet::component]`) containing:

- Storage with a single field `paused: bool`.
- Events (component's `Event` enum variants, each a struct with the listed fields):
  - `Paused { by: ContractAddress }` — emitted on every successful `pause` (and it must be the only event emitted by that call); `by` is the caller.
  - `Unpaused { by: ContractAddress }` — emitted on every successful `unpause` (and it must be the only event emitted by that call); `by` is the caller.
- An embeddable impl of `IPausable` declared with `#[embeddable_as(Pausable)]` (so contracts can embed it as `pausable_component::Pausable<ContractState>`), implementing the behavior above.
- An internal (non-embedded) impl, generated with `#[generate_trait]` and declared `pub`, providing:
  - `fn assert_not_paused(self: @ComponentState<TContractState>);` — panics with `'Pausable: paused'` when paused, does nothing otherwise.

## Machine contract

At the top level of the file, define a public interface trait `IMachine` (annotated with `#[starknet::interface]`):

- `fn tick(ref self: TContractState) -> u64;` — increments a tick counter by 1 and returns the new value. It must first call the component's `assert_not_paused`, so it panics with `'Pausable: paused'` while paused.
- `fn get_ticks(self: @TContractState) -> u64;` — returns the current tick counter.

Define a contract module named `Machine` (annotated with `#[starknet::contract]`) that:

- Instantiates the component with exactly `component!(path: pausable_component, storage: pausable, event: PausableEvent);` (substorage field named `pausable`, contract `Event` enum variant named `PausableEvent`).
- The `PausableEvent` variant of the contract's `Event` enum **must be annotated with `#[flat]`**, so the component's events are emitted with the bare variant selectors (`Paused` / `Unpaused`) as keys.
- Embeds the component's `IPausable` impl in the contract ABI: `#[abi(embed_v0)] impl Pausable = pausable_component::Pausable<ContractState>;` — so `is_paused`/`pause`/`unpause` are callable on the deployed `Machine`.
- Implements `IMachine` in an impl annotated with `#[abi(embed_v0)]`, with a tick counter starting at 0.
- Takes no constructor arguments (omit the constructor or define one with no arguments). A freshly deployed `Machine` is unpaused with a tick counter of 0.

Both interface traits, the component's `Event` enum, and its event structs must be public (`pub`).
