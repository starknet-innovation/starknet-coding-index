use nft::{ISeqNFTDispatcher, ISeqNFTDispatcherTrait};
use snforge_std::{
    ContractClassTrait, DeclareResultTrait, EventSpyTrait, declare, spy_events,
    start_cheat_caller_address, stop_cheat_caller_address,
};
use starknet::ContractAddress;

fn user1() -> ContractAddress {
    111.try_into().unwrap()
}

fn user2() -> ContractAddress {
    222.try_into().unwrap()
}

fn user3() -> ContractAddress {
    333.try_into().unwrap()
}

fn zero() -> ContractAddress {
    0.try_into().unwrap()
}

fn deploy(max_supply: u64) -> ISeqNFTDispatcher {
    let contract = declare("SeqNFT").unwrap().contract_class();
    let (address, _) = contract.deploy(@array!['MyNFT', 'MNFT', max_supply.into()]).unwrap();
    ISeqNFTDispatcher { contract_address: address }
}

fn mint_as(nft: ISeqNFTDispatcher, minter: ContractAddress) -> u64 {
    start_cheat_caller_address(nft.contract_address, minter);
    let id = nft.mint();
    stop_cheat_caller_address(nft.contract_address);
    id
}

#[test]
fn test_metadata_and_sequential_mint() {
    let nft = deploy(10);
    assert!(nft.name() == 'MyNFT', "wrong name");
    assert!(nft.symbol() == 'MNFT', "wrong symbol");
    assert!(nft.max_supply() == 10, "wrong max supply");
    assert!(nft.total_minted() == 0, "should start at zero minted");

    let id1 = mint_as(nft, user1());
    let id2 = mint_as(nft, user1());
    let id3 = mint_as(nft, user2());
    assert!(id1 == 1, "first id must be 1");
    assert!(id2 == 2, "second id must be 2");
    assert!(id3 == 3, "third id must be 3");
    assert!(nft.total_minted() == 3, "total_minted wrong");
    assert!(nft.owner_of(1) == user1(), "owner of 1 wrong");
    assert!(nft.owner_of(2) == user1(), "owner of 2 wrong");
    assert!(nft.owner_of(3) == user2(), "owner of 3 wrong");
    assert!(nft.balance_of(user1()) == 2, "balance user1 wrong");
    assert!(nft.balance_of(user2()) == 1, "balance user2 wrong");
    assert!(nft.balance_of(user3()) == 0, "balance user3 should be 0");
}

#[test]
fn test_mint_emits_transfer_event() {
    let nft = deploy(5);
    let mut spy = spy_events();
    mint_as(nft, user1());
    let events = spy.get_events().events.span();
    assert!(events.len() == 1, "expected exactly one event");
    let (from, event) = events.at(0);
    assert!(from == @nft.contract_address, "event from wrong contract");
    assert!(event.keys == @array![selector!("Transfer")], "wrong event name");
    // fields in declaration order: from (zero), to, token_id
    assert!(event.data == @array![0, user1().into(), 1], "wrong Transfer data on mint");
}

#[test]
#[should_panic(expected: 'NFT: max supply')]
fn test_mint_beyond_max_supply_panics() {
    let nft = deploy(2);
    mint_as(nft, user1());
    mint_as(nft, user1());
    mint_as(nft, user2());
}

#[test]
fn test_owner_transfer_updates_state_and_emits() {
    let nft = deploy(5);
    let id = mint_as(nft, user1());
    let mut spy = spy_events();
    start_cheat_caller_address(nft.contract_address, user1());
    nft.transfer(user2(), id);
    stop_cheat_caller_address(nft.contract_address);

    assert!(nft.owner_of(id) == user2(), "new owner wrong");
    assert!(nft.balance_of(user1()) == 0, "sender balance wrong");
    assert!(nft.balance_of(user2()) == 1, "receiver balance wrong");

    let events = spy.get_events().events.span();
    assert!(events.len() == 1, "expected exactly one event");
    let (_, event) = events.at(0);
    assert!(event.keys == @array![selector!("Transfer")], "wrong event name");
    assert!(event.data == @array![user1().into(), user2().into(), id.into()], "wrong Transfer data");
}

#[test]
fn test_approve_and_approved_transfer_flow() {
    let nft = deploy(5);
    let id = mint_as(nft, user1());

    let mut spy = spy_events();
    start_cheat_caller_address(nft.contract_address, user1());
    nft.approve(user2(), id);
    stop_cheat_caller_address(nft.contract_address);
    assert!(nft.get_approved(id) == user2(), "approval not stored");

    let events = spy.get_events().events.span();
    assert!(events.len() == 1, "expected exactly one event after approve");
    let (_, event) = events.at(0);
    assert!(event.keys == @array![selector!("Approval")], "wrong event name");
    // fields in declaration order: owner, approved, token_id
    assert!(event.data == @array![user1().into(), user2().into(), id.into()], "wrong Approval data");

    // approved third party moves the token to user3
    start_cheat_caller_address(nft.contract_address, user2());
    nft.transfer(user3(), id);
    stop_cheat_caller_address(nft.contract_address);

    assert!(nft.owner_of(id) == user3(), "owner after approved transfer wrong");
    assert!(nft.get_approved(id) == zero(), "approval must be cleared");
    assert!(nft.balance_of(user1()) == 0, "old owner balance wrong");
    assert!(nft.balance_of(user3()) == 1, "new owner balance wrong");
}

#[test]
#[should_panic(expected: 'NFT: not owner')]
fn test_approve_not_owner_panics() {
    let nft = deploy(5);
    let id = mint_as(nft, user1());
    start_cheat_caller_address(nft.contract_address, user2());
    nft.approve(user3(), id);
}

#[test]
#[should_panic(expected: 'NFT: not authorized')]
fn test_unauthorized_transfer_panics() {
    let nft = deploy(5);
    let id = mint_as(nft, user1());
    start_cheat_caller_address(nft.contract_address, user2());
    nft.transfer(user3(), id);
}

#[test]
#[should_panic(expected: 'NFT: zero address')]
fn test_transfer_to_zero_address_panics() {
    let nft = deploy(5);
    let id = mint_as(nft, user1());
    start_cheat_caller_address(nft.contract_address, user1());
    nft.transfer(zero(), id);
}

#[test]
#[should_panic(expected: 'NFT: invalid token')]
fn test_owner_of_invalid_token_panics() {
    let nft = deploy(5);
    nft.owner_of(1);
}

#[test]
#[should_panic(expected: 'NFT: invalid token')]
fn test_get_approved_invalid_token_panics() {
    let nft = deploy(5);
    nft.get_approved(7);
}
