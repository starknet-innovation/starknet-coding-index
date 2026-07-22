Implement a minimal ERC721-like NFT contract in Cairo for Starknet, from scratch (do NOT use OpenZeppelin or any external library). Tokens are minted sequentially and supply is capped.

## Requirements

Package name: `nft` (already set in Scarb.toml).

Define a public interface trait `ISeqNFT` (annotated with `#[starknet::interface]`) with exactly these functions:

- `fn name(self: @TContractState) -> felt252;` — collection name.
- `fn symbol(self: @TContractState) -> felt252;` — collection symbol.
- `fn max_supply(self: @TContractState) -> u64;` — maximum number of tokens that can ever be minted.
- `fn total_minted(self: @TContractState) -> u64;` — number of tokens minted so far.
- `fn owner_of(self: @TContractState, token_id: u64) -> ContractAddress;` — owner of a token. Must panic with the short string `'NFT: invalid token'` if the token has never been minted.
- `fn balance_of(self: @TContractState, owner: ContractAddress) -> u64;` — number of tokens held by `owner` (0 if none).
- `fn get_approved(self: @TContractState, token_id: u64) -> ContractAddress;` — the approved address for a token (the zero address if none). Must panic with `'NFT: invalid token'` if the token has never been minted.
- `fn mint(ref self: TContractState) -> u64;` — anyone can mint. Token ids are assigned sequentially starting at 1 (first mint returns 1, second returns 2, ...). The caller becomes the owner of the new token. If `total_minted` has already reached `max_supply`, panic with `'NFT: max supply'`. Returns the new token id.
- `fn approve(ref self: TContractState, to: ContractAddress, token_id: u64);` — sets `to` as the approved address for `token_id`. Only the token's current owner may call this; otherwise panic with `'NFT: not owner'`.
- `fn transfer(ref self: TContractState, to: ContractAddress, token_id: u64);` — transfers `token_id` to `to`. The caller must be the token's owner OR its approved address; otherwise panic with `'NFT: not authorized'`. `to` must not be the zero address; otherwise panic with `'NFT: zero address'`. A successful transfer clears any approval on the token (back to the zero address) and updates both parties' balances.

Define a contract module named `SeqNFT` (annotated with `#[starknet::contract]`) that implements `ISeqNFT` (the impl must be annotated with `#[abi(embed_v0)]`):

- Constructor: `fn constructor(ref self: ContractState, name: felt252, symbol: felt252, max_supply: u64)`.
- Events (contract's `Event` enum variants, each a struct with the listed fields, in this exact order; do NOT mark any field with `#[key]`):
  - `Transfer { from: ContractAddress, to: ContractAddress, token_id: u64 }` — emitted on every successful `mint` (with `from` = the zero address and `to` = the minter) and on every successful `transfer` (with `from` = the previous owner).
  - `Approval { owner: ContractAddress, approved: ContractAddress, token_id: u64 }` — emitted on every successful `approve`.

Both event structs and the trait must be public (`pub`).
