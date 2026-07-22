use erc20_capped::{ICappedTokenDispatcher, ICappedTokenDispatcherTrait};
use snforge_std::{
    ContractClassTrait, DeclareResultTrait, EventSpyTrait, declare, spy_events,
    start_cheat_caller_address, stop_cheat_caller_address,
};
use starknet::ContractAddress;

fn minter() -> ContractAddress {
    111.try_into().unwrap()
}

fn user() -> ContractAddress {
    222.try_into().unwrap()
}

fn other() -> ContractAddress {
    333.try_into().unwrap()
}

fn spender() -> ContractAddress {
    444.try_into().unwrap()
}

// cap = 1_000_000 (u256 -> two felts: low, high)
fn deploy() -> ICappedTokenDispatcher {
    let contract = declare("CappedToken").unwrap().contract_class();
    let (address, _) = contract
        .deploy(@array!['Capped Token', 'CAP', 1000000, 0, minter().into()])
        .unwrap();
    ICappedTokenDispatcher { contract_address: address }
}

fn mint(token: ICappedTokenDispatcher, to: ContractAddress, amount: u256) {
    start_cheat_caller_address(token.contract_address, minter());
    token.mint(to, amount);
    stop_cheat_caller_address(token.contract_address);
}

#[test]
fn test_metadata_and_mint() {
    let token = deploy();
    assert!(token.name() == 'Capped Token', "wrong name");
    assert!(token.symbol() == 'CAP', "wrong symbol");
    assert!(token.decimals() == 18, "wrong decimals");
    assert!(token.cap() == 1000000, "wrong cap");
    assert!(token.total_supply() == 0, "initial supply not zero");
    mint(token, user(), 1000);
    assert!(token.balance_of(user()) == 1000, "balance after mint wrong");
    assert!(token.total_supply() == 1000, "supply after mint wrong");
    mint(token, other(), 500);
    assert!(token.balance_of(other()) == 500, "second balance wrong");
    assert!(token.total_supply() == 1500, "supply after second mint wrong");
}

#[test]
#[should_panic(expected: 'ERC20: cap exceeded')]
fn test_mint_above_cap_panics() {
    let token = deploy();
    mint(token, user(), 900000);
    // exactly reaching the cap is fine
    mint(token, user(), 100000);
    assert!(token.total_supply() == 1000000, "supply should equal cap");
    mint(token, user(), 1);
}

#[test]
#[should_panic(expected: 'ERC20: not minter')]
fn test_mint_from_non_minter_panics() {
    let token = deploy();
    start_cheat_caller_address(token.contract_address, user());
    token.mint(user(), 100);
}

#[test]
fn test_transfer_moves_balance() {
    let token = deploy();
    mint(token, user(), 1000);
    start_cheat_caller_address(token.contract_address, user());
    let ok = token.transfer(other(), 400);
    stop_cheat_caller_address(token.contract_address);
    assert!(ok, "transfer should return true");
    assert!(token.balance_of(user()) == 600, "sender balance wrong");
    assert!(token.balance_of(other()) == 400, "recipient balance wrong");
    assert!(token.total_supply() == 1000, "supply must not change");
}

#[test]
#[should_panic(expected: 'ERC20: insufficient bal')]
fn test_transfer_insufficient_balance_panics() {
    let token = deploy();
    mint(token, user(), 100);
    start_cheat_caller_address(token.contract_address, user());
    token.transfer(other(), 101);
}

#[test]
fn test_approve_and_transfer_from() {
    let token = deploy();
    mint(token, user(), 1000);

    start_cheat_caller_address(token.contract_address, user());
    let ok = token.approve(spender(), 500);
    stop_cheat_caller_address(token.contract_address);
    assert!(ok, "approve should return true");
    assert!(token.allowance(user(), spender()) == 500, "allowance not set");

    start_cheat_caller_address(token.contract_address, spender());
    let ok2 = token.transfer_from(user(), other(), 300);
    stop_cheat_caller_address(token.contract_address);
    assert!(ok2, "transfer_from should return true");
    assert!(token.balance_of(user()) == 700, "owner balance wrong");
    assert!(token.balance_of(other()) == 300, "recipient balance wrong");
    assert!(token.allowance(user(), spender()) == 200, "allowance not decremented");
}

#[test]
#[should_panic(expected: 'ERC20: insufficient allow')]
fn test_transfer_from_exceeding_allowance_panics() {
    let token = deploy();
    mint(token, user(), 1000);
    start_cheat_caller_address(token.contract_address, user());
    token.approve(spender(), 100);
    stop_cheat_caller_address(token.contract_address);
    start_cheat_caller_address(token.contract_address, spender());
    token.transfer_from(user(), other(), 200);
}

#[test]
fn test_transfer_events() {
    let token = deploy();
    let mut spy = spy_events();

    mint(token, user(), 1000);
    start_cheat_caller_address(token.contract_address, user());
    token.transfer(other(), 250);
    stop_cheat_caller_address(token.contract_address);

    let events = spy.get_events().events.span();
    assert!(events.len() == 2, "expected two events");

    // mint: Transfer { from: 0, to: user, value: 1000 } (u256 -> low, high)
    let (from0, e0) = events.at(0);
    assert!(from0 == @token.contract_address, "mint event from wrong contract");
    assert!(e0.keys == @array![selector!("Transfer")], "mint event wrong name");
    assert!(e0.data == @array![0, user().into(), 1000, 0], "mint event wrong data");

    // transfer: Transfer { from: user, to: other, value: 250 }
    let (from1, e1) = events.at(1);
    assert!(from1 == @token.contract_address, "transfer event from wrong contract");
    assert!(e1.keys == @array![selector!("Transfer")], "transfer event wrong name");
    assert!(e1.data == @array![user().into(), other().into(), 250, 0], "transfer event wrong data");
}

#[test]
fn test_approval_event() {
    let token = deploy();
    let mut spy = spy_events();
    start_cheat_caller_address(token.contract_address, user());
    token.approve(spender(), 500);
    stop_cheat_caller_address(token.contract_address);

    let events = spy.get_events().events.span();
    assert!(events.len() == 1, "expected one event");
    let (from, event) = events.at(0);
    assert!(from == @token.contract_address, "event from wrong contract");
    assert!(event.keys == @array![selector!("Approval")], "wrong event name");
    assert!(event.data == @array![user().into(), spender().into(), 500, 0], "wrong event data");
}
