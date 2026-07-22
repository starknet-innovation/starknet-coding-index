Implement a capped, mintable ERC20-like token contract in Cairo for Starknet, written from scratch (do NOT use OpenZeppelin or any external library).

## Requirements

Package name: `erc20_capped` (already set in Scarb.toml).

Define a public interface trait `ICappedToken` (annotated with `#[starknet::interface]`) with exactly these functions:

- `fn name(self: @TContractState) -> felt252;` — returns the token name.
- `fn symbol(self: @TContractState) -> felt252;` — returns the token symbol.
- `fn decimals(self: @TContractState) -> u8;` — always returns 18.
- `fn total_supply(self: @TContractState) -> u256;` — total amount minted so far.
- `fn cap(self: @TContractState) -> u256;` — the maximum total supply.
- `fn balance_of(self: @TContractState, account: ContractAddress) -> u256;` — balance of `account`.
- `fn allowance(self: @TContractState, owner: ContractAddress, spender: ContractAddress) -> u256;` — remaining amount `spender` may transfer on behalf of `owner`.
- `fn mint(ref self: TContractState, to: ContractAddress, amount: u256);` — creates `amount` new tokens for `to` and increases the total supply. Only the minter address (set in the constructor) may call this; any other caller must panic with the short string `'ERC20: not minter'`. If `total_supply + amount` would exceed the cap, it must panic with `'ERC20: cap exceeded'` (minting exactly up to the cap is allowed). Emits a `Transfer` event with `from` set to the zero address.
- `fn transfer(ref self: TContractState, to: ContractAddress, amount: u256) -> bool;` — moves `amount` from the caller to `to` and returns `true`. If the caller's balance is less than `amount`, it must panic with `'ERC20: insufficient bal'`. Emits a `Transfer` event.
- `fn approve(ref self: TContractState, spender: ContractAddress, amount: u256) -> bool;` — sets the caller's allowance for `spender` to `amount` (overwriting any previous value) and returns `true`. Emits an `Approval` event.
- `fn transfer_from(ref self: TContractState, from: ContractAddress, to: ContractAddress, amount: u256) -> bool;` — moves `amount` from `from` to `to` using the caller's allowance, and returns `true`. If the caller's allowance from `from` is less than `amount`, it must panic with `'ERC20: insufficient allow'`; if `from`'s balance is less than `amount`, it must panic with `'ERC20: insufficient bal'`. On success the caller's allowance is decreased by `amount`. Emits a `Transfer` event with the given `from` and `to`.

Define a contract module named `CappedToken` (annotated with `#[starknet::contract]`) that implements `ICappedToken` (the impl must be annotated with `#[abi(embed_v0)]`):

- Constructor: `fn constructor(ref self: ContractState, name: felt252, symbol: felt252, cap: u256, minter: ContractAddress)` — stores the token name, symbol, supply cap, and the address allowed to mint. The initial total supply is zero.
- Events (contract's `Event` enum variants, each a struct with the listed fields, in this order):
  - `Transfer { from: ContractAddress, to: ContractAddress, value: u256 }` — emitted on every successful `mint` (with `from` = zero address), `transfer`, and `transfer_from`.
  - `Approval { owner: ContractAddress, spender: ContractAddress, value: u256 }` — emitted on every successful `approve`.

Both event structs and the trait must be public (`pub`).
