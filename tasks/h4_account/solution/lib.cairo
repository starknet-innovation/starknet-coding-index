use starknet::account::Call;

#[starknet::interface]
pub trait ISRC6<TContractState> {
    fn __execute__(ref self: TContractState, calls: Array<Call>) -> Array<Span<felt252>>;
    fn __validate__(self: @TContractState, calls: Array<Call>) -> felt252;
    fn is_valid_signature(
        self: @TContractState, hash: felt252, signature: Array<felt252>,
    ) -> felt252;
}

#[starknet::interface]
pub trait IAccountMeta<TContractState> {
    fn get_public_key(self: @TContractState) -> felt252;
}

#[starknet::interface]
pub trait ITarget<TContractState> {
    fn set_value(ref self: TContractState, v: felt252);
    fn get_value(self: @TContractState) -> felt252;
}

#[starknet::contract]
pub mod SimpleAccount {
    use core::ecdsa::check_ecdsa_signature;
    use starknet::account::Call;
    use starknet::storage::{StoragePointerReadAccess, StoragePointerWriteAccess};
    use starknet::syscalls::call_contract_syscall;
    use starknet::{ContractAddress, SyscallResultTrait, get_caller_address, get_tx_info};

    #[storage]
    struct Storage {
        public_key: felt252,
    }

    #[constructor]
    fn constructor(ref self: ContractState, public_key: felt252) {
        self.public_key.write(public_key);
    }

    fn is_valid_stark_signature(
        public_key: felt252, hash: felt252, signature: Span<felt252>,
    ) -> bool {
        signature.len() == 2
            && check_ecdsa_signature(hash, public_key, *signature.at(0), *signature.at(1))
    }

    #[abi(embed_v0)]
    impl SRC6Impl of super::ISRC6<ContractState> {
        fn __execute__(ref self: ContractState, calls: Array<Call>) -> Array<Span<felt252>> {
            let zero: ContractAddress = 0.try_into().unwrap();
            assert(get_caller_address() == zero, 'Account: invalid caller');
            let mut results: Array<Span<felt252>> = array![];
            for call in calls {
                let ret = call_contract_syscall(call.to, call.selector, call.calldata)
                    .unwrap_syscall();
                results.append(ret);
            }
            results
        }

        fn __validate__(self: @ContractState, calls: Array<Call>) -> felt252 {
            let tx_info = get_tx_info().unbox();
            let valid = is_valid_stark_signature(
                self.public_key.read(), tx_info.transaction_hash, tx_info.signature,
            );
            assert(valid, 'Account: invalid sig');
            'VALID'
        }

        fn is_valid_signature(
            self: @ContractState, hash: felt252, signature: Array<felt252>,
        ) -> felt252 {
            if is_valid_stark_signature(self.public_key.read(), hash, signature.span()) {
                'VALID'
            } else {
                0
            }
        }
    }

    #[abi(embed_v0)]
    impl AccountMetaImpl of super::IAccountMeta<ContractState> {
        fn get_public_key(self: @ContractState) -> felt252 {
            self.public_key.read()
        }
    }
}

#[starknet::contract]
pub mod Target {
    use starknet::storage::{StoragePointerReadAccess, StoragePointerWriteAccess};

    #[storage]
    struct Storage {
        value: felt252,
    }

    #[abi(embed_v0)]
    impl TargetImpl of super::ITarget<ContractState> {
        fn set_value(ref self: ContractState, v: felt252) {
            self.value.write(v);
        }

        fn get_value(self: @ContractState) -> felt252 {
            self.value.read()
        }
    }
}
