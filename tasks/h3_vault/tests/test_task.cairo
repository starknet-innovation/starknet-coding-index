use snforge_std::{
    ContractClassTrait, DeclareResultTrait, EventSpyTrait, declare, spy_events,
    start_cheat_caller_address, stop_cheat_caller_address,
};
use starknet::ContractAddress;
use vault::{
    IMockTokenDispatcher, IMockTokenDispatcherTrait, IVaultDispatcher, IVaultDispatcherTrait,
};

fn user1() -> ContractAddress {
    111.try_into().unwrap()
}

fn user2() -> ContractAddress {
    222.try_into().unwrap()
}

fn setup() -> (IMockTokenDispatcher, IVaultDispatcher) {
    let token_class = declare("MockToken").unwrap().contract_class();
    let (token_address, _) = token_class.deploy(@array![]).unwrap();
    let vault_class = declare("Vault").unwrap().contract_class();
    let (vault_address, _) = vault_class.deploy(@array![token_address.into()]).unwrap();
    (
        IMockTokenDispatcher { contract_address: token_address },
        IVaultDispatcher { contract_address: vault_address },
    )
}

fn fund_and_approve(
    token: IMockTokenDispatcher, vault: IVaultDispatcher, user: ContractAddress, amount: u256,
) {
    token.mint(user, amount);
    start_cheat_caller_address(token.contract_address, user);
    token.approve(vault.contract_address, amount);
    stop_cheat_caller_address(token.contract_address);
}

fn deposit_as(vault: IVaultDispatcher, user: ContractAddress, amount: u256) -> u256 {
    start_cheat_caller_address(vault.contract_address, user);
    let shares = vault.deposit(amount);
    stop_cheat_caller_address(vault.contract_address);
    shares
}

fn withdraw_as(vault: IVaultDispatcher, user: ContractAddress, shares: u256) -> u256 {
    start_cheat_caller_address(vault.contract_address, user);
    let assets = vault.withdraw(shares);
    stop_cheat_caller_address(vault.contract_address);
    assets
}

#[test]
fn test_initial_state() {
    let (token, vault) = setup();
    assert!(vault.asset() == token.contract_address, "asset address wrong");
    assert!(vault.total_assets() == 0, "total_assets should start at 0");
    assert!(vault.total_shares() == 0, "total_shares should start at 0");
    assert!(vault.shares_of(user1()) == 0, "shares_of should start at 0");
}

#[test]
fn test_deposit_withdraw_roundtrip() {
    let (token, vault) = setup();
    fund_and_approve(token, vault, user1(), 1000);

    let shares = deposit_as(vault, user1(), 400);
    assert!(shares == 400, "first deposit must mint shares == amount");
    assert!(vault.total_assets() == 400, "total_assets after deposit wrong");
    assert!(vault.total_shares() == 400, "total_shares after deposit wrong");
    assert!(vault.shares_of(user1()) == 400, "shares_of after deposit wrong");
    assert!(token.balance_of(user1()) == 600, "user token balance after deposit wrong");
    assert!(token.balance_of(vault.contract_address) == 400, "vault token balance wrong");

    let assets = withdraw_as(vault, user1(), 400);
    assert!(assets == 400, "withdraw should return all assets");
    assert!(token.balance_of(user1()) == 1000, "user balance not restored");
    assert!(vault.total_assets() == 0, "total_assets not zero after full exit");
    assert!(vault.total_shares() == 0, "total_shares not zero after full exit");
    assert!(vault.shares_of(user1()) == 0, "shares not burned");
}

