import time
from typing import List

import numpy as np

from vent.common.message import SensorValues, ControlSetting, Alarm, AlarmSeverity, ControlSettingName


class ControlModuleBase:
    # Abstract class for controlling hardware based on settings received
    #   Functions:
    def __init__(self):
        self.sensor_values = None
        self.control_settings = None
        self.loop_counter = None
        self.active_alarms = {}  # dictionary of active alarms
        self.logged_alarms = []  # list of all resolved alarms

    def get_sensors(self) -> SensorValues:
        # returns SensorValues
        # include a timestamp and loop counter
        pass

    def get_alarms(self) -> List[Alarm]:
        # Get a list of all alarms
        pass

    def get_active_alarms(self):
        # Get a dictionary of all active alarms
        pass

    def get_logged_alarms(self) -> List[Alarm]:
        # Get a list of inactive alarms
        pass

    def clear_logged_alarms(self):
        pass

    def set_control(self, control_setting: ControlSetting):
        # takes ControlSetting struct
        pass

    def get_control(self, control_setting_name: ControlSettingName) -> ControlSetting:
        pass

    def start(self, controlSettings):
        # start running
        # controls actuators to achieve target state
        # determined by settings and assessed by sensor values
        pass

    def stop(self):
        # stop running
        pass

    def test_critical_levels(min, max, value, name, active_alarms, logged_alarms):
        # Tests whether a variable exceeds its bounds, and produces an alert.
        pass


class ControlModuleDevice(ControlModuleBase):
    # Implement ControlModuleBase functions
    pass


class Balloon_Simulator:
    '''
    This is a simulator for inflating a balloon. 
    For math, see https://en.wikipedia.org/wiki/Two-balloon_experiment
    '''

    def __init__(self, leak, delay):
        # Hard parameters for the simulation
        self.max_volume = 6  # Liters  - 6?
        self.min_volume = 1.5  # Liters - baloon starts slightly inflated.
        self.PC = 20  # Proportionality constant that relates pressure to cm-H2O
        self.P0 = 0  # Minimum pressure.
        self.leak = leak
        self.delay = delay

        self.temperature = 37  # keep track of this, as is important output variable
        self.humidity = 90
        self.fio2 = 60

        # Dynamical parameters - these are the initial conditions
        self.current_flow = 0  # in unit  liters/sec
        self.current_pressure = 0  # in unit  cm-H2O
        self.r_real = (3 * self.min_volume / (4 * np.pi)) ** (1 / 3)  # size of the lung
        self.current_volume = self.min_volume  # in unit  liters

    def get_pressure(self):
        return self.current_pressure

    def get_volume(self):
        return self.current_volume

    def set_flow(self, Qin, Qout):
        self.current_flow = Qin - Qout

    def update(self, dt):  # Performs an update of duration dt [seconds]
        self.current_volume += self.current_flow * dt

        if self.leak:
            RC = 5  # pulled 5 sec out of my hat
            s = dt / (RC + dt)
            self.current_volume = self.current_volume + s * (self.min_volume - self.current_volume)

        # This is fromt the baloon equation, uses helper variable (the baloon radius)
        r_target = (3 * self.current_volume / (4 * np.pi)) ** (1 / 3)
        r0 = (3 * self.min_volume / (4 * np.pi)) ** (1 / 3)

        # Delay -> Expansion takes time
        if self.delay:
            RC = 0.1  # pulled these 100ms out of my hat
            s = dt / (RC + dt)
            self.r_real = self.r_real + s * (r_target - self.r_real)
        else:
            self.r_real = r_target

        self.current_pressure = self.P0 + (self.PC / (r0 ** 2 * self.r_real)) * (1 - (r0 / self.r_real) ** 6)

        # Temperature, humidity and o2 fluctuations modelled as OUprocess
        self.temperature = OUupdate(self.temperature, dt=dt, mu=37, sigma=0.3, tau=1)
        self.fio2 = OUupdate(self.fio2, dt=dt, mu=60, sigma=5, tau=1)
        self.humidity = OUupdate(self.humidity, dt=dt, mu=90, sigma=5, tau=1)
        if self.humidity > 100:
            self.humidity = 100


def OUupdate(variable, dt, mu, sigma, tau):
    '''
    This is a simple function to produce an OU process.
    It is used as model for fluctuations in measurement variables.
    inputs:
       variable:   float     value at previous time step
       dt      :   timestep
       mu      :   mean
       sigma   :   noise amplitude
       tau     :   time scale
    returns:
       new_variable :  value of "variable" at next time step
    '''
    sigma_bis = sigma * np.sqrt(2. / tau)
    sqrtdt = np.sqrt(dt)
    new_variable = variable + dt * (-(variable - mu) / tau) + sigma_bis * sqrtdt * np.random.randn()
    return new_variable


