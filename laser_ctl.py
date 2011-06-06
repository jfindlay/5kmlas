#!/usr/bin/env python
# laser_ctl.py
# Wed Feb 16 16:05:00 MST 2011
# findlay@cosmic.utah.edu

# TODO:
# - daemonize: move script to /usr/bin/laser_ctl and create
#   /etc/init.d/laser_ctl.  Allow for foreground connections to be made by
#   middle drum operators.  PTH init will occur on SBC bootup, retain a
#   persistent connection with the daemon, and will log environment and
#   battery data continuously.  The rest of the sequence will be controlled by
#   a simple `laser_ctl run` command assisted by argparse.  Run data and non-
#   run PTH data will be batched onto the data USB storage and formatted into a
#   DST bank by an anacron job at middle drum, where it will be pooled into the
#   regular data collection and processing streams as already implemented in
#   middle drum operations.
# - if interactive process fails, daemon process shuts down modules gracefully
# - daemon process polls PTH periodically.  Polling interval is shorter while
#   interactive process is running
# - need some kind of subprocess IPC setup to accomplish these goals
# - capture serial timeout errors at all possible points
# - color output option

# list of modules:
# - control
#   * data
#   * PTH
#     - rain
#     - heater
#     - inverter
#   * RPC
#     - radiometer
#     - shutter
#     - laser

import re
from datetime import datetime,timedelta
from time import sleep
from serial import Serial

# toggle debugging messages.  TODO: control this with invocation
debug = True

class Enum:
  # this idiom is from http://norvig.com/python-iaq.html.  It might be better
  # to use collections.namedtuple, but this datatype wasn't added to python
  # until 2.6.  I could upgrade debian to squeeze, but I'm loth to stray too
  # far from Technologic Systems' officially supported debian versions
  '''
  Create an enumerated type, then add var/value pairs to it.
  The constructor and the method .ints(names) take a list of variable names,
  and assign them consecutive integers as values.  The method .strs(names)
  assigns each variable name to itself (that is variable 'v' has value 'v').
  The method .vals(a=99, b=200) allows you to assign any value to variables.
  A 'list of variable names' can also be a string, which will be .split().
  The method .end() returns one more than the maximum int value.

  Example: opcodes = Enum('add sub load store').vals(illegal=255).
  '''

  def __init__(self,names=[]) : self.ints(names)

  def set(self,var,val):
    '''Set var to the value val in the enum.'''
    if var in vars(self).keys() : raise AttributeError('duplicate var in enum')
    if val in vars(self).values() : raise ValueError('duplicate value in enum')
    vars(self)[var] = val
    return self

  def strs(self,names):
    '''Set each of the names to itself (as a string) in the enum.'''
    for var in self._parse(names) : self.set(var,var)
    return self

  def ints(self,names):
    '''Set each of the names to the next highest int in the enum.'''
    for var in self._parse(names) : self.set(var,self.end())
    return self

  def vals(self,**entries):
    '''Set each of var=val pairs in the enum.'''
    for (var,val) in entries.items() : self.set(var,val)
    return self

  def end(self):
    '''One more than the largest int value in the enum, or 0 if none.'''
    try : return max([x for x in vars(self).values() if type(x)==type(0)]) + 1
    except ValueError : return 0

  def _parse(self,names):
    ### If names is a string, parse it as a list of names.
    if type(names) == type('') : return names.split()
    else : return names

# phases
phase = Enum('init run final')
# hardware states
power_state = Enum('undefined on off')
conf_state = Enum('undefined initialized finalized error')
rain_state = Enum('dry wet open')

class Arg:
  '''
  class to handle invocation arguments and options
  '''

  def __init__(self):
    pass

  def parse_args(self):
    pass

class Data:
  def __init__(self):
    self.radiometer = []
    self.PTH = []
    zero_time = datetime.utcfromtimestamp(0)
    self.times = {'start':zero_time,'stop':zero_time}

  def append(self,*args,**kwargs):
    if 'radiometer_datum' in kwargs:
      self.radiometer.append(kwargs['radiometer_datum'])
    if 'PTH_datum' in kwargs:
      self.PTH.append(kwargs['PTH_datum'])
    if 'start' in kwargs:
      self.times['start'] = kwargs['start']
    if 'stop' in kwargs:
      self.times['stop'] = kwargs['stop']
  def write(self):
    pass
    # TODO:
    # load objects from DST.py and write data structure into DST file
    # the format of the DST file will be a heterogeneous stream with one part per UTC day