#[test]
fn test_two_users_proportional_shares() {
    let (token, vault) = setup();
    fund_and_approve(token, vault, user1(), 100);
    fund_and_approve(token, vault, user2(), 300);

    let s1 = deposit_as(vault, user1(), 100);
    let s2 = deposit_as(vault, user2(), 300);
    assert!(s1 == 100, "user1 shares wrong");
    assert!(s2 == 300, "user2 shares must be proportional to deposit");
    assert!(vault.total_shares() == 400, "total_shares wrong");
    assert!(vault.total_assets() == 400, "total_assets wrong");

    let assets = withdraw_as(vault, user2(), 300);
    assert!(assets == 300, "user2 should redeem exactly its deposit");
    assert!(token.balance_of(user2()) == 300, "user2 token balance wrong");
    assert!(vault.total_assets() == 100, "total_assets after withdraw wrong");
    assert!(vault.shares_of(user1()) == 100, "user1 shares must be untouched");
}

#[test]
fn test_donation_does_not_change_share_price() {
    let (token, vault) = setup();
    fund_and_approve(token, vault, user1(), 100);
    fund_and_approve(token, vault, user2(), 100);

    deposit_as(vault, user1(), 100);
    // donate tokens straight to the vault address: must NOT affect tracked accounting
    token.mint(vault.contract_address, 1000);
    assert!(vault.total_assets() == 100, "donation must not change total_assets");

    let s2 = deposit_as(vault, user2(), 100);
    assert!(s2 == 100, "share price must be unchanged by donation");
    assert!(vault.total_assets() == 200, "total_assets after second deposit wrong");

    let assets = withdraw_as(vault, user2(), 100);
    assert!(assets == 100, "withdraw must pay out at tracked share price");
}

#[test]
#[should_panic(expected: 'Vault: zero amount')]
fn test_deposit_zero_panics() {
    let (token, vault) = setup();
    fund_and_approve(token, vault, user1(), 100);
    deposit_as(vault, user1(), 0);
}

#[test]
#[should_panic(expected: 'Vault: zero shares')]
fn test_withdraw_zero_panics() {
    let (token, vault) = setup();
    fund_and_approve(token, vault, user1(), 100);
    deposit_as(vault, user1(), 100);
    withdraw_as(vault, user1(), 0);
}

#[test]
#[should_panic(expected: 'Vault: insufficient shares')]
fn test_withdraw_more_than_balance_panics() {
    let (token, vault) = setup();
    fund_and_approve(token, vault, user1(), 100);
    deposit_as(vault, user1(), 100);
    withdraw_as(vault, user1(), 101);
}

#[test]
#[should_panic(expected: 'Token: insufficient allow')]
fn test_deposit_without_approval_panics() {
    let (token, vault) = setup();
    token.mint(user1(), 100);
    deposit_as(vault, user1(), 100);
}

#[test]
#[should_panic(expected: 'Token: insufficient bal')]
fn test_token_transfer_insufficient_balance_panics() {
    let (token, _vault) = setup();
    token.mint(user1(), 50);
    start_cheat_caller_address(token.contract_address, user1());
    token.transfer(user2(), 100);
}

#[test]
fn test_deposit_and_withdraw_events() {
    let (token, vault) = setup();
    fund_and_approve(token, vault, user1(), 200);

    let mut spy = spy_events();
    deposit_as(vault, user1(), 200);
    withdraw_as(vault, user1(), 50);

    let events = spy.get_events().events.span();
    assert!(events.len() == 2, "expected exactly two events");

    let (from0, deposited) = events.at(0);
    assert!(from0 == @vault.contract_address, "Deposited from wrong contract");
    assert!(deposited.keys == @array![selector!("Deposited")], "wrong first event name");
    // fields in declaration order: caller, amount (u256: low, high), shares (u256: low, high)
    assert!(deposited.data == @array![user1().into(), 200, 0, 200, 0], "wrong Deposited data");

    let (from1, withdrawn) = events.at(1);
    assert!(from1 == @vault.contract_address, "Withdrawn from wrong contract");
    assert!(withdrawn.keys == @array![selector!("Withdrawn")], "wrong second event name");
    // fields in declaration order: caller, shares (low, high), assets (low, high)
    assert!(withdrawn.data == @array![user1().into(), 50, 0, 50, 0], "wrong Withdrawn data");
}
