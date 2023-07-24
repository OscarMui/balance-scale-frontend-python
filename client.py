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
    print("sent: ", msg)
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
    gameInfo = None

    # TOKEN = await obtainToken()

    # establish ws connection
    ws = websocket.create_connection(
        WSS_URL,
        # sslopt={"cert_reqs":ssl.CERT_NONE} # bypass SSL check
    )
    print("WSS connection established ", WSS_URL)

    # spawns off ping pong task
    asyncio.create_task(pingpong(ws))

    nickname = await ainput(">>> Please input your nickname: ")
    
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
    gameInfo = response

    print(">>> We got enough players, the game starts now.")
    print("The players are: ")
    for p in gameInfo["participants"]:
        print(">>>", p["nickname"])

    # Round main loop 
    while not gameEnded:
        if not isDead:
            guess = None
            try:
                guess = int(await ainput(f'>>> Round {gameInfo["round"]}: Please input your guess: '))
            except TypeError:
                guess = None
            
            while not (isinstance(guess, int) and guess >= 0 and guess <= 100):
                try:
                    guess = await ainput("Guess invalid, please input again: ")
                except ValueError:
                    guess = None
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

            print(">>> Guess registered.")
        print(">>> Waiting for others to submit their numbers.")
        # Receive round result from the server, need await as it might take a while
        result = await recvMsg(ws)
        print(result)

        # convert from a json string to a python dictionary
        response = json.loads(result)
        assert(response["event"]=="gameInfo")
        gameInfo = response
        
        if response["event"]=="gameInfo":
            # check if gameEnded
            gameEnded = response["gameEnded"]

            # check if isDead
            ps = response["participants"]
            p = list(filter(lambda p: p["id"]==id,ps))[0]
            if isDead != p["isDead"]:
                print(f'>>> You reached {p["score"]}, GAME OVER.')
            isDead = p["isDead"] 

        print(f'>>> Round {gameInfo["round"]} is over, these are the guesses players submitted:')
        print(">>> Nickname | Guess | Score")
        for p in gameInfo["participants"]:
            print(f'>>> {p["nickname"]} | {p["guesses"][gameInfo["round"]]} | {p["score"]}',end="")
            if p["isDead"]:
                print("<-- GAME OVER")
            else:
                print("") # to go to next line
        # print("The winner(s) is/are: ")

    print("Game ended")
    ws.close()
asyncio.run(main())