class PTH(Serial):
  '''
  PTH module

  ?|HELP                  - help
  AIN [B|C|D|E]           - read inputs as analog (V)
  AMON [B|C|D|E] [<th>]   - set analog input threshold (V)
  AUTO [<sec>]            - set automatic readout period - 0 disables
  ECHO [0|1]              - serial echo - 0=disable 1=enable
  HEAT [0|1]              - set SHT11 heater - 0=off 1=on
  HUMID                   - read humidity (%RH)
  IN [A|B|C|D|E]          - read inputs as digital (0|1)
  OUT [A|B|C|D|E] [0|1]   - read [set] isolated output
  PRESS                   - read pressure (kPa)
  RAIN                    - read rain sensor dry|wet|open (D|W|X)
  RMON [0|1]              - set rain monitor enable
  SUPPLY                  - read supply voltage (V)
  TEMP                    - read temperture (degK)
  TENAB [0|1]             - set thermostat enable - 0 disables
  THIGH [<temp>]          - set cooler set point (output D)
  TLOW [<temp>]           - set heater set point (output E)
  VER                     - read device firmware version
  '''

  def __init__(self,*args,**kwargs):
    self.buffer_size = 65536    # = 2**2**2**2 : termios read buffer size
    self.name = 'PTH board'     # PTH module name
    self.conf_message = ''      # state message
    self.message = ''           # result message
    try:
      super(Serial,self).__init__('/dev/tts/0',baudrate=9600,timeout=0.5)
    except:
      self.conf_state = conf_state.error
      self.message = 'failed to initialize %s serial connection: ' % self.name
      self.message += '' # TODO: put pyserial error message in here
      return
    self.write('ECHO 0\r\n')    # disable PTH-side serial echo
    self.read(self.buffer_size) # clear output buffer
    self.check_conf_state()

  def check_conf_state(self):
    self.write('VER\r\n')                         # check PTH initialized
    self.conf_message = self.read(self.buffer_size)[:-2] # strip final '\r\n' characters from state message
    if re.search(r'VER\s+\S+',self.conf_message): # parse version message
      self.conf_state = conf_state.initialized    # module conf state
      self.message = 'PTH version: "%s"' % self.conf_message
    else:                                         # PTH did not print version message
      self.conf_state = conf_state.error
      self.message = 'PTH did not print version message.'
      self.message += '\nPTH output: "%s"' % self.conf_message

  def on(self,module=None): # close a PTH switch
    self.write('%s\r\n' % module.PTH_on_command) # close PTH switch for module
    module.PTH_message = self.read(self.buffer_size)[:-2] # capture PTH message and strip final '\r\n'
    self.check_switch_state(module=module)       # check module power on
    if module.power_state == power_state.on:     # if module powered on
      sleep(module.power_on_sleep)               # wait for module to stabilize
      module.message = '%s is on PTH switch %s' % (module.name,module.PTH_switch)
      module.message += '\nPTH message: "%s"' % module.PTH_message
    else:                                        # module failed to power on
      module.message = '%s is on PTH switch %s' % (module.name,module.PTH_switch)
      module.message += '\nPTH message: "%s"' % module.PTH_message
      module.message += '\nPTH message should be: "%s"' % module.PTH_on_command

  def off(self,module=None): # open a PTH switch
    self.write('%s\r\n' % module.PTH_off_command) # open PTH switch for module
    module.PTH_message = self.read(self.buffer_size)[:-2] # capture PTH message and strip final '\r\n'
    self.check_switch_state(module=module)        # check module power off
    if module.power_state == power_state.off:     # if module powered off
      sleep(module.power_off_sleep)               # wait for module to stabilize
      module.message = '%s is on PTH switch %s' % (module.name,module.PTH_switch)
      module.message += '\nPTH message: "%s"' % module.PTH_message
    else:                                         # module failed to power off
      module.message = '%s is on PTH switch %s' % (module.name,module.PTH_switch)
      module.message += '\nPTH message: "%s"' % module.PTH_message
      module.message += '\nPTH message should be: "%s"' % module.PTH_off_command

  def check_switch_state(self,module=None)
    if re.search(r'%s' % module.PTH_on_command,module.PTH_message,re.M):
      module.power_state = power_state.on
    elif re.search(r'%s' % module.PTH_off_command,module.PTH_message,re.M):
      module.power_state = power_state.off
    else:
      module.power_state = power_state.undefined

  def poll_data(self):
    self.read(self.buffer_size) # clear output buffer
    self.write('PRESS\r\n')  ; press = self.read(self.buffer_size)
    self.write('TEMP\r\n')   ; temp = self.read(self.buffer_size)
    self.write('HUMID\r\n')  ; humid = self.read(self.buffer_size)
    self.write('SUPPLY\r\n') ; supply = self.read(self.buffer_size)
    data_dict = {'timestamp':datetime.utcnow()}
    for measure in press,temp,humid,supply:
      # typical datum = ['PRESS','867.3']
      datum = re.split(r'\s+',measure)[:-1]
      data_dict[datum[0]] = float(datum[1])
    return data_dict

  def poll_rain(self,module=None):
    self.read(self.buffer_size) # clear output buffer
    self.write('RAIN\r\n')
    module.PTH_message = self.read(self.buffer_size)[:-2] # read rain state and trim final '\r\n'
    rain_datum = re.split(r'\s+',module.PTH_message)[:-1]
    if rain_datum[1] == 'D': # dry
      module.rain_state = rain_state.dry
      module.message = 'no rain: "%s"' % module.PTH_message
    if rain_datum[1] == 'W': # wet
      module.rain_state = rain_state.wet
      module.message = 'rain detected: "%s"' % module.PTH_message
    if rain_datum[1] == 'X': # open or no rain monitor
      module.rain_state = rain_state.open
      module.message = '%s open or no %s present: "%s"' % (module.name,module.name,module.PTH_message)

