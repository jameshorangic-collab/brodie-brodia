"""Offline checks for the exact Chert room/participant/media contract."""
import asyncio
import contextlib
import io
import json
import os
from pathlib import Path
from types import SimpleNamespace as NS
import sys
import unittest
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from livekit import api
from facetime import facetime_oss
from facetime.brodia import RoleplayConfig


def participant(identity, *tracks, agent=True):
    return NS(identity=identity, kind=api.ParticipantInfo.Kind.AGENT if agent else 0,
              tracks=[NS(name=name) for name in tracks])


class DispatchTests(unittest.IsolatedAsyncioTestCase):
    def client(self, responses):
        client = NS(room=NS(create_room=AsyncMock(), list_participants=AsyncMock(side_effect=responses)),
                    agent_dispatch=NS(create_dispatch=AsyncMock()))
        context = AsyncMock()
        context.__aenter__.return_value = client
        return context, client

    async def test_waits_for_both_tracks_on_same_agent(self):
        responses = [NS(participants=[participant('current', 'coach-audio')]),
                     NS(participants=[participant('current', 'coach-audio', 'brodia-avatar')])]
        context, client = self.client(responses)
        with patch.object(api, 'LiveKitAPI', return_value=context), \
             patch.object(asyncio, 'sleep', new_callable=AsyncMock), \
             patch.dict(os.environ, {'AGENT_NAME': 'other-checkout'}), \
             contextlib.redirect_stdout(io.StringIO()):
            room, target = await facetime_oss.dispatch_and_wait(RoleplayConfig('barista', 'interested'), 2,
                                                              'production-worker')
        self.assertEqual(target, 'current')
        self.assertEqual(client.room.list_participants.await_count, 2)
        dispatch = client.agent_dispatch.create_dispatch.call_args.args[0]
        self.assertEqual(dispatch.agent_name, 'production-worker')
        self.assertEqual(dispatch.room, room)
        self.assertEqual(json.loads(dispatch.metadata), {'brodia': {'scenario': 'barista', 'receptivity': 'interested'}})
        self.assertEqual(client.room.create_room.call_args.args[0].empty_timeout, 3600)

    async def test_does_not_combine_different_participants_tracks(self):
        response = NS(participants=[participant('audio-worker', 'coach-audio'),
                                    participant('video-worker', 'brodia-avatar'),
                                    participant('caller', 'coach-audio', 'brodia-avatar', agent=False)])
        context, _ = self.client([response])
        with patch.object(api, 'LiveKitAPI', return_value=context), \
             patch.object(asyncio, 'sleep', new_callable=AsyncMock):
            with self.assertRaisesRegex(SystemExit, 'did not publish coach-audio \\+ brodia-avatar'):
                await facetime_oss.dispatch_and_wait(RoleplayConfig('park', 'neutral'), .5, 'production-worker')

    async def test_new_room_every_call_and_exact_target_identity(self):
        context, client = self.client([NS(participants=[participant('agent-exact-id', 'coach-audio', 'brodia-avatar')])]*2)
        with patch.object(api, 'LiveKitAPI', return_value=context), contextlib.redirect_stdout(io.StringIO()):
            first = await facetime_oss.dispatch_and_wait(RoleplayConfig('park', 'neutral'), 1, 'production-worker')
            second = await facetime_oss.dispatch_and_wait(RoleplayConfig('park', 'neutral'), 1, 'production-worker')
        self.assertNotEqual(first[0], second[0])
        self.assertEqual(first[1], 'agent-exact-id')
        self.assertEqual(client.agent_dispatch.create_dispatch.await_count, 2)


if __name__ == '__main__':
    unittest.main()
