use snforge_std::{
    ContractClassTrait, DeclareResultTrait, EventSpyTrait, declare, spy_events,
    start_cheat_block_timestamp, start_cheat_caller_address, stop_cheat_block_timestamp,
    stop_cheat_caller_address,
};
use starknet::ContractAddress;
use voting::{IBallotDispatcher, IBallotDispatcherTrait};

fn alice() -> ContractAddress {
    101.try_into().unwrap()
}

fn bob() -> ContractAddress {
    102.try_into().unwrap()
}

fn carol() -> ContractAddress {
    103.try_into().unwrap()
}

fn deploy() -> IBallotDispatcher {
    let contract = declare("Ballot").unwrap().contract_class();
    let (address, _) = contract.deploy(@array![]).unwrap();
    IBallotDispatcher { contract_address: address }
}

fn vote_as(ballot: IBallotDispatcher, voter: ContractAddress, id: u64, support: bool) {
    start_cheat_caller_address(ballot.contract_address, voter);
    ballot.vote(id, support);
    stop_cheat_caller_address(ballot.contract_address);
}

#[test]
fn test_create_and_tally() {
    let ballot = deploy();
    start_cheat_block_timestamp(ballot.contract_address, 1000);
    let id1 = ballot.create_proposal('first', 3600);
    let id2 = ballot.create_proposal('second', 100);
    assert!(id1 == 1, "first id must be 1");
    assert!(id2 == 2, "second id must be 2");

    vote_as(ballot, alice(), 1, true);
    vote_as(ballot, bob(), 1, true);
    vote_as(ballot, carol(), 1, false);

    let (yes, no) = ballot.get_votes(1);
    assert!(yes == 2, "yes tally wrong");
    assert!(no == 1, "no tally wrong");
    let (yes2, no2) = ballot.get_votes(2);
    assert!(yes2 == 0 && no2 == 0, "untouched proposal must be 0/0");
    stop_cheat_block_timestamp(ballot.contract_address);
}

#[test]
#[should_panic(expected: 'Ballot: zero duration')]
fn test_zero_duration_panics() {
    let ballot = deploy();
    ballot.create_proposal('bad', 0);
}

#[test]
#[should_panic(expected: 'Ballot: already voted')]
fn test_double_vote_panics() {
    let ballot = deploy();
    start_cheat_block_timestamp(ballot.contract_address, 1000);
    ballot.create_proposal('prop', 3600);
    vote_as(ballot, alice(), 1, true);
    vote_as(ballot, alice(), 1, false);
}

#[test]
#[should_panic(expected: 'Ballot: voting closed')]
fn test_vote_at_deadline_panics() {
    let ballot = deploy();
    start_cheat_block_timestamp(ballot.contract_address, 1000);
    ballot.create_proposal('prop', 100);
    // voting is open strictly before the deadline; at deadline (1100) it is closed
    start_cheat_block_timestamp(ballot.contract_address, 1100);
    vote_as(ballot, alice(), 1, true);
}

#[test]
#[should_panic(expected: 'Ballot: no proposal')]
fn test_vote_unknown_proposal_panics() {
    let ballot = deploy();
    start_cheat_block_timestamp(ballot.contract_address, 1000);
    ballot.create_proposal('prop', 3600);
    vote_as(ballot, alice(), 99, true);
}

#[test]
#[should_panic(expected: 'Ballot: no proposal')]
fn test_get_votes_unknown_proposal_panics() {
    let ballot = deploy();
    ballot.get_votes(1);
}

#[test]
fn test_has_passed() {
    let ballot = deploy();
    start_cheat_block_timestamp(ballot.contract_address, 1000);
    // proposal 1: 2 yes / 1 no -> passes after deadline
    ballot.create_proposal('winner', 100);
    // proposal 2: 1 yes / 1 no (tie) -> never passes
    ballot.create_proposal('tie', 100);
    vote_as(ballot, alice(), 1, true);
    vote_as(ballot, bob(), 1, true);
    vote_as(ballot, carol(), 1, false);
    vote_as(ballot, alice(), 2, true);
    vote_as(ballot, bob(), 2, false);

    // before deadline: never passed, even with a majority
    start_cheat_block_timestamp(ballot.contract_address, 1099);
    assert!(!ballot.has_passed(1), "must not pass before deadline");

    // at/after deadline: majority passes, tie does not
    start_cheat_block_timestamp(ballot.contract_address, 1100);
    assert!(ballot.has_passed(1), "majority must pass after deadline");
    assert!(!ballot.has_passed(2), "tie must not pass");
    stop_cheat_block_timestamp(ballot.contract_address);
}

#[test]
fn test_proposal_created_event() {
    let ballot = deploy();
    start_cheat_block_timestamp(ballot.contract_address, 1000);
    start_cheat_caller_address(ballot.contract_address, alice());
    let mut spy = spy_events();
    ballot.create_proposal('prop', 250);
    stop_cheat_caller_address(ballot.contract_address);

    let events = spy.get_events().events.span();
    assert!(events.len() == 1, "expected exactly one event");
    let (from, event) = events.at(0);
    assert!(from == @ballot.contract_address, "event from wrong contract");
    assert!(event.keys == @array![selector!("ProposalCreated")], "wrong event name");
    // fields in order: id, creator, deadline (1000 + 250)
    assert!(event.data == @array![1, alice().into(), 1250], "wrong event data");
}

#[test]
fn test_vote_cast_event() {
    let ballot = deploy();
    start_cheat_block_timestamp(ballot.contract_address, 1000);
    ballot.create_proposal('prop', 3600);
    let mut spy = spy_events();
    vote_as(ballot, alice(), 1, true);
    vote_as(ballot, bob(), 1, false);

    let events = spy.get_events().events.span();
    assert!(events.len() == 2, "expected two events");
    let (from0, e0) = events.at(0);
    assert!(from0 == @ballot.contract_address, "event from wrong contract");
    assert!(e0.keys == @array![selector!("VoteCast")], "wrong event name");
    // fields in order: id, voter, support (bool -> 1 felt: true = 1)
    assert!(e0.data == @array![1, alice().into(), 1], "wrong yes-vote event data");
    let (_, e1) = events.at(1);
    assert!(e1.keys == @array![selector!("VoteCast")], "wrong second event name");
    assert!(e1.data == @array![1, bob().into(), 0], "wrong no-vote event data");
}
