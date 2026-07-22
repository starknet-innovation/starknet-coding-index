Implement TWO Starknet contracts in a single file (`src/lib.cairo`): a minimal test token `MockToken` and a proportional-shares `Vault` (a simplified ERC4626-style vault) that holds that token. The vault must interact with the token through dispatcher calls. Do NOT use OpenZeppelin or any external library.

## Requirements

Package name: `vault` (already set in Scarb.toml).

### Contract 1: MockToken

Define a public interface trait `IMockToken` (annotated with `#[starknet::interface]`) with exactly these functions:

- `fn mint(ref self: TContractState, to: ContractAddress, amount: u256);` — anyone can mint (test token, no access control, no supply cap). Credits `amount` to `to`.
- `fn balance_of(self: @TContractState, account: ContractAddress) -> u256;`
- `fn transfer(ref self: TContractState, to: ContractAddress, amount: u256) -> bool;` — moves `amount` from the caller to `to`; panics with the short string `'Token: insufficient bal'` if the caller's balance is less than `amount`. Returns `true`.
- `fn transfer_from(ref self: TContractState, from: ContractAddress, to: ContractAddress, amount: u256) -> bool;` — moves `amount` from `from` to `to` using the caller's allowance. Checks the allowance first (panics `'Token: insufficient allow'` if the allowance of (`from`, caller) is less than `amount`), then the balance (panics `'Token: insufficient bal'` if `from`'s balance is less than `amount`). Decrements the allowance by `amount`. Returns `true`.
- `fn approve(ref self: TContractState, spender: ContractAddress, amount: u256) -> bool;` — sets the allowance of (caller, `spender`) to `amount`. Returns `true`.
- `fn allowance(self: @TContractState, owner: ContractAddress, spender: ContractAddress) -> u256;`

Define a contract module named `MockToken` (annotated with `#[starknet::contract]`) implementing `IMockToken` (impl annotated with `#[abi(embed_v0)]`). It takes NO constructor arguments (it is deployed with empty calldata). It emits no events.

### Contract 2: Vault

Define a public interface trait `IVault` (annotated with `#[starknet::interface]`) with exactly these functions:

- `fn asset(self: @TContractState) -> ContractAddress;` — the token address the vault holds.
- `fn total_assets(self: @TContractState) -> u256;` — the vault's INTERNALLY TRACKED asset balance: the sum of all deposited amounts minus all withdrawn amounts. IMPORTANT: tokens sent directly to the vault address (donations) must NOT affect this value — do not read the token balance; keep your own accounting in storage.
- `fn total_shares(self: @TContractState) -> u256;` — total shares outstanding.
- `fn shares_of(self: @TContractState, account: ContractAddress) -> u256;` — shares held by `account`.
- `fn deposit(ref self: TContractState, amount: u256) -> u256;` — pulls `amount` tokens from the caller into the vault via the token's `transfer_from` (the caller must have approved the vault beforehand) and mints shares to the caller. Panics with `'Vault: zero amount'` if `amount` is 0. Share math (computed from the state BEFORE this deposit is applied): if `total_shares` is 0, shares minted = `amount`; otherwise shares minted = `amount * total_shares / total_assets` (integer division). Increases tracked `total_assets` by `amount`. Returns the shares minted.
- `fn withdraw(ref self: TContractState, shares: u256) -> u256;` — burns `shares` from the caller and sends back assets = `shares * total_assets / total_shares` (integer division, computed before the burn) via the token's `transfer`. Panics with `'Vault: zero shares'` if `shares` is 0, and with `'Vault: insufficient shares'` if the caller holds fewer than `shares`. Decreases tracked `total_assets` by the assets paid out. Returns the assets sent.

Define a contract module named `Vault` (annotated with `#[starknet::contract]`) implementing `IVault` (impl annotated with `#[abi(embed_v0)]`):

- Constructor: `fn constructor(ref self: ContractState, token: ContractAddress)` — stores the token address.
- Events (contract's `Event` enum variants, each a struct with the listed fields, in this exact order; do NOT mark any field with `#[key]`):
  - `Deposited { caller: ContractAddress, amount: u256, shares: u256 }` — emitted on every successful `deposit`.
  - `Withdrawn { caller: ContractAddress, shares: u256, assets: u256 }` — emitted on every successful `withdraw`.

Both interface traits, both contract modules, and the event structs must be public (`pub`). The Vault must call the token through the `IMockToken` dispatcher (`IMockTokenDispatcher`).
