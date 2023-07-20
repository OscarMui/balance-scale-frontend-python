import asyncio # for concurrency
import websocket # for connecting to web socket
import json # for json.dumps
import aiohttp # for REST API
import sys # take command line arguments

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
    print("SEND",msg)
    ws.send(json.dumps(msg))

# responsible for sending pings
async def pingpong(ws):
    while True:
        ws.ping()
        await asyncio.sleep(5)

async def main(): 
    # TOKEN = await obtainToken()

    # establish ws connection
    ws = websocket.create_connection(
        WSS_URL,
        # sslopt={"cert_reqs":ssl.CERT_NONE} # bypass SSL check
    )
    print("WSS connection established ", WSS_URL)

    # spawns off ping pong task
    asyncio.create_task(pingpong(ws))
    
    # request for join room (values mostly copied from docs)
    # https://docs.openvidu.io/en/stable/developing/rpc/#joinroom
    msg = {
        "method": "joinGame"
    }
    await sendMsg(ws,msg)

    result =  ws.recv()
    print("received: ",result)

    # Receive all kinds of messages including the pongs, join/leave events, and actual messages
    while True:
        # await asyncio.sleep(100)
        resp = await asyncio.get_event_loop().run_in_executor(None, ws.recv)
        print("received: ",resp)

        # # convert from a json string to a python dictionary
        # response = json.loads(resp)

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

asyncio.run(main())
