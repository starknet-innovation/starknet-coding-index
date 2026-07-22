use starknet::ContractAddress;

#[starknet::interface]
pub trait IRegistry<TContractState> {
    fn register(ref self: TContractState, name: felt252);
    fn name_of(self: @TContractState, account: ContractAddress) -> felt252;
    fn total_registered(self: @TContractState) -> u64;
}

#[starknet::contract]
pub mod Registry {
    use starknet::storage::{
        Map, StoragePathEntry, StoragePointerReadAccess, StoragePointerWriteAccess,
    };
    use starknet::{ContractAddress, get_caller_address};

    #[storage]
    struct Storage {
        names: Map<ContractAddress, felt252>,
        count: u64,
    }

    #[event]
    #[derive(Drop, starknet::Event)]
    pub enum Event {
        Registered: Registered,
    }

    #[derive(Drop, starknet::Event)]
    pub struct Registered {
        pub account: ContractAddress,
        pub name: felt252,
    }

    #[abi(embed_v0)]
    impl RegistryImpl of super::IRegistry<ContractState> {
        fn register(ref self: ContractState, name: felt252) {
            assert(name != 0, 'Registry: empty name');
            let caller = get_caller_address();
            let existing = self.names.entry(caller).read();
            if existing == 0 {
                self.count.write(self.count.read() + 1);
            }
            self.names.entry(caller).write(name);
            self.emit(Registered { account: caller, name });
        }

        fn name_of(self: @ContractState, account: ContractAddress) -> felt252 {
            self.names.entry(account).read()
        }

        fn total_registered(self: @ContractState) -> u64 {
            self.count.read()
        }
    }
}
