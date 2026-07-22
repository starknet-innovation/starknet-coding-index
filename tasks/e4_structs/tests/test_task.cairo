use config_store::{Config, IConfigStoreDispatcher, IConfigStoreDispatcherTrait};
use snforge_std::{
    ContractClassTrait, DeclareResultTrait, declare, start_cheat_caller_address,
    stop_cheat_caller_address,
};
use starknet::ContractAddress;

fn admin() -> ContractAddress {
    111.try_into().unwrap()
}

fn other() -> ContractAddress {
    222.try_into().unwrap()
}

fn deploy(threshold: u64, fee_bps: u16, admin_addr: ContractAddress) -> IConfigStoreDispatcher {
    let contract = declare("ConfigManager").unwrap().contract_class();
    let calldata: Array<felt252> = array![threshold.into(), fee_bps.into(), admin_addr.into()];
    let (address, _) = contract.deploy(@calldata).unwrap();
    IConfigStoreDispatcher { contract_address: address }
}

#[test]
fn test_constructor_get_config_roundtrip() {
    let store = deploy(100, 250, admin());
    let config = store.get_config();
    assert!(config == Config { threshold: 100, fee_bps: 250, admin: admin() }, "config mismatch");
}

#[test]
fn test_set_config_by_admin() {
    let store = deploy(100, 250, admin());
    let new_config = Config { threshold: 500, fee_bps: 1000, admin: other() };
    start_cheat_caller_address(store.contract_address, admin());
    store.set_config(new_config);
    stop_cheat_caller_address(store.contract_address);
    let got = store.get_config();
    assert!(got == Config { threshold: 500, fee_bps: 1000, admin: other() }, "config not updated");
}

#[test]
#[should_panic(expected: 'Config: not admin')]
fn test_non_admin_set_config_panics() {
    let store = deploy(100, 250, admin());
    let new_config = Config { threshold: 1, fee_bps: 1, admin: other() };
    start_cheat_caller_address(store.contract_address, other());
    store.set_config(new_config);
}

#[test]
#[should_panic(expected: 'Config: bad fee')]
fn test_set_config_bad_fee_panics() {
    let store = deploy(100, 250, admin());
    let new_config = Config { threshold: 1, fee_bps: 10001, admin: admin() };
    start_cheat_caller_address(store.contract_address, admin());
    store.set_config(new_config);
}

#[test]
fn test_constructor_bad_fee_deploy_fails() {
    let contract = declare("ConfigManager").unwrap().contract_class();
    let calldata: Array<felt252> = array![100, 10001, admin().into()];
    let result = contract.deploy(@calldata);
    assert!(result.is_err(), "deploy with fee_bps > 10000 must fail");
}

#[test]
fn test_compute_fee_math() {
    let store = deploy(100, 250, admin());
    // 10000 * 250 / 10000 = 250
    assert!(store.compute_fee(10000) == 250, "fee on 10000 wrong");
    // 39 * 250 / 10000 = 9750 / 10000 -> rounds down to 0
    assert!(store.compute_fee(39) == 0, "fee on 39 should round down to 0");
    // 41 * 250 / 10000 = 10250 / 10000 -> rounds down to 1
    assert!(store.compute_fee(41) == 1, "fee on 41 should round down to 1");
    // zero amount
    assert!(store.compute_fee(0) == 0, "fee on 0 wrong");
}

#[test]
fn test_compute_fee_uses_updated_config() {
    let store = deploy(100, 250, admin());
    start_cheat_caller_address(store.contract_address, admin());
    store.set_config(Config { threshold: 100, fee_bps: 10000, admin: admin() });
    stop_cheat_caller_address(store.contract_address);
    // fee_bps = 10000 -> fee equals amount
    assert!(store.compute_fee(1234) == 1234, "fee at 10000 bps should equal amount");
}
