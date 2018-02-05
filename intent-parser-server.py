#!/usr/bin/env python3

import socket
import json
from adapt.intent import IntentBuilder
from adapt.engine import IntentDeterminationEngine


def train(keyword, types, locations):
    global engine
    engine = IntentDeterminationEngine()
    for kw in keyword:
        engine.register_entity(kw, "Keyword")

    for t in types:
        engine.register_entity(t, "Type")

    for loc in locations:
        engine.register_entity(loc, "Location")

    intent = IntentBuilder("Intent")\
        .require("Keyword")\
        .optionally("Type")\
        .require("Location")\
        .build()

    engine.register_intent_parser(intent)


def print_intent(command):
    global engine
    result = ""
    for intent in engine.determine_intent(command):
        if intent.get('confidence') > 0:
            result += json.dumps(intent, indent=4)
    if result == '':
        return "-1"
    else:
        return result


# next create a socket object
s = socket.socket()
port = 5555
# Next bind to the port
s.bind(('127.0.0.1', port))
print("socket binded to %s" %(port))
# put the socket into listening mode
s.listen(5)
print("socket is listening")

# a forever loop until we interrupt it or
# an error occurs
while True:
    try:
        # Establish connection with client.
        c, addr = s.accept()
        print('Got connection from', addr)
        # c.settimeout(5.0)
        data = c.recv(4096)
        # c.settimeout(None)
        cmd = data.decode("utf-8").strip()
        if cmd[0] == 't':
            # received command to train
            print('train', cmd[2:].split('|'))
            cmd_list = cmd[2:].split('|')
            keyword_array = []
            for item in cmd_list[0].split(','):
                keyword_array.append(item)
            types_array = []
            for item in cmd_list[1].split(','):
                types_array.append(item)
            locations_array = []
            for item in cmd_list[2].split(','):
                locations_array.append(item)
            train(keyword_array, types_array, locations_array)
            c.send('1'.encode())
        elif cmd[0] == 'q':
            # received a query
            print('query', cmd[2:])
            result = print_intent(cmd[2:])
            c.send(result.encode())
        c.close()
    except Exception:
        print("General error")
        c.close()
