import asyncio

async def main():
    # Create the server
    server = await asyncio.start_server(handle_client, host=None, port=9189)

    # Serve the clients
    async with server:
        await server.serve_forever()

async def handle_client(reader, writer):
    # Log connection
    print(f"New connection from {writer.get_extra_info('peername')}")

    while True:
        data = await reader.read(1024)
        if not data:
            break
        # Log data and connection it came from
        print(f"Received {data!r} from {writer.get_extra_info('peername')}")
        
    # Close the connection
    print(f"Closing connection with {writer.get_extra_info('peername')}")
    writer.close()
    await writer.wait_closed()

if __name__ == "__main__":
    asyncio.run(main())