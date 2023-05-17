import asyncio
import uuid
import capnp

import game_capture_capnp

async def myreader(client, reader: asyncio.StreamReader):
    while True:
        data = await reader.read(4096)
        client.write(data)


async def mywriter(client, writer: asyncio.StreamWriter):
    while True:
        data = await client.read(4096)
        writer.write(data.tobytes())
        await writer.drain()

async def send_data():
    # Open connection to server
    reader, writer = await asyncio.open_connection('localhost', 9189)

    # Start TwoPartyClient using TwoWayPipe (takes no arguments in this mode)
    client = capnp.TwoPartyClient()

    # Assemble reader and writer tasks, run in the background
    coroutines = [myreader(client, reader), mywriter(client, writer)]
    asyncio.gather(*coroutines, return_exceptions=True)

    # Bootstrap the Calculator interface
    match_server = client.bootstrap().cast_as(game_capture_capnp.MatchServer)

    print("Testing pulse()")
    mac_addr = uuid.getnode()
    response_promise = match_server.pulse(macAddr=mac_addr)
    response = await response_promise.a_wait()
    print(f"Received match_id = {response.matchId}")

    print("Testing sendMove()")
    request = match_server.sendMove_request()
    request.from_dict(
        {
            'matchId': 'testId',
            'move': {'tiles': [
                {
                    'value': ord('A'),
                    'pos': {'row': 4, 'col': 9}
                },
                {
                    'value': ord('?'),
                    'pos': {'row': 4, 'col': 10}
                }
            ]}
        }
    )
    request.matchId = "testId"
    request.move.init('tiles', 1) 
    request.move.tiles[0].from_dict({'value': ord('A'), 'pos': {'row': 4, 'col': 9}})
    response_promise = request.send()
    response = await response_promise.a_wait()
    print(f"Received sucess = {response.success}")

    print("Testing sendRack()")
    request = match_server.sendRack_request()
    request.from_dict(
        {'matchId': 'testId', 
         'rack': {
            'player': 'player1',
            'tiles': '?FCDAEK'
        }}
    )
    response_promise = request.send()
    response = await response_promise.a_wait()
    print(f"Received success = {response.success}")



asyncio.run(send_data())
