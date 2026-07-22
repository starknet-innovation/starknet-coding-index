Implement a vault contract with owner-based access control in Cairo for Starknet.

## Requirements

Package name: `ownable` (already set in Scarb.toml).

Define a public interface trait `IVault` (annotated with `#[starknet::interface]`) with exactly these functions:

- `fn get_owner(self: @TContractState) -> ContractAddress;` — returns the current owner.
- `fn get_value(self: @TContractState) -> u128;` — returns the stored value (0 until first set).
- `fn set_value(ref self: TContractState, value: u128);` — stores `value`. Only the current owner may call it; any other caller must panic with the short string `'Vault: not owner'`.
- `fn transfer_ownership(ref self: TContractState, new_owner: ContractAddress);` — transfers ownership to `new_owner`. Only the current owner may call it; any other caller must panic with `'Vault: not owner'`. If `new_owner` is the zero address, it must panic with `'Vault: zero owner'`. On success the new owner immediately gains (and the previous owner loses) all owner-only rights.

Define a contract module named `Vault` (annotated with `#[starknet::contract]`) that implements `IVault` (the impl must be annotated with `#[abi(embed_v0)]`):

- Constructor: `fn constructor(ref self: ContractState, owner: ContractAddress)` — sets the initial owner.
- Events (contract's `Event` enum variants, each a struct with the listed fields, in this order):
  - `OwnershipTransferred { previous: ContractAddress, new: ContractAddress }` — emitted on every successful `transfer_ownership`, where `previous` is the owner before the transfer and `new` is the owner after.

Both the event struct and the trait must be public (`pub`).