class StateController:
    '''
    This is a class to control a respirator by iterating through set states with hard-coded valve settings
    '''

    def __init__(self):
        self.PIP = 22
        self.PIP_time = 1.0
        self.PEEP = 5
        self.PEEP_time = 0.5  # as fast as possible, try 500ms
        self.bpm = 10
        self.I_phase = 1.0
        self.Qin = 0
        self.Qout = 0
        self.pressure = 0
        self.volume = 0
        self.last_update = time.time()
        # Derived variables
        self.cycle_duration = 60 / self.bpm
        self.E_phase = self.cycle_duration - self.I_phase
        self.t_inspiration = self.PIP_time  # time [sec] for the four phases
        self.t_plateau = self.I_phase - self.PIP_time
        self.t_expiration = self.PEEP_time
        self.t_PEEP = self.E_phase - self.PEEP_time

        # Parameters to keep track of breath-cycle
        self.cycle_start = time.time()
        self.cycle_waveforms = {}  # saves the waveforms to meassure pip, peep etc.
        self.cycle_counter = 0

    def update_internalVeriables(self):
        self.cycle_duration = 60 / self.bpm
        self.E_phase = self.cycle_duration - self.I_phase
        self.t_inspiration = self.PIP_time
        self.t_plateau = self.I_phase - self.PIP_time
        self.t_expiration = self.PEEP_time
        self.t_PEEP = self.E_phase - self.PEEP_time

    def get_Qin(self):
        return self.Qin

    def get_Qout(self):
        return self.Qout

    def update(self, pressure):
        now = time.time()
        cycle_phase = now - self.cycle_start
        time_since_last_update = now - self.last_update
        self.last_update = now

        self.volume += time_since_last_update * (
                    self.Qin - self.Qout)  # Integrate what has happened within the last few seconds
        # NOTE: As Qin and Qout are set, this is what the controllr believes has happened. NOT A MEASUREMENT, MIGHT NOT BE REALITY!

        self.pressure = pressure

        if cycle_phase < self.t_inspiration:  # ADD CONTROL dP/dt
            # to PIP, air in as fast as possible
            self.Qin = 1
            self.Qout = 0
            if self.pressure > self.PIP:
                self.Qin = 0
        elif cycle_phase < self.I_phase:  # ADD CONTROL P
            # keep PIP plateau, let air in if below
            self.Qin = 0
            self.Qout = 0
            if self.pressure < self.PIP:
                self.Qin = 1
        elif cycle_phase < self.t_expiration + self.I_phase:
            # to PEEP, open exit valve
            self.Qin = 0
            self.Qout = 1
            if self.pressure < self.PEEP:
                self.Qout = 0
        elif cycle_phase < self.cycle_duration:
            # keeping PEEP, let air in if below
            self.Qin = 0
            self.Qout = 0
            if self.pressure < self.PEEP:
                self.Qin = 1
        else:
            self.cycle_start = time.time()  # new cycle starts
            self.cycle_counter += 1

        if self.cycle_counter not in self.cycle_waveforms.keys():  # if this cycle doesn't exist yet, start it
            self.cycle_waveforms[self.cycle_counter] = np.array([[0, pressure, self.volume]])  # add volume
        else:
            data = self.cycle_waveforms[self.cycle_counter]
            data = np.append(data, [[cycle_phase, pressure, self.volume]], axis=0)
            self.cycle_waveforms[self.cycle_counter] = data


