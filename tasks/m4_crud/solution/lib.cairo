use starknet::ContractAddress;

#[derive(Drop, Copy, Serde, starknet::Store, PartialEq)]
pub struct Item {
    pub id: u64,
    pub owner: ContractAddress,
    pub price: u128,
    pub active: bool,
}

#[starknet::interface]
pub trait IItemStore<TContractState> {
    fn create_item(ref self: TContractState, price: u128) -> u64;
    fn get_item(self: @TContractState, id: u64) -> Item;
    fn update_price(ref self: TContractState, id: u64, new_price: u128);
    fn deactivate(ref self: TContractState, id: u64);
    fn item_count(self: @TContractState) -> u64;
}

#[starknet::contract]
pub mod ItemStoreContract {
    use starknet::storage::{
        Map, StoragePathEntry, StoragePointerReadAccess, StoragePointerWriteAccess,
    };
    use starknet::{ContractAddress, get_caller_address};
    use super::Item;

    #[storage]
    struct Storage {
        items: Map<u64, Item>,
        count: u64,
    }

    #[event]
    #[derive(Drop, starknet::Event)]
    pub enum Event {
        ItemCreated: ItemCreated,
    }

    #[derive(Drop, starknet::Event)]
    pub struct ItemCreated {
        pub id: u64,
        pub owner: ContractAddress,
        pub price: u128,
    }

    #[abi(embed_v0)]
    impl ItemStoreImpl of super::IItemStore<ContractState> {
        fn create_item(ref self: ContractState, price: u128) -> u64 {
            assert(price != 0, 'Item: zero price');
            let id = self.count.read() + 1;
            let owner = get_caller_address();
            self.items.entry(id).write(Item { id, owner, price, active: true });
            self.count.write(id);
            self.emit(ItemCreated { id, owner, price });
            id
        }

        fn get_item(self: @ContractState, id: u64) -> Item {
            assert(id != 0 && id <= self.count.read(), 'Item: not found');
            self.items.entry(id).read()
        }

        fn update_price(ref self: ContractState, id: u64, new_price: u128) {
            let mut item = self.items.entry(id).read();
            assert(item.owner == get_caller_address(), 'Item: not owner');
            assert(new_price != 0, 'Item: zero price');
            assert(item.active, 'Item: inactive');
            item.price = new_price;
            self.items.entry(id).write(item);
        }

        fn deactivate(ref self: ContractState, id: u64) {
            let mut item = self.items.entry(id).read();
            assert(item.owner == get_caller_address(), 'Item: not owner');
            assert(item.active, 'Item: inactive');
            item.active = false;
            self.items.entry(id).write(item);
        }

        fn item_count(self: @ContractState) -> u64 {
            self.count.read()
        }
    }
}
