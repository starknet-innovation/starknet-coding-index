#[starknet::interface]
pub trait IBallot<TContractState> {
    fn create_proposal(ref self: TContractState, description: felt252, duration_secs: u64) -> u64;
    fn vote(ref self: TContractState, proposal_id: u64, support: bool);
    fn get_votes(self: @TContractState, proposal_id: u64) -> (u64, u64);
    fn has_passed(self: @TContractState, proposal_id: u64) -> bool;
}

#[starknet::contract]
pub mod Ballot {
    use starknet::storage::{
        Map, StoragePathEntry, StoragePointerReadAccess, StoragePointerWriteAccess,
    };
    use starknet::{ContractAddress, get_block_timestamp, get_caller_address};

    #[storage]
    struct Storage {
        proposal_count: u64,
        descriptions: Map<u64, felt252>,
        deadlines: Map<u64, u64>,
        yes_votes: Map<u64, u64>,
        no_votes: Map<u64, u64>,
        voted: Map<(u64, ContractAddress), bool>,
    }

    #[event]
    #[derive(Drop, starknet::Event)]
    pub enum Event {
        ProposalCreated: ProposalCreated,
        VoteCast: VoteCast,
    }

    #[derive(Drop, starknet::Event)]
    pub struct ProposalCreated {
        pub id: u64,
        pub creator: ContractAddress,
        pub deadline: u64,
    }

    #[derive(Drop, starknet::Event)]
    pub struct VoteCast {
        pub id: u64,
        pub voter: ContractAddress,
        pub support: bool,
    }

    #[abi(embed_v0)]
    impl BallotImpl of super::IBallot<ContractState> {
        fn create_proposal(
            ref self: ContractState, description: felt252, duration_secs: u64,
        ) -> u64 {
            assert(duration_secs != 0, 'Ballot: zero duration');
            let id = self.proposal_count.read() + 1;
            self.proposal_count.write(id);
            let deadline = get_block_timestamp() + duration_secs;
            self.descriptions.entry(id).write(description);
            self.deadlines.entry(id).write(deadline);
            self.emit(ProposalCreated { id, creator: get_caller_address(), deadline });
            id
        }

        fn vote(ref self: ContractState, proposal_id: u64, support: bool) {
            self.assert_exists(proposal_id);
            let deadline = self.deadlines.entry(proposal_id).read();
            assert(get_block_timestamp() < deadline, 'Ballot: voting closed');
            let voter = get_caller_address();
            assert(!self.voted.entry((proposal_id, voter)).read(), 'Ballot: already voted');
            self.voted.entry((proposal_id, voter)).write(true);
            if support {
                self.yes_votes.entry(proposal_id).write(self.yes_votes.entry(proposal_id).read() + 1);
            } else {
                self.no_votes.entry(proposal_id).write(self.no_votes.entry(proposal_id).read() + 1);
            }
            self.emit(VoteCast { id: proposal_id, voter, support });
        }

        fn get_votes(self: @ContractState, proposal_id: u64) -> (u64, u64) {
            self.assert_exists(proposal_id);
            (self.yes_votes.entry(proposal_id).read(), self.no_votes.entry(proposal_id).read())
        }

        fn has_passed(self: @ContractState, proposal_id: u64) -> bool {
            self.assert_exists(proposal_id);
            let deadline = self.deadlines.entry(proposal_id).read();
            if get_block_timestamp() < deadline {
                return false;
            }
            self.yes_votes.entry(proposal_id).read() > self.no_votes.entry(proposal_id).read()
        }
    }

    #[generate_trait]
    impl InternalImpl of InternalTrait {
        fn assert_exists(self: @ContractState, proposal_id: u64) {
            let count = self.proposal_count.read();
            assert(proposal_id != 0 && proposal_id <= count, 'Ballot: no proposal');
        }
    }
}