class Rain:
  '''rain module'''

  def __init__(self):
    self.name = 'rain monitor'               # heater module name
    self.power_state = power_state.undefined # module power state
    self.PTH_switch = 'RMON'                 # PTH board switch name
    self.PTH_on_command = '%s 1' % self.PTH_switch # PTH board on command
    self.PTH_off_command = '%s 0' % self.PTH_switch # PTH board off command
    self.power_on_sleep = 5                  # time to stabilize after power on
    self.power_off_sleep = 0                 # time to stabilize after power off
    self.PTH_message = ''                    # PTH message
    self.message = ''                        # result message

class Heater:
  '''heater module'''

  def __init__(self):
    self.name = 'window heater'              # heater module name
    self.power_state = power_state.undefined # module power state
    self.PTH_switch = 'HEAT'                 # PTH board switch name
    self.PTH_on_command = '%s 1' % self.PTH_switch # PTH board on command
    self.PTH_off_command = '%s 0' % self.PTH_switch # PTH board off command
    self.power_on_sleep = 30                 # time to stabilize after power on
    self.power_off_sleep = 0                 # time to stabilize after power off
    self.PTH_message = ''                    # PTH message
    self.message = ''                        # result message

class Inverter:
  '''inverter module'''

  def __init__(self):
    self.name = 'power inverter'             # inverter module name
    self.power_state = power_state.undefined # module power state
    self.PTH_switch = 'A'                    # PTH board switch name
    self.PTH_on_command = 'OUT %s 1' % self.PTH_switch # PTH board on command
    self.PTH_off_command = 'OUT %s 0' % self.PTH_switch # PTH board off command
    self.power_on_sleep = 10                 # time to stabilize after power on
    self.power_off_sleep = 0                 # time to stabilize after power off
    self.PTH_message = ''                    # PTH message
    self.message = ''                        # result message

