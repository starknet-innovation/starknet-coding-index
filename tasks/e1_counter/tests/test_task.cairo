use counter::{ICounterDispatcher, ICounterDispatcherTrait};
use snforge_std::{declare, ContractClassTrait, DeclareResultTrait, spy_events};
use starknet::ContractAddress;

fn deploy(initial: u64) -> ICounterDispatcher {
    let contract = declare("Counter").unwrap().contract_class();
    let (address, _) = contract.deploy(@array![initial.into()]).unwrap();
    ICounterDispatcher { contract_address: address }
}

#[test]
fn test_constructor_sets_initial_value() {
    let counter = deploy(42);
    assert!(counter.get() == 42, "initial value wrong");
}

#[test]
fn test_increment() {
    let counter = deploy(10);
    counter.increment(5);
    assert!(counter.get() == 15, "increment failed");
    counter.increment(0);
    assert!(counter.get() == 15, "increment by zero changed value");
}

#[test]
fn test_decrement() {
    let counter = deploy(10);
    counter.decrement(4);
    assert!(counter.get() == 6, "decrement failed");
    counter.decrement(6);
    assert!(counter.get() == 0, "decrement to zero failed");
}

#[test]
#[should_panic(expected: 'Counter: underflow')]
fn test_decrement_underflow_panics() {
    let counter = deploy(3);
    counter.decrement(4);
}

#[test]
fn test_increment_emits_event() {
    let counter = deploy(0);
    let mut spy = spy_events();
    counter.increment(7);
    let events = spy.get_events();
    assert!(events.events.len() == 1, "expected exactly one event");
    let (from, event) = events.events.at(0);
    assert!(from == @counter.contract_address, "event from wrong contract");
    assert!(event.keys.at(0) == @selector!("Incremented"), "wrong event name");
    // struct fields land in data in declaration order: amount, new_value
    assert!(event.data.at(0) == @7, "wrong amount in event");
    assert!(event.data.at(1) == @7, "wrong new_value in event");
}

#[test]
fn test_decrement_emits_event() {
    let counter = deploy(10);
    let mut spy = spy_events();
    counter.decrement(3);
    let events = spy.get_events();
    assert!(events.events.len() == 1, "expected exactly one event");
    let (from, event) = events.events.at(0);
    assert!(from == @counter.contract_address, "event from wrong contract");
    assert!(event.keys.at(0) == @selector!("Decremented"), "wrong event name");
    assert!(event.data.at(0) == @3, "wrong amount in event");
    assert!(event.data.at(1) == @7, "wrong new_value in event");
}
