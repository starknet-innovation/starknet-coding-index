Implement two Starknet contracts in Cairo that interact cross-contract via a dispatcher: a price oracle and a consumer that quotes prices from it.

## Requirements

Package name: `oracle_consumer` (already set in Scarb.toml). **Both contracts and both interface traits live in the single file `src/lib.cairo`.**

### Oracle interface

Define a public interface trait `IPriceOracle` (annotated with `#[starknet::interface]`) with exactly these functions:

- `fn set_price(ref self: TContractState, asset: felt252, price: u128);` — sets the price of `asset`. Only the owner may call this; any other caller must cause a panic with the short string `'Oracle: not owner'`. Setting the same asset again overwrites the price. A price of 0 is allowed.
- `fn get_price(self: @TContractState, asset: felt252) -> u128;` — returns the last price set for `asset`. If `asset` has never been set, panic with `'Oracle: unknown asset'`.

Define a contract module named `PriceOracle` (annotated with `#[starknet::contract]`) implementing `IPriceOracle` (impl annotated with `#[abi(embed_v0)]`):

- Constructor: `fn constructor(ref self: ContractState, owner: ContractAddress)` — stores the owner.

### Consumer interface

Define a public interface trait `IConsumer` (annotated with `#[starknet::interface]`) with exactly these functions:

- `fn get_oracle(self: @TContractState) -> ContractAddress;` — returns the currently configured oracle address.
- `fn quote(self: @TContractState, asset: felt252, amount: u128) -> u128;` — fetches the asset's price from the configured oracle via a cross-contract call and returns `price * amount`. If the oracle panics (e.g. unknown asset), that panic propagates to the caller.
- `fn set_oracle(ref self: TContractState, oracle: ContractAddress);` — points the consumer at a new oracle address. Anyone may call this. If `oracle` is the zero address, panic with `'Consumer: zero oracle'`.

Define a contract module named `Consumer` (annotated with `#[starknet::contract]`) implementing `IConsumer` (impl annotated with `#[abi(embed_v0)]`):

- Constructor: `fn constructor(ref self: ContractState, oracle: ContractAddress)` — stores the oracle address.
- `quote` must perform a real cross-contract call using the dispatcher generated from `IPriceOracle` (`IPriceOracleDispatcher`); do not duplicate the oracle's storage or logic inside the consumer.

Both traits must be public (`pub`). No events are required.
