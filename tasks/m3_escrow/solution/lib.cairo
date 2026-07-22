use starknet::ContractAddress;

#[starknet::interface]
pub trait IEscrow<TContractState> {
    fn deposit_for(
        ref self: TContractState, beneficiary: ContractAddress, amount: u128, unlock_time: u64,
    ) -> u64;
    fn withdraw(ref self: TContractState, deposit_id: u64);
    fn get_deposit(self: @TContractState, deposit_id: u64) -> (ContractAddress, u128, u64, bool);
    fn balance_of(self: @TContractState, beneficiary: ContractAddress) -> u128;
}

#[starknet::contract]
pub mod Escrow {
    use starknet::storage::{
        Map, StoragePathEntry, StoragePointerReadAccess, StoragePointerWriteAccess,
    };
    use starknet::{ContractAddress, get_block_timestamp, get_caller_address};

    #[storage]
    struct Storage {
        deposit_count: u64,
        beneficiaries: Map<u64, ContractAddress>,
        amounts: Map<u64, u128>,
        unlock_times: Map<u64, u64>,
        withdrawn_flags: Map<u64, bool>,
        balances: Map<ContractAddress, u128>,
    }

    #[event]
    #[derive(Drop, starknet::Event)]
    pub enum Event {
        Deposited: Deposited,
        Withdrawn: Withdrawn,
    }

    #[derive(Drop, starknet::Event)]
    pub struct Deposited {
        pub id: u64,
        pub depositor: ContractAddress,
        pub beneficiary: ContractAddress,
        pub amount: u128,
        pub unlock_time: u64,
    }

    #[derive(Drop, starknet::Event)]
    pub struct Withdrawn {
        pub id: u64,
        pub beneficiary: ContractAddress,
        pub amount: u128,
    }

    #[abi(embed_v0)]
    impl EscrowImpl of super::IEscrow<ContractState> {
        fn deposit_for(
            ref self: ContractState, beneficiary: ContractAddress, amount: u128, unlock_time: u64,
        ) -> u64 {
            assert(amount != 0, 'Escrow: zero amount');
            assert(unlock_time > get_block_timestamp(), 'Escrow: bad unlock time');
            let id = self.deposit_count.read() + 1;
            self.deposit_count.write(id);
            self.beneficiaries.entry(id).write(beneficiary);
            self.amounts.entry(id).write(amount);
            self.unlock_times.entry(id).write(unlock_time);
            self.balances.entry(beneficiary).write(self.balances.entry(beneficiary).read() + amount);
            self
                .emit(
                    Deposited {
                        id, depositor: get_caller_address(), beneficiary, amount, unlock_time,
                    },
                );
            id
        }

        fn withdraw(ref self: ContractState, deposit_id: u64) {
            self.assert_exists(deposit_id);
            let beneficiary = self.beneficiaries.entry(deposit_id).read();
            assert(get_caller_address() == beneficiary, 'Escrow: not beneficiary');
            let unlock_time = self.unlock_times.entry(deposit_id).read();
            assert(get_block_timestamp() >= unlock_time, 'Escrow: locked');
            assert(!self.withdrawn_flags.entry(deposit_id).read(), 'Escrow: already withdrawn');
            self.withdrawn_flags.entry(deposit_id).write(true);
            let amount = self.amounts.entry(deposit_id).read();
            self.balances.entry(beneficiary).write(self.balances.entry(beneficiary).read() - amount);
            self.emit(Withdrawn { id: deposit_id, beneficiary, amount });
        }

        fn get_deposit(
            self: @ContractState, deposit_id: u64,
        ) -> (ContractAddress, u128, u64, bool) {
            self.assert_exists(deposit_id);
            (
                self.beneficiaries.entry(deposit_id).read(),
                self.amounts.entry(deposit_id).read(),
                self.unlock_times.entry(deposit_id).read(),
                self.withdrawn_flags.entry(deposit_id).read(),
            )
        }

        fn balance_of(self: @ContractState, beneficiary: ContractAddress) -> u128 {
            self.balances.entry(beneficiary).read()
        }
    }

    #[generate_trait]
    impl InternalImpl of InternalTrait {
        fn assert_exists(self: @ContractState, deposit_id: u64) {
            let count = self.deposit_count.read();
            assert(deposit_id != 0 && deposit_id <= count, 'Escrow: no deposit');
        }
    }
}
