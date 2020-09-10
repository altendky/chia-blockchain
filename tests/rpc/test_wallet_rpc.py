import asyncio
from secrets import token_bytes

import pytest

from src.protocols import full_node_protocol
from src.simulator.simulator_protocol import FarmNewBlockProtocol, ReorgProtocol
from src.types.peer_info import PeerInfo
from src.util.ints import uint16, uint32, uint64
from tests.setup_nodes import setup_simulators_and_wallets, bt
from src.consensus.block_rewards import calculate_base_fee, calculate_block_reward
from tests.time_out_assert import time_out_assert, time_out_assert_not_None
from src.util.chech32 import encode_puzzle_hash
from src.rpc.wallet_rpc_client import WalletRpcClient
from src.rpc.wallet_rpc_api import WalletRpcApi
from src.util.config import load_config
from src.rpc.rpc_server import start_rpc_server


@pytest.fixture(scope="module")
def event_loop():
    loop = asyncio.get_event_loop()
    yield loop


class TestWalletRpc:
    @pytest.fixture(scope="function")
    async def two_wallet_nodes(self):
        async for _ in setup_simulators_and_wallets(
            1, 2, {"COINBASE_FREEZE_PERIOD": 0}
        ):
            yield _

    @pytest.mark.asyncio
    async def test_wallet_make_transaction(self, two_wallet_nodes):
        test_rpc_port = uint16(21529)
        num_blocks = 5
        full_nodes, wallets = two_wallet_nodes
        full_node_1, server_1 = full_nodes[0]
        wallet_node, server_2 = wallets[0]
        wallet_node_2, server_3 = wallets[1]
        wallet = wallet_node.wallet_state_manager.main_wallet
        ph = await wallet.get_new_puzzlehash()

        await server_2.start_client(PeerInfo("localhost", uint16(server_1._port)), None)

        for i in range(0, num_blocks):
            await full_node_1.farm_new_block(FarmNewBlockProtocol(ph))

        funds = sum(
            [
                calculate_base_fee(uint32(i)) + calculate_block_reward(uint32(i))
                for i in range(1, num_blocks - 1)
            ]
        )

        wallet_rpc_api = WalletRpcApi(wallet_node)

        config = load_config(bt.root_path, "config.yaml")
        hostname = config["self_hostname"]
        daemon_port = config["daemon_port"]

        def stop_node_cb():
            pass

        rpc_cleanup = await start_rpc_server(
            wallet_rpc_api,
            hostname,
            daemon_port,
            test_rpc_port,
            stop_node_cb,
            connect_to_daemon=False,
        )

        await time_out_assert(5, wallet.get_confirmed_balance, funds)
        await time_out_assert(5, wallet.get_unconfirmed_balance, funds)

        client = await WalletRpcClient.create("localhost", test_rpc_port)
        try:
            addr = encode_puzzle_hash(
                await wallet_node_2.wallet_state_manager.main_wallet.get_new_puzzlehash()
            )
            print(await client.get_wallet_summaries())
            tx = await client.send_transaction("1", 10, addr)
            print(tx)
            assert tx is not None

            while True:
                tx = await client.get_transaction("1", tx.name())
                print("Tx", tx)
                await asyncio.sleep(1)
        except Exception:
            # Checks that the RPC manages to stop the node
            client.close()
            await client.await_closed()
            await rpc_cleanup()
            raise

        client.close()
        await client.await_closed()
        await rpc_cleanup()

        # tx = await wallet.generate_signed_transaction(
        #     10,
        #     await wallet_node_2.wallet_state_manager.main_wallet.get_new_puzzlehash(),
        #     0,
        # )
        # await wallet.push_transaction(tx)

        # await time_out_assert(5, wallet.get_confirmed_balance, funds)
        # await time_out_assert(5, wallet.get_unconfirmed_balance, funds - 10)

        # for i in range(0, num_blocks):
        #     await full_node_1.farm_new_block(FarmNewBlockProtocol(ph))

        # new_funds = sum(
        #     [
        #         calculate_base_fee(uint32(i)) + calculate_block_reward(uint32(i))
        #         for i in range(1, (2 * num_blocks) - 1)
        #     ]
        # )
        # await time_out_assert(5, wallet.get_confirmed_balance, new_funds - 10)
        # await time_out_assert(5, wallet.get_unconfirmed_balance, new_funds - 10)
