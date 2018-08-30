#!/usr/bin/env python3

"""
Intent parser server.

Commands are sent over TCP as follows:

|-------|----------------------------|
| Bytes | Content                    |
|-------|----------------------------|
| 0 - 3 | Length of data, big endian |
| 4 ... | JSON-encoded data          |
|-------|----------------------------|

JSON commands are of the form:

{
    "command": "train|query",
    "data": ...
}

For a "train" command, the "data" property is an object of the form:

{
    "keywords": [ ... ],
    "types": [ ... ],
    "locations": [ ... ]
}

For a "query" command, the "data" property is just the string query.

Previously, commands were of the form:
    t:keywords|types|locations
    q:query

For the sake of backwards compatibility, we continue to support that for now.
"""

from adapt.engine import IntentDeterminationEngine
from adapt.intent import IntentBuilder
from socketserver import BaseRequestHandler, ThreadingTCPServer
import json
import struct
import threading

_DEBUG = False


class TCPServer(ThreadingTCPServer):
    """Threaded TCP server."""

    def __init__(self, address, cls):
        """Initialize the server."""
        self.allow_reuse_address = True
        ThreadingTCPServer.__init__(self, address, cls)

        self.engine = None
        self.engine_lock = threading.Lock()


class Handler(BaseRequestHandler):
    """Request handler class."""

    def parse_legacy_message(self, message):
        """
        Parse a legacy message.

        message -- message to parse
        """
        message = message.decode()

        if message[0] == 't':
            parts = message[2:].split('|')
            if len(parts) < 3:
                return None

            return {
                'command': 'train',
                'data': {
                    'keywords': parts[0].split(','),
                    'types': parts[1].split(','),
                    'locations': parts[2].split(','),
                },
            }
        elif message[0] == 'q':
            return {
                'command': 'query',
                'data': message[2:],
            }
        else:
            return None

    def send_error(self, error):
        """
        Send an error to the client.

        error -- message to send
        """
        self.request.sendall(json.dumps({
            'status': 'error',
            'error': error,
        }).encode('utf-8'))

    def send_success(self, data=None):
        """
        Send a success status to the client.

        data -- optional data to send
        """
        message = {
            'status': 'success',
        }

        if data is not None:
            message['data'] = data

        self.request.sendall(json.dumps(message).encode('utf-8'))

    def read_bytes(self, count=None):
        """
        Read bytes from the stream.

        count -- optional number of bytes to read
        """
        if count is None:
            # Read everything we can
            return self.request.recv(4096 * 4)

        data = b''
        while len(data) < count:
            data += self.request.recv(count - len(data))

        return data

    def train(self, keywords, types, locations):
        """
        Build and train the intent parser.

        keywords -- list of keywords
        types -- list of types
        locations -- list of locations
        """
        with self.server.engine_lock:
            self.server.engine = IntentDeterminationEngine()

            for kw in keywords:
                self.server.engine.register_entity(kw, 'Keyword')

            for t in types:
                self.server.engine.register_entity(t, 'Type')

            for loc in locations:
                self.server.engine.register_entity(loc, 'Location')

            intent = IntentBuilder('Intent')\
                .require('Keyword')\
                .optionally('Type')\
                .require('Location')\
                .build()

            self.server.engine.register_intent_parser(intent)

    def query(self, command):
        """
        Query the intent parser.

        command -- query string
        """
        if self.server.engine is None:
            return None, 'Intent parser was not trained.'

        result = None
        with self.server.engine_lock:
            for intent in self.server.engine.determine_intent(command):
                if intent.get('confidence') > 0:
                    result = intent
                    break

        if result is None:
            return None, 'Failed to parse command.'
        else:
            return result, None

    def handle(self):
        """Handle an incoming request."""
        legacy_mode = False

        initial = self.read_bytes(count=2)
        if initial.decode() in ['t:', 'q:']:
            legacy_mode = True
            message = self.parse_legacy_message(initial + self.read_bytes())
            if message is None:
                return
        else:
            length = struct.unpack('>I', initial + self.read_bytes(count=2))[0]
            message = self.read_bytes(count=length)
            try:
                message = json.loads(message.decode())
            except ValueError:
                self.send_error('Failed to decode message.')
                return

        if 'command' not in message or 'data' not in message:
            if not legacy_mode:
                self.send_error('Invalid message.')

            return

        data = message['data']

        if message['command'] == 'train':
            if _DEBUG:
                print('Train:', json.dumps(data))

            if 'keywords' not in data or \
                    'types' not in data or \
                    'locations' not in data:
                if not legacy_mode:
                    self.send_error('Input data is invalid.')

                return

            self.train(data['keywords'], data['types'], data['locations'])

            if legacy_mode:
                self.request.sendall('1'.encode('utf-8'))
            else:
                self.send_success()
        elif message['command'] == 'query':
            if _DEBUG:
                print('Query:', data)

            result, error = self.query(data)
            if error:
                if legacy_mode:
                    self.request.sendall('-1'.encode('utf-8'))
                else:
                    self.send_error(error)
            else:
                if legacy_mode:
                    self.request.sendall(json.dumps(result).encode('utf-8'))
                else:
                    self.send_success(data=result)
        elif not legacy_mode:
            self.send_error('Invalid command.')


if __name__ == '__main__':
    server = TCPServer(('127.0.0.1', 5555), Handler)
    server.serve_forever()
