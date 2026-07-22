Implement a time-locked escrow contract in Cairo for Starknet. The contract tracks internal credit balances only — no real token transfers are involved.

## Requirements

Package name: `escrow` (already set in Scarb.toml).

Define a public interface trait `IEscrow` (annotated with `#[starknet::interface]`) with exactly these functions:

- `fn deposit_for(ref self: TContractState, beneficiary: ContractAddress, amount: u128, unlock_time: u64) -> u64;` — records a new deposit for `beneficiary` and returns its deposit id. Ids are sequential starting at 1 (the first deposit has id 1, the second id 2, ...). If `amount` is 0, it must panic with the short string `'Escrow: zero amount'`. If `unlock_time` is less than or equal to the current block timestamp, it must panic with `'Escrow: bad unlock time'`.
- `fn withdraw(ref self: TContractState, deposit_id: u64);` — marks the deposit as withdrawn and releases its amount from the beneficiary's locked balance. If no deposit with that id exists, it must panic with `'Escrow: no deposit'`. Only the deposit's beneficiary may call this; any other caller must panic with `'Escrow: not beneficiary'`. Withdrawal is allowed only once the current block timestamp is greater than or equal to the deposit's `unlock_time`; before that it must panic with `'Escrow: locked'`. If the deposit was already withdrawn, it must panic with `'Escrow: already withdrawn'`.
- `fn get_deposit(self: @TContractState, deposit_id: u64) -> (ContractAddress, u128, u64, bool);` — returns the deposit as `(beneficiary, amount, unlock_time, withdrawn)`. If no deposit with that id exists, it must panic with `'Escrow: no deposit'`.
- `fn balance_of(self: @TContractState, beneficiary: ContractAddress) -> u128;` — returns the total amount currently locked for `beneficiary`, i.e. the sum of all their deposits that have not yet been withdrawn. It increases on `deposit_for` and decreases on `withdraw`.

Define a contract module named `Escrow` (annotated with `#[starknet::contract]`) that implements `IEscrow` (the impl must be annotated with `#[abi(embed_v0)]`):

- The contract takes no constructor arguments (it is deployed with empty calldata).
- Events (contract's `Event` enum variants, each a struct with the listed fields, in this order):
  - `Deposited { id: u64, depositor: ContractAddress, beneficiary: ContractAddress, amount: u128, unlock_time: u64 }` — emitted on every successful `deposit_for`; `depositor` is the caller.
  - `Withdrawn { id: u64, beneficiary: ContractAddress, amount: u128 }` — emitted on every successful `withdraw`.

Both event structs and the trait must be public (`pub`).
