# -*- coding: utf-8 -*-
"""
Protocol layer for 42's InterProcess Comm (IPC) socket interface.

This module is deliberately **pure protocol**: parsing and framing only, no
sockets, no Qt, no orb.  The socket loop lives in `Listener42` below, which is
a plain blocking loop suitable for a worker thread or a standalone script; a
Qt front end can sit on top without either layer knowing about the other.

The wire protocol, from upstream `Source/AutoCode/TxRxIPC.c` at commit
f5988756 (see `42_socket_survey.md`):

*42 -> peer (TX)*, once per simulation step::

    TIME 2026-205-12:34:56.789012345
    SC[0].qn = [ 1.234...e-01  ...  ]
    SC[0].wn = [ ... ]
    [ENDMSG]

then 42 **blocks** on ``read(Socket, Ack, 4)``.  The peer must send exactly
four bytes or the simulation stalls -- this is the single most important fact
about the protocol, and it is also the lever that makes run/pause/step
possible without modifying 42 (see `pause` on `Listener42`).

*peer -> 42 (RX)*: 42 does one ``read(Socket, Msg, 16384)``, immediately
writes its own 4-byte ack back, and parses the same line format.  It accepts
state variables only -- there is no command vocabulary.

Which side listens is set per socket in 42's ``InOut/Inp_IPC.txt``.  42's
shipped default is ``CLIENT``, i.e. 42 dials out and the peer listens, which
is what `Listener42` implements.
"""
import re
import socket

# 42 writes its message into a fixed `char Msg[16384]`, so a single message
# can never exceed this.  Used as the read size, matching 42's own.
MSG_BUFFER_SIZE = 16384

# The 4-byte acknowledgement.  42 reads exactly 4 bytes and does not inspect
# them, but it writes "Ack\0" in the other direction, so we match it.
ACK = b'Ack\x00'

ENDMSG = '[ENDMSG]'

# "TIME 2026-205-12:34:56.789012345" -- year, day-of-year, h, m, s
_TIME_RE = re.compile(
    r'^TIME\s+(\d+)-(\d+)-(\d+):(\d+):([\d.]+)\s*$')

# "SC[0].qn = [ 1.0e+00 2.0e+00 ]"  or  "CommLink[0].PathIsOcculted = 0"
_ASSIGN_RE = re.compile(r'^(?P<name>[^=]+?)\s*=\s*(?P<value>.+?)\s*$')


class Time42:
    """One 42 timestamp: year, day-of-year, hour, minute, second."""

    __slots__ = ('year', 'doy', 'hour', 'minute', 'second')

    def __init__(self, year, doy, hour, minute, second):
        self.year = year
        self.doy = doy
        self.hour = hour
        self.minute = minute
        self.second = second

    @property
    def seconds_of_day(self):
        return self.hour * 3600 + self.minute * 60 + self.second

    def __repr__(self):
        return (f'Time42({self.year}-{self.doy:03d}-{self.hour:02d}:'
                f'{self.minute:02d}:{self.second:012.9f})')

    def __eq__(self, other):
        return (isinstance(other, Time42)
                and (self.year, self.doy, self.hour, self.minute)
                    == (other.year, other.doy, other.hour, other.minute)
                and abs(self.second - other.second) < 1e-9)


class Message42:
    """A parsed 42 IPC message: a timestamp plus named state values.

    `values` maps the variable name exactly as 42 writes it -- e.g.
    "SC[0].qn", "SC[0].Whl[0].H", "CommLink[0].PathIsOcculted" -- to either a
    list of floats (the bracketed form) or a single float/int.

    Names are kept verbatim rather than parsed into indices, because 42's
    own prefix filtering is a literal string prefix match and keeping the
    same representation means a caller can filter the same way it configures.
    """

    __slots__ = ('time', 'values', 'unparsed')

    def __init__(self, time=None, values=None, unparsed=None):
        self.time = time
        self.values = values if values is not None else {}
        self.unparsed = unparsed if unparsed is not None else []

    def __repr__(self):
        return (f'<Message42 {self.time} {len(self.values)} values'
                + (f', {len(self.unparsed)} unparsed' if self.unparsed else '')
                + '>')

    def names_with_prefix(self, prefix):
        """Names matching `prefix`, using 42's own literal-prefix semantics."""
        return [n for n in self.values if n.startswith(prefix)]


def parse_value(text):
    """Parse the right-hand side of a 42 assignment.

    Bracketed forms become a list of floats; bare numbers become a float or
    int.  Anything unrecognised is returned as the stripped string rather
    than raising -- an unknown field should not sink a whole message.
    """
    text = text.strip()
    if text.startswith('[') and text.endswith(']'):
        inner = text[1:-1].strip()
        if not inner:
            return []
        try:
            return [float(tok) for tok in inner.split()]
        except ValueError:
            return text
    try:
        return int(text)
    except ValueError:
        pass
    try:
        return float(text)
    except ValueError:
        return text


