use ownable::{IVaultDispatcher, IVaultDispatcherTrait};
use snforge_std::{
    ContractClassTrait, DeclareResultTrait, EventSpyTrait, declare, spy_events,
    start_cheat_caller_address, stop_cheat_caller_address,
};
use starknet::ContractAddress;

fn owner() -> ContractAddress {
    111.try_into().unwrap()
}

fn other() -> ContractAddress {
    222.try_into().unwrap()
}

fn deploy(initial_owner: ContractAddress) -> IVaultDispatcher {
    let contract = declare("Vault").unwrap().contract_class();
    let (address, _) = contract.deploy(@array![initial_owner.into()]).unwrap();
    IVaultDispatcher { contract_address: address }
}

#[test]
fn test_constructor_sets_owner_and_value_starts_at_zero() {
    let vault = deploy(owner());
    assert!(vault.get_owner() == owner(), "owner not set by constructor");
    assert!(vault.get_value() == 0, "initial value should be 0");
}

#[test]
fn test_owner_can_set_value() {
    let vault = deploy(owner());
    start_cheat_caller_address(vault.contract_address, owner());
    vault.set_value(42);
    stop_cheat_caller_address(vault.contract_address);
    assert!(vault.get_value() == 42, "value not stored");
}

#[test]
#[should_panic(expected: 'Vault: not owner')]
fn test_non_owner_set_value_panics() {
    let vault = deploy(owner());
    start_cheat_caller_address(vault.contract_address, other());
    vault.set_value(1);
}

#[test]
fn test_transfer_ownership_new_owner_can_set() {
    let vault = deploy(owner());
    start_cheat_caller_address(vault.contract_address, owner());
    vault.transfer_ownership(other());
    stop_cheat_caller_address(vault.contract_address);
    assert!(vault.get_owner() == other(), "owner not updated");
    start_cheat_caller_address(vault.contract_address, other());
    vault.set_value(7);
    stop_cheat_caller_address(vault.contract_address);
    assert!(vault.get_value() == 7, "new owner could not set value");
}

#[test]
#[should_panic(expected: 'Vault: not owner')]
fn test_old_owner_cannot_set_after_transfer() {
    let vault = deploy(owner());
    start_cheat_caller_address(vault.contract_address, owner());
    vault.transfer_ownership(other());
    // still cheating as the old owner
    vault.set_value(9);
}

#[test]
#[should_panic(expected: 'Vault: zero owner')]
fn test_transfer_to_zero_address_panics() {
    let vault = deploy(owner());
    let zero: ContractAddress = 0.try_into().unwrap();
    start_cheat_caller_address(vault.contract_address, owner());
    vault.transfer_ownership(zero);
}

#[test]
fn test_transfer_emits_event() {
    let vault = deploy(owner());
    let mut spy = spy_events();
    start_cheat_caller_address(vault.contract_address, owner());
    vault.transfer_ownership(other());
    stop_cheat_caller_address(vault.contract_address);
    let events = spy.get_events().events.span();
    assert!(events.len() == 1, "expected exactly one event");
    let (from, event) = events.at(0);
    assert!(from == @vault.contract_address, "event from wrong contract");
    assert!(event.keys == @array![selector!("OwnershipTransferred")], "wrong event name");
    // struct fields land in data in declaration order: previous, new
    let expected: Array<felt252> = array![owner().into(), other().into()];
    assert!(event.data == @expected, "wrong event data");
}
