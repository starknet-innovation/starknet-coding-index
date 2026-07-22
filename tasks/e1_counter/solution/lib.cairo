#[starknet::interface]
pub trait ICounter<TContractState> {
    fn get(self: @TContractState) -> u64;
    fn increment(ref self: TContractState, amount: u64);
    fn decrement(ref self: TContractState, amount: u64);
}

#[starknet::contract]
pub mod Counter {
    use starknet::storage::{StoragePointerReadAccess, StoragePointerWriteAccess};

    #[storage]
    struct Storage {
        value: u64,
    }

    #[event]
    #[derive(Drop, starknet::Event)]
    pub enum Event {
        Incremented: Incremented,
        Decremented: Decremented,
    }

    #[derive(Drop, starknet::Event)]
    pub struct Incremented {
        pub amount: u64,
        pub new_value: u64,
    }

    #[derive(Drop, starknet::Event)]
    pub struct Decremented {
        pub amount: u64,
        pub new_value: u64,
    }

    #[constructor]
    fn constructor(ref self: ContractState, initial: u64) {
        self.value.write(initial);
    }

    #[abi(embed_v0)]
    impl CounterImpl of super::ICounter<ContractState> {
        fn get(self: @ContractState) -> u64 {
            self.value.read()
        }

        fn increment(ref self: ContractState, amount: u64) {
            let new_value = self.value.read() + amount;
            self.value.write(new_value);
            self.emit(Incremented { amount, new_value });
        }

        fn decrement(ref self: ContractState, amount: u64) {
            let current = self.value.read();
            assert(amount <= current, 'Counter: underflow');
            let new_value = current - amount;
            self.value.write(new_value);
            self.emit(Decremented { amount, new_value });
        }
    }
}
