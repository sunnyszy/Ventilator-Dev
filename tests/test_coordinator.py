import time
from vent.common.message import ControlSetting, ControlSettingName
from vent.coordinator.coordinator import get_coordinator
import pytest
import random


@pytest.mark.parametrize("control_setting_name", [ControlSettingName.PIP,
                                                  ControlSettingName.PIP_TIME,
                                                  ControlSettingName.PEEP,
                                                  ControlSettingName.BREATHS_PER_MINUTE,
                                                  ControlSettingName.INSPIRATION_TIME_SEC])
def test_single_process_simulation(control_setting_name):
    coordinator = get_coordinator(single_process=True, sim_mode=True)
    coordinator.start()
    t = time.time()
    v = random.randint(10, 100)
    v_min = v - 5
    v_max = v + 5
    c = ControlSetting(name=control_setting_name, value=v, min_value=v_min, max_value=v_max, timestamp=t)
    coordinator.set_control(c)
    time.sleep(0.1)
    c_read = coordinator.get_control(control_setting_name)

    assert c_read.name == c.name
    assert c_read.value == c.value
    assert c_read.min_value == c.min_value
    assert c_read.max_value == c.max_value
    assert c_read.timestamp == c.timestamp
    assert coordinator.get_msg_timestamp() > t
