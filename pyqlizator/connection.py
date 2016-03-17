import socket

import msgpack

from .exceptions import Error


class Socket(object):

    def __init__(self, host, port, timeout=2):
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._sock.connect((host, port))
        self._sock.settimeout(timeout)

    def close(self):
        self._sock.shutdown(socket.SHUT_RDWR)
        self._sock.close()

    def recv(self, buf_size=4096):
        while True:
            buf = self._sock.recv(buf_size)
            if not buf:
                return
            # yield received chunks immediately instead of collecting
            # all together so that streaming parsers can be utilized
            yield buf
            # in case the received package was smaller than `buf_size`
            # prevent the generator from doing any more work
            if len(buf) < buf_size:
                return

    def send(self, data):
        self._sock.sendall(data)


class Connection(object):
    SQLITE_DATE_TYPES = ('date', 'datetime', 'timestamp')
    MAX_VARIABLE_NUMBER = 999
    # server commands
    EXECUTE = 1
    EXECUTE_AND_FETCH = 2
    # server reply status codes
    OK = 0
    UNKNOWN_ERROR = 1
    INVALID_REQUEST = 2
    DESERIALIZATION_ERROR = 3
    DATABASE_OPENING_ERROR = 4
    DATABASE_NOT_FOUND = 5
    INVALID_QUERY = 5
    # client error codes
    NETWORK_ERROR = 100
    # in case an error message is not found in the reply
    DEFAULT_MESSAGE = 'Unknown error.'

    socket_cls = Socket

    _to_primitive_converters = {}
    _from_primitive_converters = {}

    def __init__(self, host, port, database, path):
        self._dbname = database
        self._dbpath = path
        try:
            self._socket = self.socket_cls(host, port)
        except (socket.error, socket.timeout) as exc:
            self._socket = None
            raise Error(self.NETWORK_ERROR, str(exc), exc)
        else:
            self._connect_to_database()

    @classmethod
    def to_primitive(cls, obj):
        try:
            fn = cls._to_primitive_converters[type(obj)]
        except KeyError:
            return obj
        else:
            return fn(obj)

    @classmethod
    def from_primitive(cls, value, type_name):
        try:
            fn = cls._from_primitive_converters[type_name]
        except KeyError:
            return value
        else:
            return fn(value)

    @classmethod
    def register_to_primitive(cls, type_object, fn):
        cls._to_primitive_converters[type_object] = fn

    @classmethod
    def register_from_primitive(cls, type_name, fn):
        cls._from_primitive_converters[type_name] = fn

    def _send(self, data):
        serialized = msgpack.packb(data, default=self.to_primitive)
        try:
            self._socket.send(serialized)
        except (socket.error, socket.timeout) as exc:
            self._socket = None
            raise Error(self.NETWORK_ERROR, str(exc), exc)

    def _recv(self):
        unpacker = msgpack.Unpacker()
        self._meta_info = None
        try:
            for data in self._socket.recv():
                unpacker.feed(data)
                for obj in unpacker:
                    reply = self._process_reply(obj)
                    if reply:
                        yield reply
        except (socket.error, socket.timeout) as exc:
            self._socket = None
            raise Error(self.NETWORK_ERROR, str(exc), exc)

    def _construct_row(self, data):
        row = dict()
        for ((col_name, col_type), value) in zip(self._meta_info, data):
            row[col_name] = self.from_primitive(value, col_type)
        return row

    def _check_status(self, data):
        # a dict containing ``status`` key holds the information about
        # whether the query was successful or not
        status = data.get('status', self.UNKNOWN_ERROR)
        if status != self.OK:
            message = data.get('message', self.DEFAULT_MESSAGE)
            raise self.Error(status, message)

        return None

    def _process_reply(self, data):
        if isinstance(data, dict):
            return self._check_status(data)

        if data and isinstance(data[-1], (list, tuple)):
            self._meta_info = data
            return None

        return self._construct_row(data)

    def _connect_to_database(self):
        data = {'endpoint': 'connect',
                'database': self._dbname,
                'path': self._dbpath}
        self._send(data)
        return list(self._recv())

    def _command(self, operation, sql, *parameters):
        try:
            (params,) = parameters
        except ValueError:
            params = ()

        data = {'endpoint': 'query',
                'operation': operation,
                'database': self._dbname,
                'query': sql,
                'parameters': params}
        self._send(data)
        return self._recv()

    def execute(self, sql, *parameters):
        return self._command(self.EXECUTE,
                             sql,
                             *parameters)

    def fetch(self, sql, *parameters):
        return self._command(self.EXECUTE_AND_FETCH,
                             sql,
                             *parameters)

    @property
    def closed(self):
        return self._socket is None

    def close(self):
        self._socket.close()
        self._socket = None

    def drop_database(self):
        data = {'endpoint': 'drop',
                'database': self._dbname,
                'path': self._dbpath}
        self._send(data)
        return list(self._recv())

