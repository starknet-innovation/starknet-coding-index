Implement a configuration store contract in Cairo for Starknet that stores a struct-typed config and computes fees from it.

## Requirements

Package name: `config_store` (already set in Scarb.toml).

At the top level of the file (OUTSIDE the contract module, so tests can import it as `config_store::Config`), define a public struct with exactly these fields, in this order:

```cairo
#[derive(Drop, Serde, starknet::Store, PartialEq)]
pub struct Config {
    pub threshold: u64,
    pub fee_bps: u16,
    pub admin: ContractAddress,
}
```

Define a public interface trait `IConfigStore` (annotated with `#[starknet::interface]`) with exactly these functions:

- `fn get_config(self: @TContractState) -> Config;` — returns the currently stored config.
- `fn set_config(ref self: TContractState, config: Config);` — replaces the stored config. Only the current config's `admin` may call it; any other caller must panic with the short string `'Config: not admin'`. If `config.fee_bps` is greater than 10000, it must panic with `'Config: bad fee'` (an admin-caller check happens for every call; the fee check applies to the new config). After a successful call the new config is fully in effect, including its `admin` field.
- `fn compute_fee(self: @TContractState, amount: u128) -> u128;` — returns `amount * fee_bps / 10000` using the stored config's `fee_bps`, with integer division (rounds down).

Define a contract module named `ConfigManager` (annotated with `#[starknet::contract]`) that implements `IConfigStore` (the impl must be annotated with `#[abi(embed_v0)]`). (The module is deliberately not named `ConfigStore`: the `starknet::Store` derive on `Config` already generates an item with that name.)

- Constructor: `fn constructor(ref self: ContractState, threshold: u64, fee_bps: u16, admin: ContractAddress)` — stores the initial config built from these arguments. If `fee_bps` is greater than 10000, it must panic with `'Config: bad fee'` (making the deployment fail).

No events are required. The struct and the trait must be public (`pub`).
