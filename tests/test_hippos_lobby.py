import json
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'services' / 'hippos-lobby'))

import hippos_lobby as lobby
import lobby_chat as chat
import lobby_rooms as rooms
from lobby_validation import LobbyError

ROOM = {'port': 31200, 'emulator': 'riverhorse', 'core_name': 'riverhorse', 'game_name': 'Crash Team Racing',
        'game_crc': 'abcd1234', 'username': 'fox', 'upnp': True}


class FakeClock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


class RoomsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.clock = FakeClock()
        self.rooms = rooms.Rooms(self.clock)

    def test_listing_uses_lobby_shape_with_server_side_ip(self):
        self.rooms.create('203.0.113.5', {**ROOM, 'ip': '1.1.1.1'})
        fields = self.rooms.listing()[0]['fields']
        self.assertEqual((fields['ip'], fields['port'], fields['game_crc'], fields['core_name']),
                         ('203.0.113.5', 31200, 'ABCD1234', 'riverhorse'))

    def test_room_expires_without_heartbeat(self):
        room = self.rooms.create('203.0.113.5', ROOM)
        self.clock.now += rooms.ROOM_TTL_SECONDS - 1
        self.rooms.heartbeat(room.id, room.token)
        self.clock.now += rooms.ROOM_TTL_SECONDS - 1
        self.assertEqual(len(self.rooms.listing()), 1)
        self.clock.now += 2
        self.assertEqual(self.rooms.listing(), [])

    def test_delete_needs_the_room_token(self):
        room = self.rooms.create('203.0.113.5', ROOM)
        with self.assertRaises(LobbyError):
            self.rooms.delete(room.id, 'wrong')
        self.rooms.delete(room.id, room.token)
        self.assertEqual(self.rooms.listing(), [])

    def test_open_rooms_per_ip_are_capped(self):
        for _ in range(rooms.MAX_ROOMS_PER_IP):
            self.rooms.create('203.0.113.5', ROOM)
        with self.assertRaises(LobbyError) as raised:
            self.rooms.create('203.0.113.5', ROOM)
        self.assertEqual(raised.exception.status, 429)
        self.rooms.create('203.0.113.6', ROOM)

    def test_invalid_fields_are_rejected(self):
        for bad in ({'port': 0}, {'port': '31200'}, {'core_name': 'a b'}, {'emulator': ''}, {'game_crc': 'xyz'}, {'username': ''}):
            with self.subTest(bad=bad), self.assertRaises(LobbyError):
                self.rooms.create('203.0.113.5', {**ROOM, **bad})


class ChallengeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.rooms = rooms.Rooms(FakeClock())
        self.room = self.rooms.create('203.0.113.5', {**ROOM, 'emulator': 'flycast', 'core_name': 'flycast',
                                                      'port': 19713, 'mode': 'challenge'})

    def _challenge(self, ip: str = '198.51.100.7', username: str = 'vm2') -> str:
        return self.rooms.challenge(self.room.id, ip, {'username': username})['token']

    def test_host_sees_pending_challenger_and_room_leaves_listing(self):
        self.assertEqual(self.rooms.listing()[0]['fields']['mode'], 'challenge')
        self.assertEqual(self.rooms.status(self.room.id, self.room.token), {'challenger': None})
        token = self._challenge()
        self.assertEqual(self.rooms.status(self.room.id, self.room.token),
                         {'challenger': {'username': 'vm2', 'ip': '198.51.100.7', 'state': 'pending'}})
        self.assertEqual(self.rooms.challenge_state(self.room.id, token), {'state': 'pending'})
        self.assertEqual(self.rooms.listing(), [])

    def test_accepted_challenger_gets_host_address(self):
        token = self._challenge()
        self.rooms.answer(self.room.id, self.room.token, {'accept': True})
        self.assertEqual(self.rooms.challenge_state(self.room.id, token),
                         {'state': 'accepted', 'ip': '203.0.113.5', 'port': 19713})

    def test_declined_challenger_is_told_and_room_reopens(self):
        token = self._challenge()
        self.rooms.answer(self.room.id, self.room.token, {'accept': False})
        self.assertEqual(self.rooms.challenge_state(self.room.id, token), {'state': 'declined'})
        self.assertEqual(len(self.rooms.listing()), 1)
        self._challenge('198.51.100.8', 'vm3')

    def test_answer_needs_a_waiting_challenger(self):
        with self.assertRaises(LobbyError) as raised:
            self.rooms.answer(self.room.id, self.room.token, {'accept': True})
        self.assertEqual(raised.exception.status, 409)

    def test_cancelled_challenge_reopens_room(self):
        token = self._challenge()
        self.rooms.cancel_challenge(self.room.id, token)
        self.assertEqual(len(self.rooms.listing()), 1)
        with self.assertRaises(LobbyError):
            self.rooms.challenge_state(self.room.id, token)

    def test_silent_challenger_expires(self):
        self._challenge()
        self.rooms._clock.now += rooms.CHALLENGER_TTL_SECONDS + 1
        self.rooms.heartbeat(self.room.id, self.room.token)
        self.assertEqual(self.rooms.status(self.room.id, self.room.token), {'challenger': None})

    def test_second_challenger_is_refused(self):
        self.rooms.challenge(self.room.id, '198.51.100.7', {'username': 'vm2'})
        with self.assertRaises(LobbyError) as raised:
            self.rooms.challenge(self.room.id, '198.51.100.8', {'username': 'vm3'})
        self.assertEqual(raised.exception.status, 409)

    def test_listen_rooms_take_no_challenges(self):
        listen = self.rooms.create('203.0.113.5', ROOM)
        with self.assertRaises(LobbyError):
            self.rooms.challenge(listen.id, '198.51.100.7', {'username': 'vm2'})

    def test_status_needs_the_room_token(self):
        with self.assertRaises(LobbyError):
            self.rooms.status(self.room.id, 'wrong')


class ChatTests(unittest.TestCase):
    def setUp(self) -> None:
        self.clock = FakeClock()
        self.files = Path(tempfile.mkdtemp())
        self.bans = self.files / 'banned-ips.txt'
        self.words = self.files / 'word-filter.txt'
        self.chat = chat.Chat(chat.Moderation(self.bans, self.words), self.clock)

    def _say(self, text, ip='203.0.113.5', channel='global', username='fox'):
        self.clock.now += chat.MIN_SECONDS_BETWEEN_MESSAGES
        return self.chat.post(ip, channel, {'username': username, 'text': text})

    def test_messages_after_an_id_per_channel(self):
        first = self._say('hello')
        self._say('anyone on psx?', channel='psx')
        second = self._say('again')
        self.assertEqual([m['text'] for m in self.chat.messages('global', first.id)], ['again'])
        self.assertEqual([m['id'] for m in self.chat.messages('global', 0)], [first.id, second.id])
        self.assertEqual(len(self.chat.messages('psx', 0)), 1)

    def test_too_fast_is_rejected(self):
        self._say('one')
        with self.assertRaises(LobbyError) as raised:
            self.chat.post('203.0.113.5', 'global', {'username': 'fox', 'text': 'two'})
        self.assertEqual(raised.exception.status, 429)

    def test_banned_ip_and_cidr(self):
        self.bans.write_text('198.51.100.0/24\n')
        with self.assertRaises(LobbyError):
            self._say('hi', ip='198.51.100.9')
        self._say('hi', ip='203.0.113.5')

    def test_word_filter_masks_whole_words(self):
        self.words.write_text('darn\n')
        self.assertEqual(self._say('Darn it, darnation').text, '**** it, darnation')

    def test_messages_expire(self):
        self._say('old')
        self.clock.now += chat.MESSAGE_TTL_SECONDS + 1
        self.assertEqual(self.chat.messages('global', 0), [])

    def test_invalid_input(self):
        for channel, body in (('Bad Channel', {'username': 'fox', 'text': 'x'}),
                              ('global', {'username': '', 'text': 'x'}),
                              ('global', {'username': 'fox', 'text': 'x' * (chat.MAX_MESSAGE + 1)}),
                              ('global', {'username': 'fox', 'text': 'line\nbreak'})):
            with self.subTest(channel=channel, body=body), self.assertRaises(LobbyError):
                self.clock.now += chat.MIN_SECONDS_BETWEEN_MESSAGES
                self.chat.post('203.0.113.5', channel, body)


class ServerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.server = lobby.make_server('127.0.0.1', 0, trusted_proxies=frozenset({'127.0.0.1'}))
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.base = f'http://127.0.0.1:{self.server.server_port}'

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()

    def _request(self, method: str, path: str, body=None, headers=None):
        data = None if body is None else json.dumps(body).encode()
        request = urllib.request.Request(self.base + path, data=data, method=method, headers=headers or {})
        with urllib.request.urlopen(request) as response:
            content = response.read()
            return response.status, json.loads(content) if content else None

    def test_create_list_heartbeat_delete(self):
        status, created = self._request('POST', '/rooms', ROOM, {'X-Forwarded-For': '198.51.100.7'})
        self.assertEqual((status, created['ip']), (201, '198.51.100.7'))
        auth = {'Authorization': f'Bearer {created["token"]}'}
        self.assertEqual(self._request('PUT', f'/rooms/{created["id"]}', headers=auth)[0], 204)
        _, listing = self._request('GET', '/list/')
        self.assertEqual(listing[0]['fields']['id'], created['id'])
        self.assertNotIn('token', listing[0]['fields'])
        self.assertEqual(self._request('DELETE', f'/rooms/{created["id"]}', headers=auth)[0], 204)
        self.assertEqual(self._request('GET', '/list')[1], [])

    def test_challenge_over_http(self):
        _, created = self._request('POST', '/rooms', {**ROOM, 'mode': 'challenge'}, {'X-Forwarded-For': '198.51.100.7'})
        status, challenge = self._request('POST', f'/rooms/{created["id"]}/challenge', {'username': 'vm2'},
                                          {'X-Forwarded-For': '203.0.113.9'})
        self.assertEqual(status, 201)
        host_auth = {'Authorization': f'Bearer {created["token"]}'}
        challenger_auth = {'Authorization': f'Bearer {challenge["token"]}'}
        _, room = self._request('GET', f'/rooms/{created["id"]}', headers=host_auth)
        self.assertEqual(room['challenger']['ip'], '203.0.113.9')
        self.assertEqual(self._request('POST', f'/rooms/{created["id"]}/answer', {'accept': True}, host_auth)[0], 204)
        _, state = self._request('GET', f'/rooms/{created["id"]}/challenge', headers=challenger_auth)
        self.assertEqual((state['state'], state['ip']), ('accepted', '198.51.100.7'))

    def test_challenge_cancel_over_http(self):
        _, created = self._request('POST', '/rooms', {**ROOM, 'mode': 'challenge'})
        _, challenge = self._request('POST', f'/rooms/{created["id"]}/challenge', {'username': 'vm2'})
        auth = {'Authorization': f'Bearer {challenge["token"]}'}
        self.assertEqual(self._request('DELETE', f'/rooms/{created["id"]}/challenge', headers=auth)[0], 204)
        self.assertEqual(len(self._request('GET', '/list')[1]), 1)

    def test_chat_post_and_poll(self):
        status, message = self._request('POST', '/chat/global', {'username': 'fox', 'text': 'hi'})
        self.assertEqual(status, 201)
        _, polled = self._request('GET', f'/chat/global?after={message["id"] - 1}')
        self.assertEqual(polled['messages'][0]['text'], 'hi')
        self.assertEqual(self._request('GET', f'/chat/global?after={message["id"]}')[1], {'messages': []})

    def test_bad_request_returns_error_status(self):
        with self.assertRaises(urllib.error.HTTPError) as raised:
            self._request('POST', '/rooms', {**ROOM, 'port': -1})
        self.assertEqual(raised.exception.code, 400)


if __name__ == '__main__':
    unittest.main()
