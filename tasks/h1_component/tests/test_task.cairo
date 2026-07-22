use pausable_machine::{
    IMachineDispatcher, IMachineDispatcherTrait, IPausableDispatcher, IPausableDispatcherTrait,
};
use snforge_std::{
    ContractClassTrait, DeclareResultTrait, EventSpyTrait, declare, spy_events,
    start_cheat_caller_address, stop_cheat_caller_address,
};
use starknet::ContractAddress;

fn operator() -> ContractAddress {
    111.try_into().unwrap()
}

fn deploy() -> (IMachineDispatcher, IPausableDispatcher) {
    let contract = declare("Machine").unwrap().contract_class();
    let (address, _) = contract.deploy(@array![]).unwrap();
    (IMachineDispatcher { contract_address: address }, IPausableDispatcher { contract_address: address })
}

#[test]
fn test_tick_increments() {
    let (machine, _) = deploy();
    assert!(machine.get_ticks() == 0, "ticks should start at 0");
    assert!(machine.tick() == 1, "first tick should return 1");
    assert!(machine.tick() == 2, "second tick should return 2");
    assert!(machine.get_ticks() == 2, "get_ticks should be 2");
}

#[test]
fn test_initially_not_paused() {
    let (_, pausable) = deploy();
    assert!(!pausable.is_paused(), "machine should deploy unpaused");
}

#[test]
fn test_pause_unpause_roundtrip() {
    let (machine, pausable) = deploy();
    machine.tick();
    pausable.pause();
    assert!(pausable.is_paused(), "should be paused after pause()");
    pausable.unpause();
    assert!(!pausable.is_paused(), "should be unpaused after unpause()");
    assert!(machine.tick() == 2, "tick should work again after unpause");
}

#[test]
#[should_panic(expected: 'Pausable: paused')]
fn test_tick_when_paused_panics() {
    let (machine, pausable) = deploy();
    machine.tick();
    pausable.pause();
    machine.tick();
}

#[test]
#[should_panic(expected: 'Pausable: paused')]
fn test_double_pause_panics() {
    let (_, pausable) = deploy();
    pausable.pause();
    pausable.pause();
}

#[test]
#[should_panic(expected: 'Pausable: not paused')]
fn test_unpause_when_not_paused_panics() {
    let (_, pausable) = deploy();
    pausable.unpause();
}

#[test]
fn test_paused_event() {
    let (_, pausable) = deploy();
    start_cheat_caller_address(pausable.contract_address, operator());
    let mut spy = spy_events();
    pausable.pause();
    stop_cheat_caller_address(pausable.contract_address);
    let events = spy.get_events().events.span();
    assert!(events.len() == 1, "expected exactly one event");
    let (from, event) = events.at(0);
    assert!(from == @pausable.contract_address, "event from wrong contract");
    // #[flat] on PausableEvent: keys hold the bare component variant selector
    assert!(event.keys == @array![selector!("Paused")], "wrong event name");
    assert!(event.data == @array![operator().into()], "wrong event data");
}

#[test]
fn test_unpaused_event() {
    let (_, pausable) = deploy();
    start_cheat_caller_address(pausable.contract_address, operator());
    pausable.pause();
    let mut spy = spy_events();
    pausable.unpause();
    stop_cheat_caller_address(pausable.contract_address);
    let events = spy.get_events().events.span();
    assert!(events.len() == 1, "expected exactly one event");
    let (from, event) = events.at(0);
    assert!(from == @pausable.contract_address, "event from wrong contract");
    assert!(event.keys == @array![selector!("Unpaused")], "wrong event name");
    assert!(event.data == @array![operator().into()], "wrong event data");
}
