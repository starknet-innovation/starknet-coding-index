use registry::{IRegistryDispatcher, IRegistryDispatcherTrait};
use snforge_std::{
    ContractClassTrait, DeclareResultTrait, EventSpyTrait, declare, spy_events,
    start_cheat_caller_address, stop_cheat_caller_address,
};
use starknet::ContractAddress;

fn user1() -> ContractAddress {
    123.try_into().unwrap()
}

fn user2() -> ContractAddress {
    456.try_into().unwrap()
}

fn deploy() -> IRegistryDispatcher {
    let contract = declare("Registry").unwrap().contract_class();
    let (address, _) = contract.deploy(@array![]).unwrap();
    IRegistryDispatcher { contract_address: address }
}

#[test]
fn test_register_and_name_of() {
    let registry = deploy();
    start_cheat_caller_address(registry.contract_address, user1());
    registry.register('alice');
    stop_cheat_caller_address(registry.contract_address);
    assert!(registry.name_of(user1()) == 'alice', "name not stored");
    assert!(registry.total_registered() == 1, "count should be 1");
}

#[test]
fn test_unregistered_account_returns_zero() {
    let registry = deploy();
    assert!(registry.name_of(user1()) == 0, "unregistered should be 0");
    assert!(registry.total_registered() == 0, "count should start at 0");
}

#[test]
fn test_overwrite_does_not_bump_count() {
    let registry = deploy();
    start_cheat_caller_address(registry.contract_address, user1());
    registry.register('alice');
    registry.register('bob');
    stop_cheat_caller_address(registry.contract_address);
    assert!(registry.name_of(user1()) == 'bob', "overwrite did not stick");
    assert!(registry.total_registered() == 1, "overwrite must not bump count");
}

#[test]
fn test_distinct_callers_bump_count() {
    let registry = deploy();
    start_cheat_caller_address(registry.contract_address, user1());
    registry.register('alice');
    stop_cheat_caller_address(registry.contract_address);
    start_cheat_caller_address(registry.contract_address, user2());
    registry.register('bob');
    stop_cheat_caller_address(registry.contract_address);
    assert!(registry.total_registered() == 2, "count should be 2");
    assert!(registry.name_of(user1()) == 'alice', "user1 name wrong");
    assert!(registry.name_of(user2()) == 'bob', "user2 name wrong");
}

#[test]
#[should_panic(expected: 'Registry: empty name')]
fn test_empty_name_panics() {
    let registry = deploy();
    start_cheat_caller_address(registry.contract_address, user1());
    registry.register(0);
}

#[test]
fn test_register_emits_event() {
    let registry = deploy();
    let mut spy = spy_events();
    start_cheat_caller_address(registry.contract_address, user1());
    registry.register('alice');
    stop_cheat_caller_address(registry.contract_address);
    let events = spy.get_events().events.span();
    assert!(events.len() == 1, "expected exactly one event");
    let (from, event) = events.at(0);
    assert!(from == @registry.contract_address, "event from wrong contract");
    assert!(event.keys == @array![selector!("Registered")], "wrong event name");
    // struct fields land in data in declaration order: account, name
    let expected: Array<felt252> = array![user1().into(), 'alice'];
    assert!(event.data == @expected, "wrong event data");
}
