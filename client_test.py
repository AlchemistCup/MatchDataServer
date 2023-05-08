import asyncio

async def send_data():
    # Open connection to server
    reader, writer = await asyncio.open_connection('localhost', 9189)

    # Send data
    message = "Hello world"
    writer.write(message.encode())
    await writer.drain()
    print(f"Sent {message!r}")

    # Close the connection
    writer.close()
    await writer.wait_closed()

asyncio.run(send_data())
