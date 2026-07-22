Implement an item store (CRUD) contract in Cairo for Starknet.

## Requirements

Package name: `item_store` (already set in Scarb.toml). Everything lives in `src/lib.cairo`.

### Item struct

At the top level of the file (outside any module), define a public struct that external code can import as `item_store::Item`:

```cairo
#[derive(Drop, Copy, Serde, starknet::Store, PartialEq)]
pub struct Item {
    pub id: u64,
    pub owner: ContractAddress,
    pub price: u128,
    pub active: bool,
}
```

Use exactly this name, these field names/types/order, and these derives (all fields `pub`).

### Interface

Define a public interface trait `IItemStore` (annotated with `#[starknet::interface]`) with exactly these functions:

- `fn create_item(ref self: TContractState, price: u128) -> u64;` — creates a new item and returns its id. Ids are sequential starting at 1 (first item has id 1, second id 2, ...). The item's `owner` is the caller, `active` is `true`, and `price` is the given price. If `price` is 0, panic with the short string `'Item: zero price'`.
- `fn get_item(self: @TContractState, id: u64) -> Item;` — returns the stored item. For an id that was never created (including 0), panic with `'Item: not found'`.
- `fn update_price(ref self: TContractState, id: u64, new_price: u128);` — sets the item's price to `new_price`. Only the item's owner may call this; otherwise panic with `'Item: not owner'`. If `new_price` is 0, panic with `'Item: zero price'`. If the item is inactive, panic with `'Item: inactive'`.
- `fn deactivate(ref self: TContractState, id: u64);` — sets the item's `active` flag to `false`. Only the item's owner may call this; otherwise panic with `'Item: not owner'`. If the item is already inactive, panic with `'Item: inactive'`.
- `fn item_count(self: @TContractState) -> u64;` — returns the total number of items ever created (deactivation does not decrease it).

### Contract

Define a contract module named `ItemStoreContract` (annotated with `#[starknet::contract]`) that implements `IItemStore` (the impl must be annotated with `#[abi(embed_v0)]`). Note: the module must be named `ItemStoreContract` — not `ItemStore` — because the `starknet::Store` derive on `Item` already generates an item named `ItemStore`.

- No constructor arguments (either omit the constructor or take no arguments); the store starts empty with a count of 0.
- Events (contract's `Event` enum variants, each a struct with the listed fields, in this order):
  - `ItemCreated { id: u64, owner: ContractAddress, price: u128 }` — emitted on every successful `create_item` (and it must be the only event emitted by that call).

The event struct and the trait must be public (`pub`).
