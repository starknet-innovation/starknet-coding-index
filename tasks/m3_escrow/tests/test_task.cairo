use escrow::{IEscrowDispatcher, IEscrowDispatcherTrait};
use snforge_std::{
    ContractClassTrait, DeclareResultTrait, EventSpyTrait, declare, spy_events,
    start_cheat_block_timestamp, start_cheat_caller_address, stop_cheat_block_timestamp,
    stop_cheat_caller_address,
};
use starknet::ContractAddress;

fn depositor() -> ContractAddress {
    11.try_into().unwrap()
}

fn ben() -> ContractAddress {
    22.try_into().unwrap()
}

fn other() -> ContractAddress {
    33.try_into().unwrap()
}

fn deploy() -> IEscrowDispatcher {
    let contract = declare("Escrow").unwrap().contract_class();
    let (address, _) = contract.deploy(@array![]).unwrap();
    IEscrowDispatcher { contract_address: address }
}

fn deposit_as(
    escrow: IEscrowDispatcher,
    caller: ContractAddress,
    beneficiary: ContractAddress,
    amount: u128,
    unlock_time: u64,
) -> u64 {
    start_cheat_caller_address(escrow.contract_address, caller);
    let id = escrow.deposit_for(beneficiary, amount, unlock_time);
    stop_cheat_caller_address(escrow.contract_address);
    id
}

fn withdraw_as(escrow: IEscrowDispatcher, caller: ContractAddress, deposit_id: u64) {
    start_cheat_caller_address(escrow.contract_address, caller);
    escrow.withdraw(deposit_id);
    stop_cheat_caller_address(escrow.contract_address);
}

#[test]
fn test_deposit_and_get_deposit() {
    let escrow = deploy();
    start_cheat_block_timestamp(escrow.contract_address, 1000);
    let id1 = deposit_as(escrow, depositor(), ben(), 500, 2000);
    let id2 = deposit_as(escrow, depositor(), ben(), 300, 3000);
    assert!(id1 == 1, "first deposit id must be 1");
    assert!(id2 == 2, "second deposit id must be 2");

    let (b, amount, unlock, withdrawn) = escrow.get_deposit(1);
    assert!(b == ben(), "wrong beneficiary");
    assert!(amount == 500, "wrong amount");
    assert!(unlock == 2000, "wrong unlock time");
    assert!(!withdrawn, "must not be withdrawn yet");

    assert!(escrow.balance_of(ben()) == 800, "locked balance wrong");
    assert!(escrow.balance_of(other()) == 0, "other balance must be 0");
    stop_cheat_block_timestamp(escrow.contract_address);
}

#[test]
fn test_withdraw_after_unlock() {
    let escrow = deploy();
    start_cheat_block_timestamp(escrow.contract_address, 1000);
    deposit_as(escrow, depositor(), ben(), 500, 2000);
    deposit_as(escrow, depositor(), ben(), 300, 3000);

    // withdrawal allowed at exactly unlock_time
    start_cheat_block_timestamp(escrow.contract_address, 2000);
    withdraw_as(escrow, ben(), 1);

    let (_, _, _, withdrawn) = escrow.get_deposit(1);
    assert!(withdrawn, "withdrawn flag not set");
    assert!(escrow.balance_of(ben()) == 300, "balance not released");
    stop_cheat_block_timestamp(escrow.contract_address);
}

#[test]
#[should_panic(expected: 'Escrow: locked')]
fn test_early_withdraw_panics() {
    let escrow = deploy();
    start_cheat_block_timestamp(escrow.contract_address, 1000);
    deposit_as(escrow, depositor(), ben(), 500, 2000);
    start_cheat_block_timestamp(escrow.contract_address, 1999);
    withdraw_as(escrow, ben(), 1);
}

#[test]
#[should_panic(expected: 'Escrow: not beneficiary')]
fn test_withdraw_by_non_beneficiary_panics() {
    let escrow = deploy();
    start_cheat_block_timestamp(escrow.contract_address, 1000);
    deposit_as(escrow, depositor(), ben(), 500, 2000);
    start_cheat_block_timestamp(escrow.contract_address, 2000);
    withdraw_as(escrow, other(), 1);
}

#[test]
#[should_panic(expected: 'Escrow: already withdrawn')]
fn test_double_withdraw_panics() {
    let escrow = deploy();
    start_cheat_block_timestamp(escrow.contract_address, 1000);
    deposit_as(escrow, depositor(), ben(), 500, 2000);
    start_cheat_block_timestamp(escrow.contract_address, 2000);
    withdraw_as(escrow, ben(), 1);
    withdraw_as(escrow, ben(), 1);
}

#[test]
#[should_panic(expected: 'Escrow: zero amount')]
fn test_zero_amount_panics() {
    let escrow = deploy();
    start_cheat_block_timestamp(escrow.contract_address, 1000);
    deposit_as(escrow, depositor(), ben(), 0, 2000);
}

#[test]
#[should_panic(expected: 'Escrow: bad unlock time')]
fn test_unlock_time_not_in_future_panics() {
    let escrow = deploy();
    start_cheat_block_timestamp(escrow.contract_address, 1000);
    // unlock_time equal to the current timestamp is invalid
    deposit_as(escrow, depositor(), ben(), 500, 1000);
}

#[test]
#[should_panic(expected: 'Escrow: no deposit')]
fn test_withdraw_unknown_deposit_panics() {
    let escrow = deploy();
    start_cheat_block_timestamp(escrow.contract_address, 1000);
    deposit_as(escrow, depositor(), ben(), 500, 2000);
    start_cheat_block_timestamp(escrow.contract_address, 2000);
    withdraw_as(escrow, ben(), 5);
}

#[test]
fn test_events() {
    let escrow = deploy();
    start_cheat_block_timestamp(escrow.contract_address, 1000);
    let mut spy = spy_events();
    deposit_as(escrow, depositor(), ben(), 500, 2000);
    start_cheat_block_timestamp(escrow.contract_address, 2000);
    withdraw_as(escrow, ben(), 1);
    stop_cheat_block_timestamp(escrow.contract_address);

    let events = spy.get_events().events.span();
    assert!(events.len() == 2, "expected two events");

    // Deposited { id, depositor, beneficiary, amount (u128 -> 1 felt), unlock_time }
    let (from0, e0) = events.at(0);
    assert!(from0 == @escrow.contract_address, "deposit event from wrong contract");
    assert!(e0.keys == @array![selector!("Deposited")], "wrong deposit event name");
    assert!(
        e0.data == @array![1, depositor().into(), ben().into(), 500, 2000],
        "wrong deposit event data",
    );

    // Withdrawn { id, beneficiary, amount }
    let (from1, e1) = events.at(1);
    assert!(from1 == @escrow.contract_address, "withdraw event from wrong contract");
    assert!(e1.keys == @array![selector!("Withdrawn")], "wrong withdraw event name");
    assert!(e1.data == @array![1, ben().into(), 500], "wrong withdraw event data");
}
