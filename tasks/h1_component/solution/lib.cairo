#[starknet::interface]
pub trait IPausable<TContractState> {
    fn is_paused(self: @TContractState) -> bool;
    fn pause(ref self: TContractState);
    fn unpause(ref self: TContractState);
}

#[starknet::component]
pub mod pausable_component {
    use starknet::storage::{StoragePointerReadAccess, StoragePointerWriteAccess};
    use starknet::{ContractAddress, get_caller_address};

    #[storage]
    pub struct Storage {
        pub paused: bool,
    }

    #[event]
    #[derive(Drop, starknet::Event)]
    pub enum Event {
        Paused: Paused,
        Unpaused: Unpaused,
    }

    #[derive(Drop, starknet::Event)]
    pub struct Paused {
        pub by: ContractAddress,
    }

    #[derive(Drop, starknet::Event)]
    pub struct Unpaused {
        pub by: ContractAddress,
    }

    #[embeddable_as(Pausable)]
    impl PausableImpl<
        TContractState, +HasComponent<TContractState>,
    > of super::IPausable<ComponentState<TContractState>> {
        fn is_paused(self: @ComponentState<TContractState>) -> bool {
            self.paused.read()
        }

        fn pause(ref self: ComponentState<TContractState>) {
            assert(!self.paused.read(), 'Pausable: paused');
            self.paused.write(true);
            self.emit(Paused { by: get_caller_address() });
        }

        fn unpause(ref self: ComponentState<TContractState>) {
            assert(self.paused.read(), 'Pausable: not paused');
            self.paused.write(false);
            self.emit(Unpaused { by: get_caller_address() });
        }
    }

    #[generate_trait]
    pub impl InternalImpl<
        TContractState, +HasComponent<TContractState>,
    > of InternalTrait<TContractState> {
        fn assert_not_paused(self: @ComponentState<TContractState>) {
            assert(!self.paused.read(), 'Pausable: paused');
        }
    }
}

#[starknet::interface]
pub trait IMachine<TContractState> {
    fn tick(ref self: TContractState) -> u64;
    fn get_ticks(self: @TContractState) -> u64;
}

#[starknet::contract]
pub mod Machine {
    use starknet::storage::{StoragePointerReadAccess, StoragePointerWriteAccess};
    use super::pausable_component;
    use super::pausable_component::InternalTrait;

    component!(path: pausable_component, storage: pausable, event: PausableEvent);

    #[abi(embed_v0)]
    impl Pausable = pausable_component::Pausable<ContractState>;
    impl PausableInternal = pausable_component::InternalImpl<ContractState>;

    #[storage]
    struct Storage {
        ticks: u64,
        #[substorage(v0)]
        pausable: pausable_component::Storage,
    }

    #[event]
    #[derive(Drop, starknet::Event)]
    pub enum Event {
        #[flat]
        PausableEvent: pausable_component::Event,
    }

    #[abi(embed_v0)]
    impl MachineImpl of super::IMachine<ContractState> {
        fn tick(ref self: ContractState) -> u64 {
            self.pausable.assert_not_paused();
            let new_value = self.ticks.read() + 1;
            self.ticks.write(new_value);
            new_value
        }

        fn get_ticks(self: @ContractState) -> u64 {
            self.ticks.read()
        }
    }
}
