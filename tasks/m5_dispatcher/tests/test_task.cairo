use oracle_consumer::{
    IConsumerDispatcher, IConsumerDispatcherTrait, IPriceOracleDispatcher,
    IPriceOracleDispatcherTrait,
};
use snforge_std::{
    ContractClassTrait, DeclareResultTrait, declare, start_cheat_caller_address,
    stop_cheat_caller_address,
};
use starknet::ContractAddress;

fn owner() -> ContractAddress {
    111.try_into().unwrap()
}

fn stranger() -> ContractAddress {
    222.try_into().unwrap()
}

fn deploy_oracle(owner_addr: ContractAddress) -> IPriceOracleDispatcher {
    let contract = declare("PriceOracle").unwrap().contract_class();
    let (address, _) = contract.deploy(@array![owner_addr.into()]).unwrap();
    IPriceOracleDispatcher { contract_address: address }
}

fn deploy_consumer(oracle: ContractAddress) -> IConsumerDispatcher {
    let contract = declare("Consumer").unwrap().contract_class();
    let (address, _) = contract.deploy(@array![oracle.into()]).unwrap();
    IConsumerDispatcher { contract_address: address }
}

fn setup() -> (IPriceOracleDispatcher, IConsumerDispatcher) {
    let oracle = deploy_oracle(owner());
    let consumer = deploy_consumer(oracle.contract_address);
    (oracle, consumer)
}

#[test]
fn test_constructor_wiring() {
    let (oracle, consumer) = setup();
    assert!(consumer.get_oracle() == oracle.contract_address, "oracle address wrong");
}

#[test]
fn test_set_price_and_get_price() {
    let (oracle, _) = setup();
    start_cheat_caller_address(oracle.contract_address, owner());
    oracle.set_price('ETH', 3000);
    oracle.set_price('BTC', 60000);
    oracle.set_price('ETH', 3500);
    stop_cheat_caller_address(oracle.contract_address);
    assert!(oracle.get_price('ETH') == 3500, "ETH price wrong after update");
    assert!(oracle.get_price('BTC') == 60000, "BTC price wrong");
}

#[test]
#[should_panic(expected: 'Oracle: not owner')]
fn test_set_price_not_owner_panics() {
    let (oracle, _) = setup();
    start_cheat_caller_address(oracle.contract_address, stranger());
    oracle.set_price('ETH', 3000);
}

#[test]
#[should_panic(expected: 'Oracle: unknown asset')]
fn test_get_price_unknown_asset_panics() {
    let (oracle, _) = setup();
    oracle.get_price('DOGE');
}

#[test]
fn test_quote_math() {
    let (oracle, consumer) = setup();
    start_cheat_caller_address(oracle.contract_address, owner());
    oracle.set_price('ETH', 3000);
    stop_cheat_caller_address(oracle.contract_address);
    assert!(consumer.quote('ETH', 7) == 21000, "quote math wrong");
    assert!(consumer.quote('ETH', 0) == 0, "quote of zero amount should be 0");
}

#[test]
#[should_panic(expected: 'Oracle: unknown asset')]
fn test_quote_unknown_asset_propagates_oracle_panic() {
    let (oracle, consumer) = setup();
    start_cheat_caller_address(oracle.contract_address, owner());
    oracle.set_price('ETH', 3000);
    stop_cheat_caller_address(oracle.contract_address);
    consumer.quote('DOGE', 5);
}

#[test]
#[should_panic(expected: 'Consumer: zero oracle')]
fn test_set_oracle_zero_panics() {
    let (_, consumer) = setup();
    let zero: ContractAddress = 0.try_into().unwrap();
    consumer.set_oracle(zero);
}

#[test]
fn test_rewire_to_second_oracle() {
    let (oracle1, consumer) = setup();
    start_cheat_caller_address(oracle1.contract_address, owner());
    oracle1.set_price('ETH', 3000);
    stop_cheat_caller_address(oracle1.contract_address);
    assert!(consumer.quote('ETH', 2) == 6000, "quote from first oracle wrong");

    let oracle2 = deploy_oracle(stranger());
    start_cheat_caller_address(oracle2.contract_address, stranger());
    oracle2.set_price('ETH', 5000);
    stop_cheat_caller_address(oracle2.contract_address);

    consumer.set_oracle(oracle2.contract_address);
    assert!(consumer.get_oracle() == oracle2.contract_address, "rewire not stored");
    assert!(consumer.quote('ETH', 2) == 10000, "quote should use second oracle");
}
