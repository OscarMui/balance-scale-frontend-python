import asyncio # for concurrency
import websocket # for connecting to web socket
import json # for json.dumps
import aiohttp # for REST API
import sys # take command line arguments
from concurrent.futures import ThreadPoolExecutor

# constants
SERVER_IP = sys.argv[1] if len(sys.argv) > 1 else "localhost:8999"
SERVER_URL = "http://"+SERVER_IP+"/"
WSS_URL = "ws://"+SERVER_IP+"/game"

# async def obtainToken():
#     async with aiohttp.ClientSession() as session:
#         headers = {
#             "Content-Type": "application/json"
#         } 
        
#         async with session.post(
#             SERVER_URL + "???", 
#             verify_ssl=False, 
#             headers=headers
#         ) as resp:
#             # print(f'resp:{resp}') # print out the response header
#             # response = await resp.text() # use for testing in case the response is not as expected
#             response = await resp.json() # get the actual response
#             # print(f'response:{response}')
#             token = response['token']
#             print(f'token: {token}')
#             return token

# send a message to the websocket, handling the ID correctly with mutual exclusion
async def sendMsg(ws,msg):
    print("SEND: ",msg)
    ws.send(json.dumps(msg))

# ws.recv() will stop the ping pongs
# receive a message, only use this when you know the message will not come soon
async def recvMsg(ws):
    return await asyncio.get_event_loop().run_in_executor(None, ws.recv)

# asynchronus input copied from web
async def ainput(prompt: str = ''):
    with ThreadPoolExecutor(1, 'ainput') as executor:
        return (await asyncio.get_event_loop().run_in_executor(executor, input, prompt)).rstrip()

# responsible for sending pings
async def pingpong(ws):
    while True:
        # print("ping")
        ws.ping()
        await asyncio.sleep(5)

async def main(): 
    # variables
    nickname = ""
    id = ""
    isDead = False
    gameEnded = False

    # TOKEN = await obtainToken()

    # establish ws connection
    ws = websocket.create_connection(
        WSS_URL,
        # sslopt={"cert_reqs":ssl.CERT_NONE} # bypass SSL check
    )
    print("WSS connection established ", WSS_URL)

    # spawns off ping pong task
    asyncio.create_task(pingpong(ws))

    nickname = await ainput("Please input your nickname: ")
    
    # request for join room (values mostly copied from docs)
    # https://docs.openvidu.io/en/stable/developing/rpc/#joinroom
    msg = {
        "method": "joinGame",
        "nickname": nickname,
    }
    await sendMsg(ws,msg)

    # Receive joinGame reply (ignore)
    result =  ws.recv()
    print("received: ",result)
    response = json.loads(result)
    id = response["id"]
    assert(response["result"]=="success")

    # Receive start game event
    result = await recvMsg(ws)
    response = json.loads(result)
    assert(response["event"]=="gameInfo")

    # Receive all kinds of messages until game ends
    while not gameEnded:
        if not isDead:
            guess = await ainput("Please input your guess: ")
            msg = {
                "method": "submitGuess",
                "id": id,
                "guess": guess,
            }
            await sendMsg(ws,msg)

            # Receive submitGuess reply (ignore)
            result =  ws.recv()
            print("received: ",result)
            response = json.loads(result)
            assert(response["result"]=="success")

        # Receive round result from the server, need await as it might take a while
        result = await recvMsg(ws)
        print(result)

        # convert from a json string to a python dictionary
        response = json.loads(result)
        assert(response["event"]=="gameInfo")

        if response["event"]=="gameInfo":
            # check if gameEnded
            gameEnded = response["gameEnded"]

            # check if isDead
            ps = response["participants"]
            p = list(filter(lambda p: p["id"]==id,ps))[0]
            isDead = p["isDead"] 

        # # check if it is an actual message
        # if response.get("method",False) == "sendMessage":
        #     print("detected message, now decoding")
        #     try:
        #         # retrieving the message from the recived message string
        #         params = response["params"]
        #         # print("PARAMS: ",params)
        #         data = json.loads(params["data"])
        #         # print("DATA: ",data)
        #         message = data["message"]
        #         print("MESSAGE: ",message)
        #     except:
        #         print("Error decoding message, message ignored")

    print("Game ended")
    ws.close()
asyncio.run(main())
