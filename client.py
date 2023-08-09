import asyncio # for concurrency
import websocket # for connecting to web socket
import json # for json.dumps
import aiohttp # for REST API
import sys # take command line arguments
import time 
from concurrent.futures import ThreadPoolExecutor
from enum import Enum

#* constants
SERVER_IP = sys.argv[1] if len(sys.argv) > 1 else "tenbin-b735da2f640d.herokuapp.com"
SSL = sys.argv[2]=="True" if len(sys.argv) > 2 else True
SERVER_URL = f'http{"s" if SSL else ""}://{SERVER_IP}'
WSS_URL = f'ws{"s" if SSL else ""}://{SERVER_IP}/game'

CLIENT_VERSION = "20230802.dev"

# an event for receiving the success message after submitGuess
guessSuccessEvent = asyncio.Event()

# endTime and a lock for mutex
globalEndTime = 0
# endTimeLock = asyncio.Lock()

globalGuess = None

#* purely functional functions
def now():
    return round(time.time() * 1000)

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

# send a message to the websocket, handling the ID correctly with mutual exclusion
def sendMsg(ws,msg):
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

#* Tasks that happen during round

async def printCountdown():
    global globalEndTime, globalGuess
    while True:
        if now() < globalEndTime: 
            seconds = (globalEndTime-now())//1000
            if seconds < 10 or seconds%5==0:
                print(f'{(globalEndTime-now())//1000}s') 
            if seconds < 10:
                if globalGuess != None:
                    print(f'>>> Your guess is {globalGuess}.')
                else:
                    print("\033[91m>>> You have not submitted your guess.\033[0m")
            await asyncio.sleep(1)

async def submitGuesses(ws,id):
    global globalEndTime, globalGuess
    while True:
        guess = None
        try:
            # Yellow
            guess = int(await ainput())
        except (TypeError, ValueError) as e:
            guess = None
        
        if not (isinstance(guess, int) and guess >= 0 and guess <= 100):
            # Red, invalid guess
            print("\033[91m>>> Guess invalid, please input again. \033[0m")
        elif now() >= globalEndTime:
            # Red, submitted too late
            print("\033[91m>>> Time is up, your guess is invalid. \033[0m")
        else:

            msg = {
                "method": "submitGuess",
                "id": id,
                "guess": guess,
            }
            sendMsg(ws,msg)
            # Receive submitGuess reply - message will be received in main loop instead 
            await guessSuccessEvent.wait()
            # Need to clear it or else it will just pass through
            guessSuccessEvent.clear()

            globalGuess = guess
            # Green
            print(f'\033[32m>>> Guess {guess} registered.\033[0m')

