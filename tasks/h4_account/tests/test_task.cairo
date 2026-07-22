use account::{
    IAccountMetaDispatcher, IAccountMetaDispatcherTrait, ISRC6Dispatcher, ISRC6DispatcherTrait,
    ITargetDispatcher, ITargetDispatcherTrait,
};
use snforge_std::signature::KeyPairTrait;
use snforge_std::signature::stark_curve::{
    StarkCurveKeyPairImpl, StarkCurveSignerImpl, StarkCurveVerifierImpl,
};
use snforge_std::{
    ContractClassTrait, DeclareResultTrait, declare, start_cheat_caller_address,
    start_cheat_signature, start_cheat_transaction_hash, stop_cheat_caller_address,
    stop_cheat_signature, stop_cheat_transaction_hash,
};
use starknet::ContractAddress;
use starknet::account::Call;

fn deploy_account(public_key: felt252) -> ISRC6Dispatcher {
    let contract = declare("SimpleAccount").unwrap().contract_class();
    let (address, _) = contract.deploy(@array![public_key]).unwrap();
    ISRC6Dispatcher { contract_address: address }
}

fn deploy_target() -> ITargetDispatcher {
    let contract = declare("Target").unwrap().contract_class();
    let (address, _) = contract.deploy(@array![]).unwrap();
    ITargetDispatcher { contract_address: address }
}

#[test]
fn test_get_public_key() {
    let kp = KeyPairTrait::<felt252, felt252>::generate();
    let account = deploy_account(kp.public_key);
    let meta = IAccountMetaDispatcher { contract_address: account.contract_address };
    assert!(meta.get_public_key() == kp.public_key, "public key not stored");
}

#[test]
fn test_is_valid_signature_accepts_valid() {
    let kp = KeyPairTrait::<felt252, felt252>::generate();
    let account = deploy_account(kp.public_key);
    let hash = 0x1234567;
    let (r, s): (felt252, felt252) = kp.sign(hash).unwrap();
    assert!(account.is_valid_signature(hash, array![r, s]) == 'VALID', "valid sig rejected");
}

#[test]
fn test_is_valid_signature_rejects_invalid() {
    let kp = KeyPairTrait::<felt252, felt252>::generate();
    let account = deploy_account(kp.public_key);
    let hash = 0x1234567;
    let (r, s): (felt252, felt252) = kp.sign(hash).unwrap();
    // signature over a different hash
    assert!(account.is_valid_signature(0x7654321, array![r, s]) == 0, "wrong hash accepted");
    // tampered signature
    assert!(account.is_valid_signature(hash, array![r, s + 1]) == 0, "tampered sig accepted");
    // malformed signature (wrong length) must return 0, not panic
    assert!(account.is_valid_signature(hash, array![r]) == 0, "short sig accepted");
}

#[test]
fn test_validate_accepts_valid_tx_signature() {
    let kp = KeyPairTrait::<felt252, felt252>::generate();
    let account = deploy_account(kp.public_key);
    let tx_hash = 0xdeadbeef;
    let (r, s): (felt252, felt252) = kp.sign(tx_hash).unwrap();

    start_cheat_transaction_hash(account.contract_address, tx_hash);
    start_cheat_signature(account.contract_address, array![r, s].span());
    let result = account.__validate__(array![]);
    stop_cheat_transaction_hash(account.contract_address);
    stop_cheat_signature(account.contract_address);

    assert!(result == 'VALID', "valid tx signature rejected");
}

#[test]
#[should_panic(expected: 'Account: invalid sig')]
fn test_validate_rejects_invalid_tx_signature() {
    let kp = KeyPairTrait::<felt252, felt252>::generate();
    let account = deploy_account(kp.public_key);
    let tx_hash = 0xdeadbeef;
    // signature over a DIFFERENT hash than the transaction hash
    let (r, s): (felt252, felt252) = kp.sign(0xbadc0de).unwrap();

    start_cheat_transaction_hash(account.contract_address, tx_hash);
    start_cheat_signature(account.contract_address, array![r, s].span());
    account.__validate__(array![]);
}

#[test]
fn test_execute_dispatches_call_to_target() {
    let kp = KeyPairTrait::<felt252, felt252>::generate();
    let account = deploy_account(kp.public_key);
    let target = deploy_target();
    assert!(target.get_value() == 0, "target must start at 0");

    let call = Call {
        to: target.contract_address, selector: selector!("set_value"), calldata: array![42].span(),
    };
    let zero: ContractAddress = 0.try_into().unwrap();
    start_cheat_caller_address(account.contract_address, zero);
    let results = account.__execute__(array![call]);
    stop_cheat_caller_address(account.contract_address);

    assert!(results.len() == 1, "expected one result per call");
    assert!(target.get_value() == 42, "target value not updated");
}

#[test]
fn test_execute_collects_return_data_in_order() {
    let kp = KeyPairTrait::<felt252, felt252>::generate();
    let account = deploy_account(kp.public_key);
    let target = deploy_target();

    let set_call = Call {
        to: target.contract_address, selector: selector!("set_value"), calldata: array![7].span(),
    };
    let get_call = Call {
        to: target.contract_address, selector: selector!("get_value"), calldata: array![].span(),
    };
    let zero: ContractAddress = 0.try_into().unwrap();
    start_cheat_caller_address(account.contract_address, zero);
    let results = account.__execute__(array![set_call, get_call]);
    stop_cheat_caller_address(account.contract_address);

    assert!(results.len() == 2, "expected two results");
    let results = results.span();
    assert!((*results.at(0)).len() == 0, "set_value should return no data");
    assert!(*results.at(1) == array![7].span(), "get_value return data wrong");
}

#[test]
#[should_panic(expected: 'Account: invalid caller')]
fn test_execute_nonzero_caller_panics() {
    let kp = KeyPairTrait::<felt252, felt252>::generate();
    let account = deploy_account(kp.public_key);
    let target = deploy_target();

    let call = Call {
        to: target.contract_address, selector: selector!("set_value"), calldata: array![1].span(),
    };
    let caller: ContractAddress = 123.try_into().unwrap();
    start_cheat_caller_address(account.contract_address, caller);
    account.__execute__(array![call]);
}