def parse_message(text):
    """Parse one complete 42 message (with or without its `[ENDMSG]`).

    Returns a `Message42`.  Lines that do not match are collected in
    `unparsed` rather than discarded, so a protocol change upstream shows up
    as data instead of as silence.
    """
    msg = Message42()
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line == ENDMSG:
            continue
        m = _TIME_RE.match(line)
        if m:
            msg.time = Time42(int(m.group(1)), int(m.group(2)),
                              int(m.group(3)), int(m.group(4)),
                              float(m.group(5)))
            continue
        m = _ASSIGN_RE.match(line)
        if m:
            msg.values[m.group('name').strip()] = parse_value(m.group('value'))
        else:
            msg.unparsed.append(line)
    return msg


def format_value(value):
    """Render a Python value the way 42 writes it, for the RX direction.

    42 uses the C format "%18.12le".  The `l` there is a length modifier that
    C needs and Python rejects, so the Python equivalent is "{:18.12e}" --
    same width and precision, which is what actually has to match.
    """
    if isinstance(value, (list, tuple)):
        return '[' + ' '.join(f'{float(v):18.12e}' for v in value) + ']'
    if isinstance(value, int):
        return str(value)
    return f'{float(value):18.12e}'


def build_message(time=None, values=None):
    """Build a message to send *to* 42.

    42 accepts state variables only -- there is no command vocabulary -- so
    `values` should use the same names it emits.
    """
    lines = []
    if time is not None:
        lines.append(
            f'TIME {time.year}-{time.doy:03d}-{time.hour:02d}:'
            f'{time.minute:02d}:{time.second:012.9f}')
    for name, value in (values or {}).items():
        lines.append(f'{name} = {format_value(value)}')
    lines.append(ENDMSG)
    return '\n'.join(lines) + '\n'


class Listener42:
    """Accept one 42 connection and exchange messages with it.

    42's shipped `Inp_IPC.txt` uses Socket Role CLIENT, so 42 dials out and
    we listen.  Usage::

        with Listener42(port=10001) as lis:
            lis.accept()
            for msg in lis.messages():
                print(msg.time, msg.values.get('SC[0].qn'))

    **Acknowledgement is the contract.** `messages()` sends the 4-byte ack
    *after* yielding each message, so a slow consumer throttles 42 rather
    than losing data, and a consumer that stops iterating pauses it.  That is
    deliberate: it is what makes run/pause/step possible without touching 42.
    """

    def __init__(self, port=10001, host='', timeout=None):
        self.host = host
        self.port = port
        self.timeout = timeout
        self.server = None
        self.conn = None
        self.peer = None
        self._buf = ''

    def __enter__(self):
        self.open()
        return self

    def __exit__(self, *exc):
        self.close()
        return False

    def open(self):
        self.server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server.bind((self.host, self.port))
        self.server.listen(1)
        if self.timeout is not None:
            self.server.settimeout(self.timeout)
        return self

    def accept(self):
        """Block until 42 connects."""
        self.conn, self.peer = self.server.accept()
        if self.timeout is not None:
            self.conn.settimeout(self.timeout)
        return self.peer

    def read_message(self):
        """Read one complete message, up to and including `[ENDMSG]`.

        Returns the raw text, or None if 42 closed the connection.

        NOTE: 42 sends one message per simulation step and they can arrive
        coalesced or split across TCP segments, so this buffers and splits on
        the terminator rather than assuming one read is one message.  (42's
        own RX side does assume that -- see the survey -- which is a
        constraint on what we send, not on what we receive.)
        """
        while True:
            end = self._buf.find(ENDMSG)
            if end != -1:
                cut = end + len(ENDMSG)
                text, self._buf = self._buf[:cut], self._buf[cut:].lstrip('\n')
                return text
            chunk = self.conn.recv(MSG_BUFFER_SIZE)
            if not chunk:
                return None
            self._buf += chunk.decode('utf-8', errors='replace')

    def send_ack(self):
        """Send the 4-byte acknowledgement 42 is blocking on."""
        self.conn.sendall(ACK)

    def send_message(self, time=None, values=None):
        """Send state *to* 42 and consume the ack it sends back."""
        self.conn.sendall(build_message(time, values).encode('utf-8'))
        return self.conn.recv(len(ACK))

    def messages(self, limit=None):
        """Yield parsed messages, acking after each one.

        Acking *after* the yield is what lets a consumer pace the simulation.
        """
        count = 0
        while limit is None or count < limit:
            text = self.read_message()
            if text is None:
                return
            yield parse_message(text)
            self.send_ack()
            count += 1

    def close(self):
        for sock in (self.conn, self.server):
            try:
                if sock is not None:
                    sock.close()
            except OSError:
                pass
        self.conn = None
        self.server = None
