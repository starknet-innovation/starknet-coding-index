Implement a proposal voting contract with deadlines in Cairo for Starknet.

## Requirements

Package name: `voting` (already set in Scarb.toml).

Define a public interface trait `IBallot` (annotated with `#[starknet::interface]`) with exactly these functions:

- `fn create_proposal(ref self: TContractState, description: felt252, duration_secs: u64) -> u64;` — creates a new proposal and returns its id. Ids are sequential starting at 1 (the first proposal has id 1, the second id 2, ...). If `duration_secs` is 0, it must panic with the short string `'Ballot: zero duration'`. The proposal's voting deadline is the current block timestamp plus `duration_secs`.
- `fn vote(ref self: TContractState, proposal_id: u64, support: bool);` — casts the caller's vote on a proposal (`support` = `true` for yes, `false` for no). If no proposal with that id exists, it must panic with `'Ballot: no proposal'`. Voting is allowed only while the current block timestamp is strictly less than the proposal's deadline; at or after the deadline it must panic with `'Ballot: voting closed'`. Each address may vote at most once per proposal; a second vote from the same address must panic with `'Ballot: already voted'`.
- `fn get_votes(self: @TContractState, proposal_id: u64) -> (u64, u64);` — returns the tally as `(yes_votes, no_votes)`. If no proposal with that id exists, it must panic with `'Ballot: no proposal'`.
- `fn has_passed(self: @TContractState, proposal_id: u64) -> bool;` — returns `true` only if the current block timestamp is greater than or equal to the proposal's deadline AND the proposal has strictly more yes votes than no votes; otherwise `false` (in particular, always `false` before the deadline, and `false` on a tie). If no proposal with that id exists, it must panic with `'Ballot: no proposal'`.

Define a contract module named `Ballot` (annotated with `#[starknet::contract]`) that implements `IBallot` (the impl must be annotated with `#[abi(embed_v0)]`):

- The contract takes no constructor arguments (it is deployed with empty calldata).
- Events (contract's `Event` enum variants, each a struct with the listed fields, in this order):
  - `ProposalCreated { id: u64, creator: ContractAddress, deadline: u64 }` — emitted on every successful `create_proposal`; `creator` is the caller and `deadline` is the computed voting deadline.
  - `VoteCast { id: u64, voter: ContractAddress, support: bool }` — emitted on every successful `vote`; `voter` is the caller.

Both event structs and the trait must be public (`pub`).
