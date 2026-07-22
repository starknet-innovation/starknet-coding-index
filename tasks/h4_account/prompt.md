Implement a minimal SNIP-6-style Starknet account contract that validates STARK-curve ECDSA signatures, plus a tiny target contract used to exercise call execution. Both contracts live in a single file (`src/lib.cairo`). Do NOT use OpenZeppelin or any external library.

## Requirements

Package name: `account` (already set in Scarb.toml).

Use the standard `Call` struct from the core library: `starknet::account::Call` (fields `to: ContractAddress`, `selector: felt252`, `calldata: Span<felt252>`). Do NOT define your own `Call` struct — import it.

### Interfaces (at file top level, all `pub`, each annotated with `#[starknet::interface]`)

Trait `ISRC6` with exactly these functions:

- `fn __execute__(ref self: TContractState, calls: Array<Call>) -> Array<Span<felt252>>;`
- `fn __validate__(self: @TContractState, calls: Array<Call>) -> felt252;`
- `fn is_valid_signature(self: @TContractState, hash: felt252, signature: Array<felt252>) -> felt252;`

Trait `IAccountMeta` with exactly:

- `fn get_public_key(self: @TContractState) -> felt252;`

Trait `ITarget` with exactly:

- `fn set_value(ref self: TContractState, v: felt252);`
- `fn get_value(self: @TContractState) -> felt252;`

### Contract 1: SimpleAccount

Define a contract module named `SimpleAccount` (annotated with `#[starknet::contract]`) implementing both `ISRC6` and `IAccountMeta` (each impl annotated with `#[abi(embed_v0)]`):

- Constructor: `fn constructor(ref self: ContractState, public_key: felt252)` — stores the STARK-curve public key.
- `get_public_key` returns the stored public key.
- `is_valid_signature(hash, signature)` — returns the short string `'VALID'` (as a `felt252`) if `signature` is exactly `[r, s]` (length 2) and is a valid ECDSA signature over `hash` for the stored public key (use `core::ecdsa::check_ecdsa_signature`); otherwise returns `0` (it must NOT panic on an invalid signature).
- `__validate__(calls)` — reads the current transaction info via `starknet::get_tx_info()` and checks that the transaction's `signature` (as `[r, s]`) is a valid ECDSA signature over its `transaction_hash` for the stored public key. Returns `'VALID'` on success; panics with the short string `'Account: invalid sig'` otherwise (including when the signature does not have exactly 2 elements).
- `__execute__(calls)` — the caller must be the zero address (Starknet protocol convention); otherwise panic with `'Account: invalid caller'`. Then execute each call in order via `starknet::syscalls::call_contract_syscall(call.to, call.selector, call.calldata)`, and return the collected return values (one `Span<felt252>` per call, in order).

### Contract 2: Target

Define a contract module named `Target` (annotated with `#[starknet::contract]`) implementing `ITarget` (impl annotated with `#[abi(embed_v0)]`). It takes no constructor arguments (deployed with empty calldata). `set_value` stores `v`; `get_value` returns the stored value (0 initially).

Both contract modules and all three interface traits must be public (`pub`).
