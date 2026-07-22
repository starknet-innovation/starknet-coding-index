use item_store::{IItemStoreDispatcher, IItemStoreDispatcherTrait, Item};
use snforge_std::{
    ContractClassTrait, DeclareResultTrait, EventSpyTrait, declare, spy_events,
    start_cheat_caller_address, stop_cheat_caller_address,
};
use starknet::ContractAddress;

fn alice() -> ContractAddress {
    111.try_into().unwrap()
}

fn bob() -> ContractAddress {
    222.try_into().unwrap()
}

fn deploy() -> IItemStoreDispatcher {
    let contract = declare("ItemStoreContract").unwrap().contract_class();
    let (address, _) = contract.deploy(@array![]).unwrap();
    IItemStoreDispatcher { contract_address: address }
}

#[test]
fn test_create_get_roundtrip_and_sequential_ids() {
    let store = deploy();
    start_cheat_caller_address(store.contract_address, alice());
    let id1 = store.create_item(500);
    let id2 = store.create_item(900);
    stop_cheat_caller_address(store.contract_address);
    start_cheat_caller_address(store.contract_address, bob());
    let id3 = store.create_item(1);
    stop_cheat_caller_address(store.contract_address);

    assert!(id1 == 1, "first id should be 1");
    assert!(id2 == 2, "second id should be 2");
    assert!(id3 == 3, "third id should be 3");
    assert!(store.item_count() == 3, "item_count should be 3");

    let item1 = store.get_item(1);
    assert!(
        item1 == Item { id: 1, owner: alice(), price: 500, active: true }, "item 1 wrong",
    );
    let item3 = store.get_item(3);
    assert!(item3 == Item { id: 3, owner: bob(), price: 1, active: true }, "item 3 wrong");
}

#[test]
#[should_panic(expected: 'Item: zero price')]
fn test_create_zero_price_panics() {
    let store = deploy();
    start_cheat_caller_address(store.contract_address, alice());
    store.create_item(0);
}

#[test]
fn test_update_price_happy() {
    let store = deploy();
    start_cheat_caller_address(store.contract_address, alice());
    let id = store.create_item(500);
    store.update_price(id, 750);
    stop_cheat_caller_address(store.contract_address);
    let item = store.get_item(id);
    assert!(item.price == 750, "price should be updated");
    assert!(item.owner == alice(), "owner should be unchanged");
    assert!(item.active, "item should stay active");
}

#[test]
#[should_panic(expected: 'Item: not owner')]
fn test_update_price_not_owner_panics() {
    let store = deploy();
    start_cheat_caller_address(store.contract_address, alice());
    let id = store.create_item(500);
    stop_cheat_caller_address(store.contract_address);
    start_cheat_caller_address(store.contract_address, bob());
    store.update_price(id, 750);
}

#[test]
#[should_panic(expected: 'Item: zero price')]
fn test_update_price_zero_panics() {
    let store = deploy();
    start_cheat_caller_address(store.contract_address, alice());
    let id = store.create_item(500);
    store.update_price(id, 0);
}

#[test]
#[should_panic(expected: 'Item: inactive')]
fn test_deactivate_then_double_deactivate_panics() {
    let store = deploy();
    start_cheat_caller_address(store.contract_address, alice());
    let id = store.create_item(500);
    store.deactivate(id);
    let item = store.get_item(id);
    assert!(!item.active, "item should be inactive after deactivate");
    store.deactivate(id);
}

#[test]
#[should_panic(expected: 'Item: inactive')]
fn test_update_price_after_deactivate_panics() {
    let store = deploy();
    start_cheat_caller_address(store.contract_address, alice());
    let id = store.create_item(500);
    store.deactivate(id);
    store.update_price(id, 750);
}

#[test]
#[should_panic(expected: 'Item: not found')]
fn test_get_item_not_found_panics() {
    let store = deploy();
    start_cheat_caller_address(store.contract_address, alice());
    store.create_item(500);
    store.get_item(999);
}

#[test]
fn test_create_emits_event() {
    let store = deploy();
    start_cheat_caller_address(store.contract_address, alice());
    let mut spy = spy_events();
    store.create_item(500);
    stop_cheat_caller_address(store.contract_address);
    let events = spy.get_events().events.span();
    assert!(events.len() == 1, "expected exactly one event");
    let (from, event) = events.at(0);
    assert!(from == @store.contract_address, "event from wrong contract");
    assert!(event.keys == @array![selector!("ItemCreated")], "wrong event name");
    // data in field declaration order: id, owner, price
    assert!(event.data == @array![1, alice().into(), 500], "wrong event data");
}
