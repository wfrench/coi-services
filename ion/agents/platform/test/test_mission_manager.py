#!/usr/bin/env python

"""
@package ion.agents.platform.test.test_mission_manager
@file    ion/agents/platform/test/test_mission_manager.py
@author  Carlos Rueda
@brief   Test cases for platform agent integrated with mission scheduler
"""

__author__ = 'Carlos Rueda'
__license__ = 'Apache 2.0'

# bin/nosetests -sv --nologcapture ion/agents/platform/test/test_mission_manager.py:TestPlatformAgentMission.test_simple_mission_command_state
# bin/nosetests -sv --nologcapture ion/agents/platform/test/test_mission_manager.py:TestPlatformAgentMission.test_simple_mission_streaming_state


from ion.agents.platform.test.base_test_platform_agent_with_rsn import BaseIntTestPlatform
from ion.agents.platform.platform_agent_enums import PlatformAgentEvent
from ion.agents.platform.platform_agent_enums import PlatformAgentState

from interface.objects import AgentCommand

from pyon.public import log, CFG

from gevent import sleep
from mock import patch
from unittest import skipIf
import os

@patch.dict(CFG, {'endpoint': {'receive': {'timeout': 180}}})
@skipIf((not os.getenv('PYCC_MODE', False)) and os.getenv('CEI_LAUNCH_TEST', False), 'Skip until tests support launch port agent configurations.')
class TestPlatformAgentMission(BaseIntTestPlatform):
    """
    """
    def _run_startup_commands(self, recursion=True):
        self._ping_agent()
        self._initialize(recursion)
        self._go_active(recursion)
        self._run(recursion)

    def _run_shutdown_commands(self, recursion=True):
        """
        Issues commands as needed to bring the parent platform to shutdown.
        """
        log.debug('[mm] _run_shutdown_commands.  state=%s', self._get_state())
        try:
            state = self._get_state()
            if state != PlatformAgentState.UNINITIALIZED:
                if state in [PlatformAgentState.IDLE,
                             PlatformAgentState.STOPPED,
                             PlatformAgentState.COMMAND,
                             PlatformAgentState.LOST_CONNECTION]:
                    self._go_inactive(recursion)

                self._reset(recursion)
        finally:  # attempt shutdown anyway
            self._shutdown(True)  # NOTE: shutdown always with recursion=True

    def _set_mission(self, yaml_filename):
        log.debug('[mm] _set_mission: setting agent param mission = %s', yaml_filename)
        self._pa_client.set_agent({'mission': yaml_filename})

    def _get_mission(self):
        mission = self._pa_client.get_agent(['mission'])['mission']
        self.assertIsNotNone(mission)
        log.debug('[mm] _get_mission: agent param mission = %s', mission)
        return mission

    def _run_mission(self):
        cmd = AgentCommand(command=PlatformAgentEvent.RUN_MISSION)
        retval = self._execute_agent(cmd)
        log.debug('[mm] _run_mission: RUN_MISSION return: %s', retval)

    def _await_mission_completion(self, mission_state, max_wait=None):
        """
        @param mission_state  The mission that we are waiting to leave
        @param max_wait       maximum wait; no effect if None
        """
        step = 5
        elapsed = 0
        while (max_wait is None or elapsed < max_wait) and mission_state == self._get_state():
            sleep(step)
            elapsed += step
            if elapsed % 20 == 0:
                log.debug('[mm] _await_mission_completion: waiting, elapsed=%s', elapsed)

        state = self._get_state()
        if mission_state != state:
            log.info('[mm] _await_mission_completion: completed, elapsed=%s, '
                     'transitioned from=%s to=%s', elapsed, mission_state, state)
        else:
            log.warn('[mm] _await_mission_completion: timeout, elapsed=%s, '
                     'still in state=%s', elapsed, mission_state)

    def _test_simple_mission(self, mission_filename, in_command_state, max_wait=None):
        """
        Verifies mission execution, mainly as coordinated from platform agent.
        Verifications regarding the concrete steps in the mission plan itself,
        or events published from there, and the like, are not done here.

        @param mission_filename
        @param in_command_state
                    True to start mission execution in COMMAND state.
                    False to start mission execution in MONITORING state.
        @param max_wait
                    maximum wait for mission completion; no effect if None.
                    Actual argument in the tests is based on local tests plus
                    some extra time mainly for buildbot. The extra time is rather
                    large due to the high variability in the execution elapsed
                    time. In any case, we want to avoid waiting forever.
        """
        self._set_receive_timeout()

        if in_command_state:
            base_state    = PlatformAgentState.COMMAND
            mission_state = PlatformAgentState.MISSION_COMMAND
        else:
            base_state    = PlatformAgentState.MONITORING
            mission_state = PlatformAgentState.MISSION_STREAMING

        # start everything up to platform agent in COMMAND state.
        # Instruments launched here are the ones referenced in the mission
        # file below.
        instr_keys = ['SBE37_SIM_02']
        p_root = self._set_up_single_platform_with_some_instruments(instr_keys)
        self._start_platform(p_root)
        self.addCleanup(self._stop_platform, p_root)
        self.addCleanup(self._run_shutdown_commands)
        self._run_startup_commands()

        if not in_command_state:
            self._start_resource_monitoring()

        # now prepare, set, and run mission:

        # TODO determine appropriate instrument identification mechanism as the
        # instrument keys (like SBE37_SIM_02) are basically only known in
        # the scope of the tests. In the following, we transform the mission
        # file so the instrument keys are replaced by the corresponding
        # instrument_device_id's:

        string = open(mission_filename).read()
        for instr_key in instr_keys:
            i_obj = self._get_instrument(instr_key)
            resource_id = i_obj.instrument_device_id
            log.debug('[mm] replacing %s to %s', instr_key, resource_id)
            string = string.replace(instr_key, resource_id)

        generated_filename = mission_filename.replace(".yml", "_GENERATED.yml")
        with open(generated_filename, 'w') as f:
            f.write(string)

        # now set and run mission:
        self._set_mission(generated_filename)
        self._run_mission()

        state = self._get_state()
        if state == mission_state:
            # ok, this is the general expected behaviour here as typical
            # mission plans should at least take several seconds to complete;
            # now wait until mission is completed:
            self._await_mission_completion(mission_state, max_wait)
        # else: mission completed/failed very quickly; we should be
        # back in the base state, as verified below in general.

        # verify we are back to the base_state:
        self._assert_state(base_state)

        if not in_command_state:
            self._stop_resource_monitoring()

    def test_simple_mission_command_state(self):
        #
        # With mission plan to be started in COMMAND state.
        #
        self._test_simple_mission(
            "ion/agents/platform/test/mission_RSN_simulator0C.yml",
            in_command_state=True,
            max_wait=200 + 300)

    def test_simple_mission_streaming_state(self):
        #
        # With mission plan to be started in MONITORING state.
        #
        self._test_simple_mission(
            "ion/agents/platform/test/mission_RSN_simulator0S.yml",
            in_command_state=False,
            max_wait=200 + 300)
