import asyncio # for concurrency
import websocket # for connecting to web socket
import json # for json.dumps
import aiohttp # for REST API
import sys # take command line arguments
from concurrent.futures import ThreadPoolExecutor
from enum import Enum

# constants
SERVER_IP = sys.argv[1] if len(sys.argv) > 1 else "localhost:8999"
SERVER_URL = "http://"+SERVER_IP
WSS_URL = "ws://"+SERVER_IP+"/game"

CLIENT_VERSION = "20230801.0"
DEAD_LIMIT = -10

async def obtainToken():
    async with aiohttp.ClientSession() as session:
        headers = {
            "Content-Type": "application/json"
        } 
        
        async with session.get(
            SERVER_URL + "/api/version"
        ) as resp:
            response = await resp.json()
            assert(response["result"]=="success")
            acceptedClientVersions = response["acceptedClientVersions"]
            if CLIENT_VERSION not in acceptedClientVersions:
                raise Exception("VERSION ERROR: Incompatible version with server. Please obtain the latest code.")
    
        # async with session.post(
        #     SERVER_URL + "???", 
        #     verify_ssl=False, 
        #     headers=headers
        # ) as resp:
        #     # print(f'resp:{resp}') # print out the response header
        #     # response = await resp.text() # use for testing in case the response is not as expected
        #     response = await resp.json() # get the actual response
        #     # print(f'response:{response}')
        #     token = response['token']
        #     print(f'token: {token}')
        #     return token

# class Special(Enum):
#     PLAYER_DEAD = 0
#     PLAYER_DISCONNECTED = 1
#     ADDITIONAL_RULE_APPLIED = 2

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
    gameInfo = None

    TOKEN = await obtainToken()

    # establish ws connection
    ws = websocket.create_connection(
        WSS_URL,
        # sslopt={"cert_reqs":ssl.CERT_NONE} # bypass SSL check
    )
    print("WSS connection established ", WSS_URL)

    # spawns off ping pong task
    asyncio.create_task(pingpong(ws))

    # receive connection reply (get the id)
    result =  ws.recv()
    print("received: ",result)
    response = json.loads(result)
    id = response["id"]
    assert(response["result"]=="success")


    print(">>> Welcome to the game!")
    print(">>> Difficulty: King of Diamonds - Tenbin (Balance Scale)")
    print(">>> Rules: The player must select a number from 0 to 100. Once all numbers are selected, the average will be calculated, then multiplied by 0.8. The player closest to the number wins the round. The other players each lose a point. All players start with 0 points. If a player reaches -10 points, it is a GAME OVER for that player. A new rule will be introduced for every player eliminated. It is GAME CLEAR for the last remaining player.")
    nickname = await ainput("\033[93m>>> Are you ready? Please input your nickname: \033[0m")
    
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
    assert(response["result"]=="success")

    # Receive gameStart event
    result = await recvMsg(ws)
    response = json.loads(result)
    assert(response["event"]=="gameStart")
    gameInfo = response

    #cyan
    print("\033[96m>>> We got enough players, the game starts now.\033[0m")
    print(">>> The players are: ")
    for p in gameInfo["participants"]:
        print(">>> ", p["nickname"])

    # Round main loop 
    while not gameInfo["gameEnded"]:
        if not isDead:
            guess = None
            try:
                # Yellow
                guess = int(await ainput(f'\033[93m>>> Round {gameInfo["round"]}: {nickname} please input your guess: \033[0m'))
            except (TypeError, ValueError) as e:
                guess = None
            
            while not (isinstance(guess, int) and guess >= 0 and guess <= 100):
                try:
                    # Red
                    guess = int(await ainput("\033[91mGuess invalid, please input again: \033[0m"))
                except (TypeError, ValueError) as e:
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

            # Green
            print("\033[32m>>> Guess registered.\033[0m")
        print(">>> Waiting for others to submit their numbers.")
        # Receive round result from the server, need await as it might take a while
        result = await recvMsg(ws)
        print(result)

        # convert from a json string to a python dictionary
        response = json.loads(result)
        assert(response["event"]=="gameInfo")
        gameInfo = response
        
        if response["event"]=="gameInfo":
            # check if ourselves isDead
            ps = response["participants"]
            p = list(filter(lambda p: p["id"]==id,ps))[0]
            # if isDead != p["isDead"]:
            #     # red
            #     print(f'\033[91m>>> You reached {p["score"]} score, GAME OVER.\033[0m')
            isDead = p["isDead"] 

        print(f'>>> Round {gameInfo["round"]-1} is over, these are the guesses players submitted:')
        print(">>> Nickname | Guess | Score")
        for p in gameInfo["participants"]:
            print(f'>>> {p["nickname"]+(" (YOU)" if p["id"]==id else "")} | {p["guess"] if p["guess"]!=None else "N/A"} | {p["score"]}',end="")
            if p["id"] in gameInfo["winners"]:
                # Green
                print("\033[32m <-- Round winner\033[0m")
            elif p["isDead"]:
                # Red
                print("\033[91m <-- GAME OVER\033[0m")
            else:
                print("") # to go to next line
        print(f'>>> The target was {round(gameInfo["target"],2)}.')

        # Remind people which rules are applied
        for r in gameInfo["justAppliedRules"]:
            # Magenta
            if r == 2:
                print("\033[95m>>> Rule applied: If someone chooses 0, a player who chooses 100 automatically wins the round.\033[0m")
            elif r == 3:
                print("\033[95m>>> Rule applied: If a player chooses the exact correct number, they win the round and all other players lose two points.\033[0m")
            elif r == 4:
                print("\033[95m>>> Rule applied: If two or more players choose the same number, the number is invalid and all players who selected the number will lose a point.\033[0m")
        # Print people died
        for d in gameInfo["justDiedParticipants"]:
            ps = response["participants"]
            p = list(filter(lambda p: p["id"]==d,ps))[0]
            if p["score"]==DEAD_LIMIT:
                # Red
                print(f'\033[91m>>> {p["nickname"]+(" (YOU)" if p["id"]==id else "")} reached {DEAD_LIMIT} score. GAME OVER.\033[0m')
            else:
                # Red
                print(f'\033[91m>>> {p["nickname"]+(" (YOU)" if p["id"]==id else "")} disconnected. GAME OVER.\033[0m')
        # Display the additional rules if someone died
        if len(gameInfo["justDiedParticipants"]) > 0:
            # Magenta
            print("\033[95m>>> Since at least one player died, the following rules are added from now on:")
            aliveCount = gameInfo["aliveCount"]
            if aliveCount <= 4:
                print("\033[95m>>> 1. If two or more players choose the same number, the number is invalid and all players who selected the number will lose a point.\033[0m")
            if aliveCount <= 3:
                print("\033[95m>>> 2. If a player chooses the exact correct number, they win the round and all other players lose two points.\033[0m")
            if aliveCount <= 2:
                print("\033[95m>>> 3. If someone chooses 0, a player who chooses 100 automatically wins the round.\033[0m")
    ps = response["participants"]
    filteredP = list(filter(lambda p: not p["isDead"],ps))
    #cyan
    if(len(filteredP)>0):
        p = filteredP[0]
        print(f'\033[96m>>> Game ended, the winner is {p["nickname"]+(" (YOU)" if p["id"]==id else "")}\033[0m')
    ws.close()
asyncio.run(main())
