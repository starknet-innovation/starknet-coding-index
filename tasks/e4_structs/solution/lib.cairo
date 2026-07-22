use starknet::ContractAddress;

#[derive(Drop, Serde, starknet::Store, PartialEq)]
pub struct Config {
    pub threshold: u64,
    pub fee_bps: u16,
    pub admin: ContractAddress,
}

#[starknet::interface]
pub trait IConfigStore<TContractState> {
    fn get_config(self: @TContractState) -> Config;
    fn set_config(ref self: TContractState, config: Config);
    fn compute_fee(self: @TContractState, amount: u128) -> u128;
}

#[starknet::contract]
pub mod ConfigManager {
    use starknet::storage::{StoragePointerReadAccess, StoragePointerWriteAccess};
    use starknet::{ContractAddress, get_caller_address};
    use super::Config;

    #[storage]
    struct Storage {
        config: Config,
    }

    #[constructor]
    fn constructor(ref self: ContractState, threshold: u64, fee_bps: u16, admin: ContractAddress) {
        assert(fee_bps <= 10000, 'Config: bad fee');
        self.config.write(Config { threshold, fee_bps, admin });
    }

    #[abi(embed_v0)]
    impl ConfigManagerImpl of super::IConfigStore<ContractState> {
        fn get_config(self: @ContractState) -> Config {
            self.config.read()
        }

        fn set_config(ref self: ContractState, config: Config) {
            assert(get_caller_address() == self.config.read().admin, 'Config: not admin');
            assert(config.fee_bps <= 10000, 'Config: bad fee');
            self.config.write(config);
        }

        fn compute_fee(self: @ContractState, amount: u128) -> u128 {
            let fee_bps: u128 = self.config.read().fee_bps.into();
            amount * fee_bps / 10000
        }
    }
}
