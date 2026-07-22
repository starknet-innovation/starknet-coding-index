use starknet::ContractAddress;

#[starknet::interface]
pub trait ISeqNFT<TContractState> {
    fn name(self: @TContractState) -> felt252;
    fn symbol(self: @TContractState) -> felt252;
    fn max_supply(self: @TContractState) -> u64;
    fn total_minted(self: @TContractState) -> u64;
    fn owner_of(self: @TContractState, token_id: u64) -> ContractAddress;
    fn balance_of(self: @TContractState, owner: ContractAddress) -> u64;
    fn get_approved(self: @TContractState, token_id: u64) -> ContractAddress;
    fn mint(ref self: TContractState) -> u64;
    fn approve(ref self: TContractState, to: ContractAddress, token_id: u64);
    fn transfer(ref self: TContractState, to: ContractAddress, token_id: u64);
}

#[starknet::contract]
pub mod SeqNFT {
    use starknet::storage::{
        Map, StoragePathEntry, StoragePointerReadAccess, StoragePointerWriteAccess,
    };
    use starknet::{ContractAddress, get_caller_address};

    fn zero_address() -> ContractAddress {
        0.try_into().unwrap()
    }

    #[storage]
    struct Storage {
        name: felt252,
        symbol: felt252,
        max_supply: u64,
        total_minted: u64,
        owners: Map<u64, ContractAddress>,
        balances: Map<ContractAddress, u64>,
        approvals: Map<u64, ContractAddress>,
    }

    #[event]
    #[derive(Drop, starknet::Event)]
    pub enum Event {
        Transfer: Transfer,
        Approval: Approval,
    }

    #[derive(Drop, starknet::Event)]
    pub struct Transfer {
        pub from: ContractAddress,
        pub to: ContractAddress,
        pub token_id: u64,
    }

    #[derive(Drop, starknet::Event)]
    pub struct Approval {
        pub owner: ContractAddress,
        pub approved: ContractAddress,
        pub token_id: u64,
    }

    #[constructor]
    fn constructor(ref self: ContractState, name: felt252, symbol: felt252, max_supply: u64) {
        self.name.write(name);
        self.symbol.write(symbol);
        self.max_supply.write(max_supply);
    }

    #[abi(embed_v0)]
    impl SeqNFTImpl of super::ISeqNFT<ContractState> {
        fn name(self: @ContractState) -> felt252 {
            self.name.read()
        }

        fn symbol(self: @ContractState) -> felt252 {
            self.symbol.read()
        }

        fn max_supply(self: @ContractState) -> u64 {
            self.max_supply.read()
        }

        fn total_minted(self: @ContractState) -> u64 {
            self.total_minted.read()
        }

        fn owner_of(self: @ContractState, token_id: u64) -> ContractAddress {
            let owner = self.owners.entry(token_id).read();
            assert(owner != zero_address(), 'NFT: invalid token');
            owner
        }

        fn balance_of(self: @ContractState, owner: ContractAddress) -> u64 {
            self.balances.entry(owner).read()
        }

        fn get_approved(self: @ContractState, token_id: u64) -> ContractAddress {
            let owner = self.owners.entry(token_id).read();
            assert(owner != zero_address(), 'NFT: invalid token');
            self.approvals.entry(token_id).read()
        }

        fn mint(ref self: ContractState) -> u64 {
            let minted = self.total_minted.read();
            assert(minted < self.max_supply.read(), 'NFT: max supply');
            let token_id = minted + 1;
            let caller = get_caller_address();
            self.total_minted.write(token_id);
            self.owners.entry(token_id).write(caller);
            self.balances.entry(caller).write(self.balances.entry(caller).read() + 1);
            self.emit(Transfer { from: zero_address(), to: caller, token_id });
            token_id
        }

        fn approve(ref self: ContractState, to: ContractAddress, token_id: u64) {
            let owner = self.owners.entry(token_id).read();
            assert(get_caller_address() == owner, 'NFT: not owner');
            self.approvals.entry(token_id).write(to);
            self.emit(Approval { owner, approved: to, token_id });
        }

        fn transfer(ref self: ContractState, to: ContractAddress, token_id: u64) {
            let owner = self.owners.entry(token_id).read();
            let caller = get_caller_address();
            let approved = self.approvals.entry(token_id).read();
            assert(caller == owner || caller == approved, 'NFT: not authorized');
            assert(to != zero_address(), 'NFT: zero address');
            self.approvals.entry(token_id).write(zero_address());
            self.owners.entry(token_id).write(to);
            self.balances.entry(owner).write(self.balances.entry(owner).read() - 1);
            self.balances.entry(to).write(self.balances.entry(to).read() + 1);
            self.emit(Transfer { from: owner, to, token_id });
        }
    }
}