class RPC(Serial):
  '''
  RPC module

  RPC-2 Series
  (C) 1997 by BayTech
  F2.07

  Circuit Breaker: On

  1)...Outlet 1  : Off
  2)...Outlet 2  : Off
  3)...Outlet 3  : Off
  4)...Outlet 4  : Off
  5)...Outlet 5  : Off
  6)...Outlet 6  : Off
  '''

  def __init__(self):
    self.buffer_size = 65536 # = 2**2**2**2 : termios read buffer size
    self.name = 'RPC module' # RPC module name
    self.conf_message = ''   # state message
    self.message = ''        # result message
    try:
      super(Serial,self).__init__('/dev/tts/1',baudrate=9600,timeout=1)
    except:
      self.conf_state = conf_state.error
      self.message = 'failed to initialize %s serial connection: ' % self.name
      self.message += '' # TODO: put pyserial error message in here
      return
    self.check_conf_state()

  def check_conf_state(self):
    self.conf_message = self.read(self.buffer_size) # init message
    if re.search(r'BayTech',self.conf_message):     # parse message for 'BayTech' string
      self.conf_state = conf_state.initialized      # module conf state
      self.message = 'RPC initialized.'
      self.message += '\nRPC message:\n"%s"' % self.conf_message
    else: # not a BayTech RPC, no RPC present, or if RPC prints out a message, the message doesn't contain 'BayTech'
      self.conf_state = conf_State.error
      self.message = 'RPC did not initialize.'
      self.message += '\nRPC message:\n"%s"' % self.conf_message

  def on(self,module=None): # power on a RPC outlet
    self.write('ON %d\r\n' % module.RPC_outlet)      # power on RPC outlet for module
    sleep(0.5) ; self.write('Y\r\n')                 # wait 0.5 s and confirm power on
    module.RPC_message = self.read(self.buffer_size) # capture RPC message
    self.check_power_state(module=module)            # check powered on
    if module.power_state == power_state.on:         # if module powered on
      sleep(module.power_on_sleep)                   # wait for module to stabilize
      module.message = '%s is on RPC outlet %s' % (module.name,module.RPC_outlet)
      module.message += '\nRPC message:\n"%s"' % module.RPC_message
    else:                                            # module failed to power on
      module.message = '%s is on RPC outlet %s' % (module.name,module.RPC_outlet)
      module.message += '\nRPC message:\n"%s"\n' % module.RPC_message
      module.message += '\nRPC message should contain: "%d)...Outlet %d  : On"' % (module.RPC_outlet,module.RPC_outlet)

  def off(self,module=None): # power off a RPC outlet
    self.write('OFF %d\r\n' % module.RPC_outlet)     # power off RPC outlet for module
    sleep(0.5) ; self.write('Y\r\n')                 # wait 0.5 s and confirm power off
    module.RPC_message = self.read(self.buffer_size) # capture RPC message
    self.check_power_state(module=module)            # check powered off
    if module.power_state == power_state.off:        # if module powered off
      sleep(module.power_off_sleep)                  # wait for module to stabilize
      module.message = '%s is on RPC outlet %s' % (module.name,module.RPC_outlet)
      module.message += '\nRPC message:\n"%s"' % module.RPC_message
    else:                                            # module failed to power off
      module.message = '%s is on RPC outlet %s' % (module.name,module.RPC_outlet)
      module.message += '\nRPC message:\n"%s"\n' % module.RPC_message
      module.message += '\nRPC message should contain: "%d)...Outlet %d  : On"' % (module.RPC_outlet,module.RPC_outlet)

  def check_power_state(self,module=None):
    if re.search(r'^.*Outlet\s+%d\s+:\s+On.*$' % module.RPC_outlet,module.RPC_message,re.M):
      module.power_state = power_state.on
    elif re.search(r'^.*Outlet\s+%d\s+:\s+Off.*$' % module.RPC_outlet,module.RPC_message,re.M):
      module.power_state = power_state.off
    else:
      module.power_state = power_state.undefined

