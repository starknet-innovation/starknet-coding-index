use starknet::ContractAddress;

#[starknet::interface]
pub trait IPriceOracle<TContractState> {
    fn set_price(ref self: TContractState, asset: felt252, price: u128);
    fn get_price(self: @TContractState, asset: felt252) -> u128;
}

#[starknet::interface]
pub trait IConsumer<TContractState> {
    fn get_oracle(self: @TContractState) -> ContractAddress;
    fn quote(self: @TContractState, asset: felt252, amount: u128) -> u128;
    fn set_oracle(ref self: TContractState, oracle: ContractAddress);
}

#[starknet::contract]
pub mod PriceOracle {
    use starknet::storage::{
        Map, StoragePathEntry, StoragePointerReadAccess, StoragePointerWriteAccess,
    };
    use starknet::{ContractAddress, get_caller_address};

    #[storage]
    struct Storage {
        owner: ContractAddress,
        prices: Map<felt252, u128>,
        has_price: Map<felt252, bool>,
    }

    #[constructor]
    fn constructor(ref self: ContractState, owner: ContractAddress) {
        self.owner.write(owner);
    }

    #[abi(embed_v0)]
    impl PriceOracleImpl of super::IPriceOracle<ContractState> {
        fn set_price(ref self: ContractState, asset: felt252, price: u128) {
            assert(get_caller_address() == self.owner.read(), 'Oracle: not owner');
            self.prices.entry(asset).write(price);
            self.has_price.entry(asset).write(true);
        }

        fn get_price(self: @ContractState, asset: felt252) -> u128 {
            assert(self.has_price.entry(asset).read(), 'Oracle: unknown asset');
            self.prices.entry(asset).read()
        }
    }
}

#[starknet::contract]
pub mod Consumer {
    use starknet::ContractAddress;
    use starknet::storage::{StoragePointerReadAccess, StoragePointerWriteAccess};
    use super::{IPriceOracleDispatcher, IPriceOracleDispatcherTrait};

    #[storage]
    struct Storage {
        oracle: ContractAddress,
    }

    #[constructor]
    fn constructor(ref self: ContractState, oracle: ContractAddress) {
        self.oracle.write(oracle);
    }

    #[abi(embed_v0)]
    impl ConsumerImpl of super::IConsumer<ContractState> {
        fn get_oracle(self: @ContractState) -> ContractAddress {
            self.oracle.read()
        }

        fn quote(self: @ContractState, asset: felt252, amount: u128) -> u128 {
            let oracle = IPriceOracleDispatcher { contract_address: self.oracle.read() };
            oracle.get_price(asset) * amount
        }

        fn set_oracle(ref self: ContractState, oracle: ContractAddress) {
            let zero: ContractAddress = 0.try_into().unwrap();
            assert(oracle != zero, 'Consumer: zero oracle');
            self.oracle.write(oracle);
        }
    }
}
