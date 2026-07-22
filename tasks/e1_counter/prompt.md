Implement a counter contract in Cairo for Starknet.

## Requirements

Package name: `counter` (already set in Scarb.toml).

Define a public interface trait `ICounter` (annotated with `#[starknet::interface]`) with exactly these functions:

- `fn get(self: @TContractState) -> u64;` — returns the current counter value.
- `fn increment(ref self: TContractState, amount: u64);` — increases the counter by `amount`.
- `fn decrement(ref self: TContractState, amount: u64);` — decreases the counter by `amount`. If `amount` is greater than the current value, it must panic with the short string `'Counter: underflow'`.

Define a contract module named `Counter` (annotated with `#[starknet::contract]`) that implements `ICounter` (the impl must be annotated with `#[abi(embed_v0)]`):

- Constructor: `fn constructor(ref self: ContractState, initial: u64)` — sets the initial counter value.
- Events (contract's `Event` enum variants, each a struct with the listed fields, in this order):
  - `Incremented { amount: u64, new_value: u64 }` — emitted on every successful `increment`.
  - `Decremented { amount: u64, new_value: u64 }` — emitted on every successful `decrement`.

Both event structs and the trait must be public (`pub`).