class Radiometer(Serial):
  '''
  radiometer module

  Auger CLF radiometer (RM-3700) settings from lwiencke:
  ID       Identity(3700)
  VR       Version
  TG 3     Trigger (0 internal, 3 external - positive edge)
  SS 0     Single shot (1 enable, 0 disable)
  FA 1.00  Calibration Factor Channel A - we use 1.00
  WA 335   Wavelength of laser(used to correct for Si probe response,)
  PA       Probe id and type (23 0 : 465 Si ), (2 0 : 734 pyro)
  EV 1     Event average       (should be 1)
  BS 0     In case this radiometer has batteries installed
  RA 4     Range  1,2,3:X,XX,XXX e-12 | 4,5,6:X,XX,XXX e-9 pJ
  ST       Return error status (should be 0)
  AD       ASCII Dump Mode
  '''

  def __init__(self): # software init
    self.name = 'radiometer'                 # radiometer module name
    self.power_state = power_state.undefined # power state
    self.conf_state = conf_state.undefined   # configuration state
    self.RPC_outlet = 1                      # RPC outlet number
    self.power_on_sleep = 0                  # time to wait after power on
    self.power_off_sleep = 0                 # time to wait after power off
    self.RPC_message = ''                    # RPC message
    self.conf_message = ''                   # state message
    self.message = ''                        # result message

  def init(self): # hardware init
    self.buffer_size = 65536          # = 2**2**2**2 : termios read buffer size
    try:
      # TODO: figure out how long the timeout needs to be to capture 5 m worth of radiometer data
      super(Serial,self).__init__('/dev/tts/2',baudrate=9600,timeout=5)
    except:
      self.conf_state = conf_state.error
      self.message = 'failed to initialize %s serial connection: ' % self.name
      self.message += '' # TODO: put pyserial error message in here
      return
    # the radiometer needs a timeout buffer between consecutive commands
    sleep(0.5) ; self.write('TG 1\r') # internal trigger
    sleep(0.5) ; self.write('SS 0\r') # no single shot
    sleep(0.5) ; self.write('RA 2\r') # range 2: TODO: energy limits on this range?
    sleep(0.5) ; self.write('BS 0\r') # disable internal battery save
    #self.flushInput()
    #self.flushOutput()               # doesn't work when run from SBC
    self.read(self.buffer_size)       # clear output buffer
    self.check_conf_state()
    self.write('AD\r')                # ASCII dump

  def check_conf_state(self):
    self.write('ST\r')               # check error status
    self.conf_message = self.read(self.buffer_size)[:-1] # strip final '\r' characters from state message
    if re.search(r'0',self.message): # if no errors
      self.conf_state = conf_state.initialized
      self.message = 'radiometer returned error status "0", no error'
    else: # TODO: try to figure out how to get radiometer into 0 (no) error state
      #self.conf_state = conf_state.error
      self.conf_state = conf_state.initialized
      self.message = 'radiometer returned error status "%s"' % self.conf_message

  def read_data(self):
    energies = []
    for i in re.split(r'\s+',self.read(self.buffer_size)):
      try: # only return the numbers from the radiometer message
        energies.append(float(i))
      except:
        pass
    data_dict = {'timestamp':datetime.utcnow(),'energies':energies}
    return data_dict

class Shutter:
  '''shutter module'''

  def __init__(self):
    self.name = 'shutter'                    # radiometer module name
    self.power_state = power_state.undefined # power state
    self.RPC_outlet = 3                      # RPC outlet number
    self.power_on_sleep = 10                 # time to wait after power on
    self.power_off_sleep = 10                # time to wait after power off
    self.RPC_message = ''                    # RPC message
    self.message = ''                        # result message

class Laser:
  '''laser module'''

  def __init__(self):
    self.name = 'laser'                      # radiometer module name
    self.power_state = power_state.undefined # power state
    self.RPC_outlet = 2                      # RPC outlet number
    self.power_on_sleep = 2                  # time to wait after power on
    self.power_off_sleep = 0                 # time to wait after power off
    self.RPC_message = ''                    # RPC message
    self.message = ''                        # result message

