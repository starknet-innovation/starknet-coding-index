Implement a name registry contract in Cairo for Starknet. Each account (the caller) can register a single name for itself.

## Requirements

Package name: `registry` (already set in Scarb.toml).

Define a public interface trait `IRegistry` (annotated with `#[starknet::interface]`) with exactly these functions:

- `fn register(ref self: TContractState, name: felt252);` — stores `name` as the caller's name. If `name` is 0, it must panic with the short string `'Registry: empty name'`. If the caller already registered before, the new name overwrites the old one.
- `fn name_of(self: @TContractState, account: ContractAddress) -> felt252;` — returns the name registered by `account`, or 0 if that account never registered.
- `fn total_registered(self: @TContractState) -> u64;` — returns the number of unique accounts that have ever registered. It starts at 0, increases by 1 the first time a given account registers, and does NOT increase when an account overwrites its existing name.

Define a contract module named `Registry` (annotated with `#[starknet::contract]`) that implements `IRegistry` (the impl must be annotated with `#[abi(embed_v0)]`):

- Constructor: none required — the contract is deployed with no constructor arguments.
- Events (contract's `Event` enum variants, each a struct with the listed fields, in this order):
  - `Registered { account: ContractAddress, name: felt252 }` — emitted on every successful `register` call (including overwrites), where `account` is the caller and `name` is the name just stored.

Both the event struct and the trait must be public (`pub`).