async def main(): 
    global globalEndTime, globalGuess
    # variables
    nickname = ""
    id = ""
    isDead = False
    gameInfo = None

    print("WS server:", WSS_URL)
    print("HTTP server:", SERVER_URL)
    print("Client version:", CLIENT_VERSION)
    print("Establishing connection to the server, please wait...")

    # Do the necessary API calls
    TOKEN = await obtainToken()

    print("Connected to server. Establishing connection to the game, please wait...")
    # establish ws connection
    ws = websocket.create_connection(WSS_URL)

    print("Connected to game")

    # spawns off ping pong task
    asyncio.create_task(pingpong(ws))

    # receive connection reply (get the id)
    result =  await recvMsg(ws)
    print("received: ",result)
    response = json.loads(result)
    id = response["id"]
    assert(response["result"]=="success")


    print(">>> Welcome to the game!")
    print(">>> Difficulty: King of Diamonds - Tenbin (Balance Scale)")
    print(">>> Rules: The player must select a number from 0 to 100. Once all numbers are selected, the average will be calculated, then multiplied by 0.8. The player closest to the number wins the round. The other players each lose a point. All players start with 0 points. If a player reaches -10 points, it is a GAME OVER for that player. A new rule will be introduced for every player eliminated. It is GAME CLEAR for the last remaining player.")
    nickname = await ainput("\033[93m>>> Are you ready? Please input your nickname: \033[0m")
    while nickname == "":
        nickname = await ainput("\033[91m>>> Nickname cannot be blank, please input again: \033[0m")
    # request for join room (values mostly copied from docs)
    # https://docs.openvidu.io/en/stable/developing/rpc/#joinroom
    msg = {
        "method": "joinGame",
        "nickname": nickname,
    }
    sendMsg(ws,msg)

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

    submitGuessesTask = asyncio.create_task(submitGuesses(ws,id))
    printCountdownTask = asyncio.create_task(printCountdown())
    
    while not gameInfo["gameEnded"]:
        if not isDead:
            print(f'\033[93m>>> Round {gameInfo["round"]} - {nickname}, the 3-minute countdown starts now.\033[0m')
            print(f'\033[93m>>> Please input your guess and hit \"enter\" to submit, you can change your guess anytime. \033[0m')
            globalEndTime = gameInfo["roundEndTime"]
            globalGuess = None

            result = await recvMsg(ws)
            print(result)
            response = json.loads(result)

            while "event" not in response or response["event"]!="gameInfo":
                # Receive events from the server, need await as it might take a while
                # Receiving all messages from the server
                # Terminate when it receives gameInfo                
                if "event" in response:
                    if response["event"]=="participantDisconnectedMidgame":
                        # Print person died
                        ps = gameInfo["participants"]
                        p = list(filter(lambda p: p["id"]==response["id"],ps))[0]
                        # Red
                        print(f'\033[91m>>> {p["nickname"]+(" (YOU)" if p["id"]==id else "")} disconnected. GAME OVER.\033[0m')
                        # Display the additional rules
                        # Magenta
                        print("\033[95m>>> Since at least one player died, the following rules are added from now on:")
                        aliveCount = response["aliveCount"]
                        if aliveCount <= 4:
                            print("\033[95m>>> 1. If two or more players choose the same number, the number is invalid and all players who selected the number will lose a point.\033[0m")
                        if aliveCount <= 3:
                            print("\033[95m>>> 2. If a player chooses the exact correct number, they win the round and all other players lose two points.\033[0m")
                        if aliveCount <= 2:
                            print("\033[95m>>> 3. If someone chooses 0, a player who chooses 100 automatically wins the round.\033[0m")
                    elif response["event"]=="shortenCountdown":
                        print(f'\033[93m>>> Every player has submitted their guess, the timer is changed to 15 seconds. \033[0m')
                        # update globalEndTime
                        globalEndTime = response["endTime"]
                    else:
                        raise Exception("Unexpected event received")
                else:
                    assert(response["result"]=="success")
                    guessSuccessEvent.set()
                result = await recvMsg(ws)
                print(result)
                response = json.loads(result)
            
            assert(response["event"]=="gameInfo")
            gameInfo = response

        else:
            print(">>> Waiting for others to submit their numbers.")

            result = await recvMsg(ws)
            print(result)
            response = json.loads(result)
            assert("event" in response)

            while response["event"]!="gameInfo":
                # Receive events from the server, need await as it might take a while
                # Receiving all messages from the server
                # Terminate when it receives gameInfo                

                if response["event"]=="participantDisconnectedMidgame":
                    # Print person died
                    ps = gameInfo["participants"]
                    p = list(filter(lambda p: p["id"]==response["id"],ps))[0]
                    # Red
                    print(f'\033[91m>>> {p["nickname"]+(" (YOU)" if p["id"]==id else "")} disconnected. GAME OVER.\033[0m')
                    # Display the additional rules
                    # Magenta
                    print("\033[95m>>> Since at least one player died, the following rules are added from now on:")
                    aliveCount = response["aliveCount"]
                    if aliveCount <= 4:
                        print("\033[95m>>> 1. If two or more players choose the same number, the number is invalid and all players who selected the number will lose a point.\033[0m")
                    if aliveCount <= 3:
                        print("\033[95m>>> 2. If a player chooses the exact correct number, they win the round and all other players lose two points.\033[0m")
                    if aliveCount <= 2:
                        print("\033[95m>>> 3. If someone chooses 0, a player who chooses 100 automatically wins the round.\033[0m")
                else:
                    raise Exception("Unexpected event received")
                
                result = await recvMsg(ws)
                print(result)
                response = json.loads(result)
                assert("event" in response)
            
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
            ps = gameInfo["participants"]
            p = list(filter(lambda p: p["id"]==d["id"],ps))[0]
            if d["reason"]=="deadLimit":
                # Red
                print(f'\033[91m>>> {p["nickname"]+(" (YOU)" if p["id"]==id else "")} reached {p["score"]} score. GAME OVER.\033[0m')
            elif d["reason"]=="disconnected":
                # Red
                print(f'\033[91m>>> {p["nickname"]+(" (YOU)" if p["id"]==id else "")} disconnected. GAME OVER.\033[0m')
        # Display the additional rules if someone died because of disconnected or deadLimit
        if len(list(filter(lambda dp : dp["reason"]!="disconnectedMidgame",gameInfo["justDiedParticipants"]))) > 0:
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