class Control:
  '''
  software control module for 5kmlas apparatus

  This control module wraps each function call of the other modules in order to
  simplify and unify error traps.  Each call sets one or more associated states
  in the module.  The control module will take action upon each setting of
  state: either proceed normally or try to return the hardware and software to
  a well-defined and safe state.

  This scheme assumes at least three things:
  - The python code and the operating system it runs on are either so much more
    reliable in comparison with the hardware that they aren't worth checking or
    they will provide their own error handling when necessary.
  - The firmware on the hardware is so much more reliable than the hardware
    itself that all problems will originate with a hardware failure or
    misconfiguration and that the firmware will report it.
  - The hardware modules will fail only at the time of a state change
  If any of the serial devices (PTH,RPC,radiometer) fail on the negotiation of
  the serial connection, pyserial will handle and report those errors and the
  control module will intercept those errors and shutdown as appropriate.

  The control process has three phases: init, run, and final.  Depending on the
  phase and module, the control module may fail in a different manner.
  '''

  def __init__(self):
    self.data = Data() # data structure
    self.phase = phase.init
    # TODO: connect to daemon process

  def init_PTH(self):
    print 'initializing PTH board ...'
    self.pth = PTH()                       # init PTH board
    self.check_init_state(module=self.pth) # check PTH init state

  def on_rain(self):
    print 'powering on rain monitor ...'
    self.rain = Rain()
    self.pth.on(module=self.rain)    # power on rain monitor module
    self.check_on_state(module=self.rain) # check rain monitor power state

  def off_rain(self):
    print 'powering off rain monitor ...'
    self.pth.off(module=self.rain)    # power off rain monitor module
    self.check_off_state(module=self.rain) # check rain monitor init state

  def poll_rain(self,phase_state=None):
    print 'checking rain monitor ...'
    self.pth.poll_rain(module=self.rain)   # poll rain state
    self.check_rain_state(module=self.rain) # check rain state

  def on_heater(self):
    print 'powering on heater ...'
    self.heater = Heater()                  # create heater object
    self.pth.on(module=self.heater)         # power on heater module
    self.check_on_state(module=self.heater) # check heater power state

  def off_heater(self):
    print 'powering off heater ...'
    self.pth.off(module=self.heater)         # power off heater module
    self.check_off_state(module=self.heater) # check heater power state

  def on_inverter(self):
    print 'powering on inverter ...'
    self.inverter = Inverter()                # create inverter object
    self.pth.on(module=self.inverter)         # power on inverter module
    self.check_on_state(module=self.inverter) # check inverter power state

  def off_inverter(self):
    print 'powering off inverter ...'
    self.pth.off(module=self.inverter)         # power off inverter module
    self.check_off_state(module=self.inverter) # check inverter power state

  def init_RPC(self):
    print 'initializing RPC module ...'
    self.rpc = RPC()                       # init RPC module
    self.check_init_state(module=self.rpc) # check RPC init state

  def on_radiometer(self):
    print 'powering on radiometer ...'
    self.radiometer = Radiometer()                # create radiometer object
    self.rpc.on(module=self.radiometer)           # power on radiometer module
    self.check_on_state(module=self.radiometer)   # check radiometer power state

  def init_radiometer(self):
    print 'initializing radiometer ...'
    self.radiometer.init()                        # init radiometer module
    self.check_init_state(module=self.radiometer) # check radiometer conf state

  def off_radiometer(self):
    print 'powering off radiometer ...'
    self.rpc.off(module=self.radiometer)           # power off radiometer module
    self.check_off_state(module=self.radiometer)   # check radiometer power state

  def on_shutter(self):
    print 'opening shutter ...'
    self.shutter = Shutter()                 # create shutter object
    self.rpc.on(module=self.shutter)         # power on shutter module
    self.check_on_state(module=self.shutter) # check shutter power state

  def off_shutter(self):
    print 'closing shutter ...'
    self.rpc.off(module=self.shutter)         # power off shutter module
    self.check_off_state(module=self.shutter) # check shutter power state

  def on_laser(self):
    print '  powering on laser ...'
    self.laser = Laser()                   # create laser object
    self.rpc.on(module=self.laser)         # power on laser module
    self.check_on_state(module=self.laser) # check laser power state

  def off_laser(self):
    print '  powering off laser ...'
    self.rpc.off(module=self.laser)         # power off laser
    self.check_off_state(module=self.laser) # check laser power state

  def write_data()
    print 'writing data ...'
    self.data.write() # format and save data
    print 'done'

  def check_init_state(self,module=None):
    if module.conf_state == conf_state.initialized:
      self.add_module(module)
      print 'done'
      if debug == True:
        print module.message
    elif module.conf_state == conf_state.undefined or module.conf_state == conf_state.finalized:
      print 'failed\n%s\n' % module.message
      self.emergency_shutdown()
    elif module.conf_state == conf_state.error:
      print 'error\n%s\n' % module.message
      self.emergency_shutdown()

  def check_final_state(self,module=None):
    if module.conf_state == conf_state.finalized:
      self.del_module(module)
      print 'done'
      if debug == True:
        print module.message
    elif module.conf_state == conf_state.undefined or module.conf_state == conf_state.initialized:
      print 'failed\n%s\n' % module.message
      self.emergency_shutdown()
    elif module.conf_state == conf_state.error:
      print 'error\n%s\n' % module.message
      self.emergency_shutdown()

  def check_on_state(self,module=None):
    if module.power_state == power_state.on:
      self.add_module(module)
      print 'done'
      if debug == True:
        print module.message
    elif module.power_state == power_state.undefined or module.power_state == power_state.off:
      print 'failed\n%s\n' % module.message
      self.emergency_shutdown()

  def check_off_state(self,module=None):
    if module.power_state == power_state.off:
      self.del_module(module)
      print 'done'
      if debug == True:
        print module.message
    elif module.power_state == power_state.undefined or module.power_state == power_state.on:
      print 'failed\n%s\n' % module.message
      self.emergency_shutdown()

  def check_rain_state(self,module=None):
    if module.rain_state == rain_state.dry:
      print 'dry'
      if debug == True:
        print module.message
    elif module.rain_state == rain_state.wet:
      print 'wet\n%s\n' % module.message
      if self.phase != phase.final:
        self.emergency_shutdown()
    elif module.rain_state == rain_state.open:
      print 'open\n%s\n' % module.message
      if self.phase != phase.final:
        self.emergency_shutdown()

  def emergency_shutdown(self):
    print '\nshutting down 5kmlas'
    if self.laser.power_state      == power_state.on : self.off_laser()
    self.data.write() # try to save whatever data we have
    if self.shutter.power_state    == power_state.on : self.off_shutter()
    if self.radiometer.power_state == power_state.on : self.off_radiometer()
    if self.inverter.power_state   == power_state.on : self.off_inverter()
    if self.heater.power_state     == power_state.on : self.off_heater()
    if self.rain.power_state       == power_state.on : self.off_rain()
    # perhaps set a flag on the SBC to not run again if there is a problem