class ControlModuleSimulator(ControlModuleBase):
    # Implement ControlModuleBase functions
    def __init__(self):
        super().__init__()  # get all from parent

        self.Balloon = Balloon_Simulator(leak=True, delay=False)
        self.Controller = StateController()
        self.loop_counter = 0
        self.pressure = 15
        self.last_update = time.time()

        # Variable limits to raise alarms, initialized as +- 10% of what the controller initializes
        self.PIP_min = self.Controller.PIP * 0.9
        self.PIP_max = self.Controller.PIP * 1.1
        self.PIP_lastset = time.time()
        self.PIP_time_min = self.Controller.PIP_time * 0.9
        self.PIP_time_max = self.Controller.PIP_time * 1.1
        self.PIP_time_lastset = time.time()
        self.PEEP_min = self.Controller.PEEP * 0.9
        self.PEEP_max = self.Controller.PEEP * 1.1
        self.PEEP_lastset = time.time()
        self.bpm_min = self.Controller.bpm * 0.9
        self.bpm_max = self.Controller.bpm * 1.1
        self.bpm_lastset = time.time()
        self.I_phase_min = self.Controller.I_phase * 0.9
        self.I_phase_max = self.Controller.I_phase * 1.1
        self.I_phase_lastset = time.time()

        # These are measurement values from the last breath cycle.
        # NOTE: For the controller target value, see Controller.PEEP etc.
        self.PEEP = None  # Measured valued of PEEP
        self.PIP = None  # Measured value of PIP
        self.first_PIP = None  # Time of reaching PIP plateau
        self.I_phase = None  # Time when PIP plateau ends is end of inspiratory phase
        self.first_PEEP = None  # Time when PEEP is reached first
        self.last_PEEP = None  # Last time of PEEP - by definition end of breath cycle
        self.bpm = None  # Measured breathing rate, by definition 60sec / length_of_breath_cycle
        self.vte = None  # Maximum air displacement in last breath cycle

    def test_critical_levels(self, min, max, value, name):
        '''
        This tests whether a variable is within bounds.
        If it is, and an alarm existed, then the "alarm_end_time" is set.
        If it is NOT, a new alarm is generated and appendede to the alarm-list.
        Input:
            min:           minimum value  (e.g. 2)
            max:           maximum value  (e.g. 5)
            value:         test value   (e.g. 3)
            name:          parameter type (e.g. "PIP", "PEEP" etc.)
        '''
        if (value < min) or (value > max):  # If the variable is not within limits
            if name not in self.active_alarms.keys():  # And and alarm for that variable doesn't exist yet -> RAISE ALARM.
                new_alarm = Alarm(alarm_name=name, is_active=True, severity=AlarmSeverity.RED, \
                                  alarm_start_time=time.time(), alarm_end_time=None)
                self.active_alarms[name] = new_alarm
        else:  # Else: if the variable is within bounds,
            if name in self.active_alarms.keys():  # And an alarm exists -> inactivate it.
                old_alarm = self.active_alarms[name]
                old_alarm.alarm_end_time = time.time()
                old_alarm.is_active = False
                self.logged_alarms.append(old_alarm)
                del self.active_alarms[name]

    def update_alarms(self):
        ''' This goes through the LAST waveform, and updates alarms.'''
        this_cycle = self.Controller.cycle_counter

        if this_cycle > 1:  # The first cycle for which we can calculate this is cycle "1".
            data = self.Controller.cycle_waveforms[this_cycle - 1]
            phase = data[:, 0]
            pressure = data[:, 1]
            volume = data[:, 2]

            self.vte = np.max(volume) - np.min(volume)

            # get the pressure niveau heuristically (much faster than fitting)
            # 20 and 80 percentiles pulled out of my hat.
            self.PEEP = np.percentile(pressure, 20)
            self.PIP = np.percentile(pressure, 80)

            # measure time of reaching PIP, and leaving PIP
            self.first_PIP = phase[np.min(np.where(pressure > self.PIP))]
            self.I_phase = phase[np.max(np.where(pressure > self.PIP))]

            # and measure the same for PEEP
            self.first_PEEP = phase[np.min(np.where(np.logical_and(pressure < self.PEEP, phase > 1)))]
            self.bpm = 60. / phase[-1]  # 60 sec divided by the duration of last waveform

            self.test_critical_levels(min=self.PIP_min, max=self.PIP_max, value=self.PIP, name="PIP")
            self.test_critical_levels(min=self.PIP_time_min, max=self.PIP_time_max, value=self.first_PIP,
                                      name="PIP_TIME")
            self.test_critical_levels(min=self.PEEP_min, max=self.PEEP_max, value=self.PEEP, name="PEEP")
            self.test_critical_levels(min=self.bpm_min, max=self.bpm_max, value=self.bpm, name="BREATHS_PER_MINUTE")
            self.test_critical_levels(min=self.I_phase_min, max=self.I_phase_max, value=self.I_phase, name="I_PHASE")

    def get_sensors(self):
        # returns SensorValues and a time stamp

        self.update_alarms()  # Make sure we are up to date

        self.sensor_values = SensorValues(pip=self.Controller.PIP,
                                          peep=self.PEEP,
                                          fio2=self.Balloon.fio2,
                                          temp=self.Balloon.temperature,
                                          humidity=self.Balloon.humidity,
                                          pressure=self.Balloon.current_pressure,
                                          vte=self.vte,
                                          breaths_per_minute=self.bpm,
                                          inspiration_time_sec=self.I_phase,
                                          timestamp=time.time())

        return self.sensor_values

    def get_alarms(self):
        # Returns all alarms as a list
        ls = self.logged_alarms
        for alarm_key in self.active_alarms.keys():
            ls.append(self.active_alarms[alarm_key])
        return ls

    def get_active_alarms(self):
        # Returns only the active alarms
        return self.active_alarms

    def get_logged_alarms(self):
        # Returns only the inactive alarms
        return self.logged_alarms

    def set_control(self, control_setting):
        ''' Updates the control settings. '''
        if control_setting.name == ControlSettingName.PIP:
            self.Controller.PIP = control_setting.value
            self.PIP_min = control_setting.min_value
            self.PIP_max = control_setting.max_value
            self.PIP_lastset = control_setting.timestamp

        elif control_setting.name == ControlSettingName.PIP_TIME:
            self.Controller.PIP_time = control_setting.value
            self.PIP_time_min = control_setting.min_value
            self.PIP_time_max = control_setting.max_value
            self.PIP_time_lastset = control_setting.timestamp

        elif control_setting.name == ControlSettingName.PEEP:
            self.Controller.PEEP = control_setting.value
            self.PEEP_min = control_setting.min_value
            self.PEEP_max = control_setting.max_value
            self.PEEP_lastset = control_setting.timestamp

        elif control_setting.name == ControlSettingName.BREATHS_PER_MINUTE:
            self.Controller.bpm = control_setting.value
            self.bpm_min = control_setting.min_value
            self.bpm_max = control_setting.max_value
            self.bpm_lastset = control_setting.timestamp

        elif control_setting.name == ControlSettingName.INSPIRATION_TIME_SEC:
            self.Controller.I_phase = control_setting.value
            self.I_phase_min = control_setting.min_value
            self.I_phase_max = control_setting.max_value
            self.I_phase_lastset = control_setting.timestamp

        else:
            raise KeyError("You cannot set the variabe: " + str(control_setting.name))

        self.Controller.update_internalVeriables()

    def get_control(self, control_setting_name: ControlSettingName) -> ControlSetting:
        ''' Updates the control settings. '''
        if control_setting_name == ControlSettingName.PIP:
            return ControlSetting(control_setting_name,
                                  self.Controller.PIP,
                                  self.PIP_min,
                                  self.PIP_max,
                                  self.PIP_lastset)
        elif control_setting_name == ControlSettingName.PIP_TIME:
            return ControlSetting(control_setting_name,
                                  self.Controller.
                                  PIP_time,
                                  self.PIP_time_min,
                                  self.PIP_time_max,
                                  self.PIP_time_lastset, )
        elif control_setting_name == ControlSettingName.PEEP:
            return ControlSetting(control_setting_name,
                                  self.Controller.PEEP,
                                  self.PEEP_min,
                                  self.PEEP_max,
                                  self.PEEP_lastset)
        elif control_setting_name == ControlSettingName.BREATHS_PER_MINUTE:
            return ControlSetting(control_setting_name,
                                  self.Controller.bpm,
                                  self.bpm_min,
                                  self.bpm_max,
                                  self.bpm_lastset)
        elif control_setting_name == ControlSettingName.INSPIRATION_TIME_SEC:
            return ControlSetting(control_setting_name,
                                  self.Controller.I_phase,
                                  self.I_phase_min,
                                  self.I_phase_max,
                                  self.I_phase_lastset)
        else:
            raise KeyError("You cannot set the variabe: " + str(control_setting_name))

    def run(self):
        # start running
        # controls actuators to achieve target state
        # determined by settings and assessed by sensor values

        self.loop_counter += 1
        now = time.time()
        self.Balloon.update(now - self.last_update)
        self.last_update = now

        pressure = self.Balloon.get_pressure()
        temperature = self.Balloon.temperature

        self.Controller.update(pressure)
        Qout = self.Controller.get_Qout()
        Qin = self.Controller.get_Qin()
        self.Balloon.set_flow(Qin, Qout)

    def stop(self):
        # stop running
        pass

    def recvUIHeartbeat(self):
        return time.time()


def get_control_module(sim_mode=False):
    if sim_mode == True:
        return ControlModuleSimulator()
    else:
        return ControlModuleDevice()
