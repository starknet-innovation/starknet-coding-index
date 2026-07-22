use starknet::ContractAddress;

#[starknet::interface]
pub trait ICappedToken<TContractState> {
    fn name(self: @TContractState) -> felt252;
    fn symbol(self: @TContractState) -> felt252;
    fn decimals(self: @TContractState) -> u8;
    fn total_supply(self: @TContractState) -> u256;
    fn cap(self: @TContractState) -> u256;
    fn balance_of(self: @TContractState, account: ContractAddress) -> u256;
    fn allowance(self: @TContractState, owner: ContractAddress, spender: ContractAddress) -> u256;
    fn mint(ref self: TContractState, to: ContractAddress, amount: u256);
    fn transfer(ref self: TContractState, to: ContractAddress, amount: u256) -> bool;
    fn approve(ref self: TContractState, spender: ContractAddress, amount: u256) -> bool;
    fn transfer_from(
        ref self: TContractState, from: ContractAddress, to: ContractAddress, amount: u256,
    ) -> bool;
}

#[starknet::contract]
pub mod CappedToken {
    use starknet::storage::{
        Map, StoragePathEntry, StoragePointerReadAccess, StoragePointerWriteAccess,
    };
    use starknet::{ContractAddress, get_caller_address};

    #[storage]
    struct Storage {
        token_name: felt252,
        token_symbol: felt252,
        supply: u256,
        cap: u256,
        minter: ContractAddress,
        balances: Map<ContractAddress, u256>,
        allowances: Map<(ContractAddress, ContractAddress), u256>,
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
        pub value: u256,
    }

    #[derive(Drop, starknet::Event)]
    pub struct Approval {
        pub owner: ContractAddress,
        pub spender: ContractAddress,
        pub value: u256,
    }

    #[constructor]
    fn constructor(
        ref self: ContractState,
        name: felt252,
        symbol: felt252,
        cap: u256,
        minter: ContractAddress,
    ) {
        self.token_name.write(name);
        self.token_symbol.write(symbol);
        self.cap.write(cap);
        self.minter.write(minter);
    }

    #[abi(embed_v0)]
    impl CappedTokenImpl of super::ICappedToken<ContractState> {
        fn name(self: @ContractState) -> felt252 {
            self.token_name.read()
        }

        fn symbol(self: @ContractState) -> felt252 {
            self.token_symbol.read()
        }

        fn decimals(self: @ContractState) -> u8 {
            18
        }

        fn total_supply(self: @ContractState) -> u256 {
            self.supply.read()
        }

        fn cap(self: @ContractState) -> u256 {
            self.cap.read()
        }

        fn balance_of(self: @ContractState, account: ContractAddress) -> u256 {
            self.balances.entry(account).read()
        }

        fn allowance(
            self: @ContractState, owner: ContractAddress, spender: ContractAddress,
        ) -> u256 {
            self.allowances.entry((owner, spender)).read()
        }

        fn mint(ref self: ContractState, to: ContractAddress, amount: u256) {
            let caller = get_caller_address();
            assert(caller == self.minter.read(), 'ERC20: not minter');
            let new_supply = self.supply.read() + amount;
            assert(new_supply <= self.cap.read(), 'ERC20: cap exceeded');
            self.supply.write(new_supply);
            self.balances.entry(to).write(self.balances.entry(to).read() + amount);
            let zero: ContractAddress = 0.try_into().unwrap();
            self.emit(Transfer { from: zero, to, value: amount });
        }

        fn transfer(ref self: ContractState, to: ContractAddress, amount: u256) -> bool {
            let from = get_caller_address();
            let from_balance = self.balances.entry(from).read();
            assert(from_balance >= amount, 'ERC20: insufficient bal');
            self.balances.entry(from).write(from_balance - amount);
            self.balances.entry(to).write(self.balances.entry(to).read() + amount);
            self.emit(Transfer { from, to, value: amount });
            true
        }

        fn approve(ref self: ContractState, spender: ContractAddress, amount: u256) -> bool {
            let owner = get_caller_address();
            self.allowances.entry((owner, spender)).write(amount);
            self.emit(Approval { owner, spender, value: amount });
            true
        }

        fn transfer_from(
            ref self: ContractState, from: ContractAddress, to: ContractAddress, amount: u256,
        ) -> bool {
            let caller = get_caller_address();
            let allowed = self.allowances.entry((from, caller)).read();
            assert(allowed >= amount, 'ERC20: insufficient allow');
            self.allowances.entry((from, caller)).write(allowed - amount);
            let from_balance = self.balances.entry(from).read();
            assert(from_balance >= amount, 'ERC20: insufficient bal');
            self.balances.entry(from).write(from_balance - amount);
            self.balances.entry(to).write(self.balances.entry(to).read() + amount);
            self.emit(Transfer { from, to, value: amount });
            true
        }
    }
}