class Interactive:
  '''
  operate 5kmlas system
  '''

  def __init__(self):
    self.control = Control() # control module

  def init(self):
    self.control.phase = phase.init
    self.control.init_PTH()        # init PTH board
    self.control.on_rain()         # power on rain monitor
    self.control.poll_rain(phase_state=phase.init) # check rain state
    self.control.on_heater()       # power on window heater
    self.control.on_inverter()     # power on inverter
    self.control.init_RPC()        # init RPC
    self.control.on_radiometer()   # power on radiometer
    self.control.init_radiometer() # init radiometer
    self.control.on_shutter()      # power on shutter

  def run(self):
    self.control.phase = phase.run
    print 'collecting data ...'
    five_minutes = timedelta(seconds=10)
    now = start_time = datetime.utcnow()       # record laser on time
    self.control.on_laser()                    # power on laser
    while (now < start_time + five_minutes):   # run for 5 minutes
      PTH_datum = self.control.pth.poll_data() # collect PTH data about every 5 seconds
      control.data.append(PTH_datum=PTH_datum)
      if debug == True : print PTH_datum       # print PTH datum when debugging
      sleep(5)
      now = datetime.utcnow()
    self.control.off_laser()                   # power off laser
    stop_time = datetime.utcnow()              # record laser off time
    print 'done'

  def final(self):
    self.control.phase = phase.final
    self.control.off_shutter()    # close shutter
    radiometer_datum = self.control.read_radiometer_data() # read data
    self.control.data.append(radiometer_datum=radiometer_datum,
        start=start_time,stop=stop_time)
    self.control.write_data()     # write data
    self.control.off_radiometer() # power off radiometer
    self.control.off_inverter()   # power off inverter
    self.control.off_heater()     # power off window heater
    self.control.off_rain()       # power off rain monitor
    print control.data.radiometer
    print control.data.PTH
    print control.data.times

def main():
  if opt == 'daemon':
    daemon = Daemon() # daemon process
    daemon.init()
    daemon.run()
  if opt == 'interactive': # or 'run'?
    interactive = Interactive() # operate 5kmlas system
    interactive.init()
    interactive.run()
    interactive.final()

if __name__ == '__main__' : main()
