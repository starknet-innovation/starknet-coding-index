use starknet::ContractAddress;

#[starknet::interface]
pub trait IVault<TContractState> {
    fn get_owner(self: @TContractState) -> ContractAddress;
    fn get_value(self: @TContractState) -> u128;
    fn set_value(ref self: TContractState, value: u128);
    fn transfer_ownership(ref self: TContractState, new_owner: ContractAddress);
}

#[starknet::contract]
pub mod Vault {
    use starknet::storage::{StoragePointerReadAccess, StoragePointerWriteAccess};
    use starknet::{ContractAddress, get_caller_address};

    #[storage]
    struct Storage {
        owner: ContractAddress,
        value: u128,
    }

    #[event]
    #[derive(Drop, starknet::Event)]
    pub enum Event {
        OwnershipTransferred: OwnershipTransferred,
    }

    #[derive(Drop, starknet::Event)]
    pub struct OwnershipTransferred {
        pub previous: ContractAddress,
        pub new: ContractAddress,
    }

    #[constructor]
    fn constructor(ref self: ContractState, owner: ContractAddress) {
        self.owner.write(owner);
    }

    #[abi(embed_v0)]
    impl VaultImpl of super::IVault<ContractState> {
        fn get_owner(self: @ContractState) -> ContractAddress {
            self.owner.read()
        }

        fn get_value(self: @ContractState) -> u128 {
            self.value.read()
        }

        fn set_value(ref self: ContractState, value: u128) {
            assert(get_caller_address() == self.owner.read(), 'Vault: not owner');
            self.value.write(value);
        }

        fn transfer_ownership(ref self: ContractState, new_owner: ContractAddress) {
            let previous = self.owner.read();
            assert(get_caller_address() == previous, 'Vault: not owner');
            let new_owner_felt: felt252 = new_owner.into();
            assert(new_owner_felt != 0, 'Vault: zero owner');
            self.owner.write(new_owner);
            self.emit(OwnershipTransferred { previous, new: new_owner });
        }
    }
}
