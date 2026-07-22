use starknet::ContractAddress;

#[starknet::interface]
pub trait IMockToken<TContractState> {
    fn mint(ref self: TContractState, to: ContractAddress, amount: u256);
    fn balance_of(self: @TContractState, account: ContractAddress) -> u256;
    fn transfer(ref self: TContractState, to: ContractAddress, amount: u256) -> bool;
    fn transfer_from(
        ref self: TContractState, from: ContractAddress, to: ContractAddress, amount: u256,
    ) -> bool;
    fn approve(ref self: TContractState, spender: ContractAddress, amount: u256) -> bool;
    fn allowance(
        self: @TContractState, owner: ContractAddress, spender: ContractAddress,
    ) -> u256;
}

#[starknet::interface]
pub trait IVault<TContractState> {
    fn asset(self: @TContractState) -> ContractAddress;
    fn total_assets(self: @TContractState) -> u256;
    fn total_shares(self: @TContractState) -> u256;
    fn shares_of(self: @TContractState, account: ContractAddress) -> u256;
    fn deposit(ref self: TContractState, amount: u256) -> u256;
    fn withdraw(ref self: TContractState, shares: u256) -> u256;
}

#[starknet::contract]
pub mod MockToken {
    use starknet::storage::{
        Map, StoragePathEntry, StoragePointerReadAccess, StoragePointerWriteAccess,
    };
    use starknet::{ContractAddress, get_caller_address};

    #[storage]
    struct Storage {
        balances: Map<ContractAddress, u256>,
        allowances: Map<(ContractAddress, ContractAddress), u256>,
    }

    #[abi(embed_v0)]
    impl MockTokenImpl of super::IMockToken<ContractState> {
        fn mint(ref self: ContractState, to: ContractAddress, amount: u256) {
            self.balances.entry(to).write(self.balances.entry(to).read() + amount);
        }

        fn balance_of(self: @ContractState, account: ContractAddress) -> u256 {
            self.balances.entry(account).read()
        }

        fn transfer(ref self: ContractState, to: ContractAddress, amount: u256) -> bool {
            let caller = get_caller_address();
            let from_balance = self.balances.entry(caller).read();
            assert(from_balance >= amount, 'Token: insufficient bal');
            self.balances.entry(caller).write(from_balance - amount);
            self.balances.entry(to).write(self.balances.entry(to).read() + amount);
            true
        }

        fn transfer_from(
            ref self: ContractState, from: ContractAddress, to: ContractAddress, amount: u256,
        ) -> bool {
            let caller = get_caller_address();
            let allowed = self.allowances.entry((from, caller)).read();
            assert(allowed >= amount, 'Token: insufficient allow');
            let from_balance = self.balances.entry(from).read();
            assert(from_balance >= amount, 'Token: insufficient bal');
            self.allowances.entry((from, caller)).write(allowed - amount);
            self.balances.entry(from).write(from_balance - amount);
            self.balances.entry(to).write(self.balances.entry(to).read() + amount);
            true
        }

        fn approve(ref self: ContractState, spender: ContractAddress, amount: u256) -> bool {
            let caller = get_caller_address();
            self.allowances.entry((caller, spender)).write(amount);
            true
        }

        fn allowance(
            self: @ContractState, owner: ContractAddress, spender: ContractAddress,
        ) -> u256 {
            self.allowances.entry((owner, spender)).read()
        }
    }
}

#[starknet::contract]
pub mod Vault {
    use starknet::storage::{
        Map, StoragePathEntry, StoragePointerReadAccess, StoragePointerWriteAccess,
    };
    use starknet::{ContractAddress, get_caller_address, get_contract_address};
    use super::{IMockTokenDispatcher, IMockTokenDispatcherTrait};

    #[storage]
    struct Storage {
        token: ContractAddress,
        total_assets: u256,
        total_shares: u256,
        shares: Map<ContractAddress, u256>,
    }

    #[event]
    #[derive(Drop, starknet::Event)]
    pub enum Event {
        Deposited: Deposited,
        Withdrawn: Withdrawn,
    }

    #[derive(Drop, starknet::Event)]
    pub struct Deposited {
        pub caller: ContractAddress,
        pub amount: u256,
        pub shares: u256,
    }

    #[derive(Drop, starknet::Event)]
    pub struct Withdrawn {
        pub caller: ContractAddress,
        pub shares: u256,
        pub assets: u256,
    }

    #[constructor]
    fn constructor(ref self: ContractState, token: ContractAddress) {
        self.token.write(token);
    }

    #[abi(embed_v0)]
    impl VaultImpl of super::IVault<ContractState> {
        fn asset(self: @ContractState) -> ContractAddress {
            self.token.read()
        }

        fn total_assets(self: @ContractState) -> u256 {
            self.total_assets.read()
        }

        fn total_shares(self: @ContractState) -> u256 {
            self.total_shares.read()
        }

        fn shares_of(self: @ContractState, account: ContractAddress) -> u256 {
            self.shares.entry(account).read()
        }

        fn deposit(ref self: ContractState, amount: u256) -> u256 {
            assert(amount != 0, 'Vault: zero amount');
            let caller = get_caller_address();
            let total_shares = self.total_shares.read();
            let total_assets = self.total_assets.read();
            let shares = if total_shares == 0 {
                amount
            } else {
                amount * total_shares / total_assets
            };
            let token = IMockTokenDispatcher { contract_address: self.token.read() };
            token.transfer_from(caller, get_contract_address(), amount);
            self.total_assets.write(total_assets + amount);
            self.total_shares.write(total_shares + shares);
            self.shares.entry(caller).write(self.shares.entry(caller).read() + shares);
            self.emit(Deposited { caller, amount, shares });
            shares
        }

        fn withdraw(ref self: ContractState, shares: u256) -> u256 {
            assert(shares != 0, 'Vault: zero shares');
            let caller = get_caller_address();
            let caller_shares = self.shares.entry(caller).read();
            assert(caller_shares >= shares, 'Vault: insufficient shares');
            let total_shares = self.total_shares.read();
            let total_assets = self.total_assets.read();
            let assets = shares * total_assets / total_shares;
            self.shares.entry(caller).write(caller_shares - shares);
            self.total_shares.write(total_shares - shares);
            self.total_assets.write(total_assets - assets);
            let token = IMockTokenDispatcher { contract_address: self.token.read() };
            token.transfer(caller, assets);
            self.emit(Withdrawn { caller, shares, assets });
            assets
        }
    }
}
