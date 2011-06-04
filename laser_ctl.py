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
# - change failure responses as appropriate: it is not necessary to 'emergency
#   shutdown' after every failure
# - shutdown if rain detected
# - PTH and RPC don't really use the check_*_state scheme as implemented.  Is
#   there a command that can be used to test the success of their
#   initialization?
# - capture and handle pyserial errors on the PTH, RPC, and radiometer
# - debug flag to print out internal messages

# list of modules:
# control
#   data
#   PTH
#     rain
#     heater
#     inverter
#   RPC
#     radiometer
#     shutter
#     laser

import re
from datetime import datetime,timedelta
from time import sleep
from serial import Serial

class Data:
  def __init__(self):
    self.radiometer = []
    self.pth = []
    zero_time = datetime.utcfromtimestamp(0)
    self.times = {'start':zero_time,'stop':zero_time}

  def append(self,*args,**kwargs):
    if 'radiometer_datum' in kwargs:
      self.radiometer.append(kwargs['radiometer_datum'])
    if 'pth_datum' in kwargs:
      self.pth.append(kwargs['pth_datum'])
    if 'start' in kwargs:
      self.times['start'] = kwargs['start']
    if 'stop' in kwargs:
      self.times['stop'] = kwargs['stop']
  def write(self):
    pass
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
    self.buffer_size = 65536                  # = 2**2**2**2 : termios read buffer size
    self.name = 'PTH board'                   # PTH module name
    self.message = ''                         # state message
    super(Serial,self).__init__('/dev/tts/0',baudrate=9600,timeout=0.5)
    self.write('ECHO 0\r\n')                  # disable PTH-side serial echo
    self.read(self.buffer_size)               # clear output buffer
    self.write('HELP\r\n')                    # check PTH initialized
    self.output = self.read(self.buffer_size)
    if re.search(r'\?\|HELP\s+-\s+help',self.output,re.M):
      self.conf_state = conf_state.initialized  # module conf state: undefined,initialized,finalized
    else: # PTH did not print help message
      self.conf_state = conf_state.error

  def on_rain(self,module=None):
    self.write('RMON 1\r\n')                        # enable rain monitoring
    module.PTH_output = self.read(self.buffer_size) # capture PTH output
    module.message = '\nPTH output:\n%s' % module.PTH_output
    self.check_switch_state(module=module)          # check that rmon got enabled
    if module.power_state == power_state.on:        # if module powered on
      sleep(module.power_on_sleep)                  # wait for module to stabilize

  def off_rain(self,module=None):
    self.write('RMON 0\r\n')                        # disable rain monitoring
    module.PTH_output = self.read(self.buffer_size) # capture PTH output
    module.message = '\nPTH output:\n%s' % module.PTH_output
    self.check_switch_state(module=module)          # check that rmon got disabled
    if module.power_state == power_state.off:       # if module powered off
      sleep(module.power_off_sleep)                 # wait for module to stabilize

  def on(self,module=None): # close a PTH switch
    self.write('OUT %s 1\r\n' % module.PTH_switch)  # close PTH switch for module
    module.PTH_output = self.read(self.buffer_size) # capture PTH output
    module.message = '%s is on PTH switch %s\n\nPTH output:\n%s' % (module.name,module.PTH_switch,module.PTH_output)
    self.check_switch_state(module=module)          # check module power on
    if module.power_state == power_state.on:        # if module powered on
      sleep(module.power_on_sleep)                  # wait for module to stabilize

  def off(self,module=None): # open a PTH switch
    self.write('OUT %s 0\r\n' % module.PTH_switch)  # open PTH switch for module
    module.PTH_output = self.read(self.buffer_size) # capture PTH output
    module.message = '%s is on PTH switch %s\n\nPTH output:\n%s' % (module.name,module.PTH_switch,module.PTH_output)
    self.check_switch_state(module=module)          # check module power off
    if module.power_state == power_state.off:       # if module powered off
      sleep(module.power_off_sleep)                 # wait for module to stabilize

  def poll_data(self):
    self.read(self.buffer_size) # clear output buffer
    self.write('PRESS\r\n')  ; press = self.read(self.buffer_size)
    self.write('TEMP\r\n')   ; temp = self.read(self.buffer_size)
    self.write('HUMID\r\n')  ; humid = self.read(self.buffer_size)
    self.write('RAIN\r\n')   ; rain = self.read(self.buffer_size)
    self.write('SUPPLY\r\n') ; supply = self.read(self.buffer_size)
    data_dict = {}
    for measure in press,temp,humid,supply:
      # typical datum = ['PRESS','867.3']
      datum = re.split(r'\s+',measure)[:-1]
      data_dict[datum[0]] = float(datum[1])
    rain_datum = re.split(r'\s+',measure)[:-1]
    data_dict[rain_datum[0]] = rain_datum[1]
    data_dict['timestamp'] = datetime.utcnow()
    return data_dict

  def check_switch_state(self,module=None):
    if re.search(r'rain',module.name): # checking rain module switch
      if re.search(r'^.*RMON 1.*$',module.PTH_output,re.M):
        module.power_state = power_state.on
      elif re.search(r'^.*RMON 0.*$',module.PTH_output,re.M):
        module.power_state = power_state.off
      else:
        module.power_state = power_state.undefined
    else: # checking other module switch: heater or inverter
      if re.search(r'^.*OUT %s 1.*$' % module.PTH_switch,module.PTH_output,re.M):
        module.power_state = power_state.on
      elif re.search(r'^.*OUT %s 0.*$' % module.PTH_switch,module.PTH_output,re.M):
        module.power_state = power_state.off
      else:
        module.power_state = power_state.undefined

class Rain:
  '''rain module'''

  def __init__(self):
    self.name = 'rain monitor'               # heater module name
    self.power_state = power_state.undefined # module power state: undefined,on,off
    self.power_on_sleep = 5                  # time to stabilize after power on
    self.power_off_sleep = 0                 # time to stabilize after power off
    self.PTH_output = ''                     # PTH output
    self.message = ''                        # state message

class Heater:
  '''heater module'''

  def __init__(self):
    self.name = 'window heater'              # heater module name
    self.power_state = power_state.undefined # module power state: undefined,on,off
    self.PTH_switch = 'B'                    # PTH board switch name
    self.power_on_sleep = 30                 # time to stabilize after power on
    self.power_off_sleep = 0                 # time to stabilize after power off
    self.PTH_output = ''                     # PTH output
    self.message = ''                        # state message

class Inverter:
  '''inverter module'''

  def __init__(self):
    self.name = 'power inverter'             # inverter module name
    self.power_state = power_state.undefined # module power state: undefined,on,off
    self.PTH_switch = 'A'                    # PTH board switch name
    self.power_on_sleep = 10                 # time to stabilize after power on
    self.power_off_sleep = 0                 # time to stabilize after power off
    self.PTH_output = ''                     # PTH output
    self.message = ''                        # state message

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
    self.buffer_size = 65536                 # = 2**2**2**2 : termios read buffer size
    self.name = 'RPC module'                 # RPC module name
    self.message = ''                        # state message
    super(Serial,self).__init__('/dev/tts/1',baudrate=9600,timeout=2)
    output = self.read(self.buffer_size) # init message
    if re.search(r'RPC-2 Series\s+\(C\) 1997 by BayTech\s+F2\.07',output):
      self.conf_state = conf_state.initialized # module conf state: undefined,initialized,finalized

  def on(self,module=None): # power on a RPC outlet
    self.write('ON %d\r\n' % module.RPC_outlet)     # power on RPC outlet for module
    sleep(1) ; self.write('Y\r\n')                  # wait 1 s and confirm power on
    module.RPC_output = self.read(self.buffer_size) # capture RPC output
    module.message = '%s is on RPC outlet %d\n\nRPC output:\n%s' % (module.name,module.RPC_outlet,module.RPC_output)
    self.check_power_state(module=module)                 # check powered on
    if module.power_state == power_state.on:        # if module powered on
      sleep(module.power_on_sleep)                  # wait for module to stabilize

  def off(self,module=None): # power off a RPC outlet
    self.write('OFF %d\r\n' % module.RPC_outlet)    # power off RPC outlet for module
    sleep(1) ; self.write('Y\r\n')                  # wait 1 s and confirm power off
    module.RPC_output = self.read(self.buffer_size) # capture RPC output
    module.message = '%s is on RPC outlet %d\n\nRPC output:\n%s' % (module.name,module.RPC_outlet,module.RPC_output)
    self.check_power_state(module=module)                 # check powered off
    if module.power_state == power_state.off:       # if module powered off
      sleep(module.power_off_sleep)                 # wait for module to stabilize

  def check_power_state(self,module=None):
    if re.search(r'^.*Outlet\s+%d\s+:\s+On.*$' % module.RPC_outlet,module.RPC_output,re.M):
      module.power_state = power_state.on
    elif re.search(r'^.*Outlet\s+%d\s+:\s+Off.*$' % module.RPC_outlet,module.RPC_output,re.M):
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
    self.power_state = power_state.undefined # power state: undefined,on,off
    self.conf_state = conf_state.undefined   # configuration state: undefined,initialized,finalized
    self.RPC_outlet = 1                      # RPC outlet number
    self.power_on_sleep = 0                  # time to wait after power on
    self.power_off_sleep = 0                 # time to wait after power off
    self.RPC_output = ''                     # RPC output
    self.message = ''                        # state message

  def init(self): # hardware init
    self.buffer_size = 65536          # = 2**2**2**2 : termios read buffer size
    super(Serial,self).__init__('/dev/tts/2',baudrate=9600,timeout=5)
    # the radiometer needs a timeout buffer between consecutive commands
    sleep(0.5) ; self.write('TG 1\r') # internal trigger
    sleep(0.5) ; self.write('SS 0\r') # no single shot
    sleep(0.5) ; self.write('RA 2\r') # range 2: TODO: energy limits on this range?
    sleep(0.5) ; self.write('BS 0\r') # disable internal battery save
    #self.flushInput()
    #self.flushOutput()               # doesn't work when run from SBC
    self.read(self.buffer_size)       # clear output buffer
    self.write('ST\r')                # check return status
    self.output = self.read(self.buffer_size)
    if self.output == 0:
      self.conf_state = conf_state.initialized
      self.write('AD\r')              # ASCII dump
    else: # TODO: try to figure out how to get radiometer into 0 (no) error state
      #self.conf_state = conf_state.error
      #self.message = 'radiometer returned error status, ST, %d' % int(self.output)
      self.conf_state = conf_state.initialized
      self.write('AD\r')              # ASCII dump

  def read_data(self):
    energies = []
    for i in re.split(r'\s+',self.read(self.buffer_size)):
      try: # only return the numbers from the radiometer output
        energies.append(float(i))
        #energy = float(i)
        #if energy == 0:
        #  energies.append(energy)
      except:
        pass
    data_dict = {'timestamp':datetime.utcnow(),'energies':energies}
    return data_dict

class Shutter:
  '''shutter module'''

  def __init__(self):
    self.name = 'shutter'                    # radiometer module name
    self.power_state = power_state.undefined # power state: undefined,on,off
    self.RPC_outlet = 3                      # RPC outlet number
    self.power_on_sleep = 10                 # time to wait after power on
    self.power_off_sleep = 10                # time to wait after power off
    self.RPC_output = ''                     # RPC output
    self.message = ''                        # state message

class Laser:
  '''laser module'''

  def __init__(self):
    self.name = 'laser'                      # radiometer module name
    self.power_state = power_state.undefined # power state: undefined,on,off
    self.RPC_outlet = 2                      # RPC outlet number
    self.power_on_sleep = 2                  # time to wait after power on
    self.power_off_sleep = 0                 # time to wait after power off
    self.RPC_output = ''                     # RPC output
    self.message = ''                        # state message

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

phase = Enum('init run final')
# hardware states
power_state = Enum('undefined on off')
conf_state = Enum('undefined initialized finalized error')

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
    pass

  def init_PTH(self):
    print 'initializing PTH board ...'
    self.pth = PTH()                       # init PTH board
    self.check_init_state(module=self.pth) # check PTH init state

  def on_rain(self):
    print 'powering on rain monitor ...'
    self.rain = Rain()
    self.pth.on_rain(module=self.rain)    # power on rain monitor module
    self.check_on_state(module=self.rain) # check rain monitor power state

  def off_rain(self):
    print 'powering off rain monitor ...'
    self.pth.off_rain(module=self.rain)    # power off rain monitor module
    self.check_off_state(module=self.rain) # check rain monitor init state

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

  def check_init_state(self,module=None):
    if module.conf_state == conf_state.initialized:
      print 'done'
    elif module.conf_state == conf_state.undefined or module.conf_state == conf_state.finalized:
      print 'failed\n%s\n' % module.message
      self.emergency_shutdown(phase=phase.init)
    elif module.conf_state == conf_state.error:
      print 'error\n%s\n' % module.message
      self.emergency_shutdown(phase=phase.init)

  def check_final_state(self,module=None):
    if module.conf_state == conf_state.finalized:
      print 'done'
    elif module.conf_state == conf_state.undefined or module.conf_state == conf_state.initialized:
      print 'failed\n%s\n' % module.message
      self.emergency_shutdown(phase=phase.final)
    elif module.conf_state == conf_state.error:
      print 'error\n%s\n' % module.message
      self.emergency_shutdown(phase=phase.final)

  def check_on_state(self,module=None):
    if module.power_state == power_state.on:
      print 'done'
    elif module.power_state == power_state.undefined or module.power_state == power_state.off:
      print 'failed\n%s\n' % module.message
      self.emergency_shutdown(phase=phase.init)

  def check_off_state(self,module=None):
    if module.power_state == power_state.off:
      print 'done'
    elif module.power_state == power_state.undefined or module.power_state == power_state.on:
      print 'failed\n%s\n' % module.message
      self.emergency_shutdown(phase=phase.final)

  def emergency_shutdown(self,phase_state=None):
    print 'shutting down 5kmlas'
    if phase_state == phase.init:
      print 'shutting down from init phase'
      # check what modules are already inited and shut them down in reverse order
    if phase_state == phase.final:
      print 'shutting down from final phase'
      # try to save the data and get the system shutdown safely
      # perhaps set a flag on the SBC to not run again if there is a problem

def main():
  '''
  Interface with the control module
  '''

  control = Control() # control module

  # init phase
  control.data = Data()     # init data structure
  control.init_PTH()        # init PTH board
  control.on_rain()         # power on rain monitor
  control.on_heater()       # power on window heater
  control.on_inverter()     # power on inverter
  control.init_RPC()        # init RPC
  control.on_radiometer()   # power on radiometer
  control.init_radiometer() # init radiometer
  control.on_shutter()      # power on shutter

  # run phase
  print 'collecting data ...'
  five_minutes = timedelta(seconds=10)
  now = start_time = datetime.utcnow()     # record laser on time
  control.on_laser()                       # power on laser
  while (now < start_time + five_minutes): # run for 5 minutes
    control.data.append(pth_datum=control.pth.poll_data())
    sleep(5)                               # collect PTH data about every 5 seconds
    now = datetime.utcnow()
  control.off_laser()                      # power off laser
  stop_time = datetime.utcnow()            # record laser off time
  print 'done'

  # final phase
  control.off_shutter()    # close shutter
  control.data.append(radiometer_datum=control.radiometer.read_data(),
      start=start_time,
      stop=stop_time)
  print 'writing data ...'
  control.data.write()     # format and save data
  print 'done'
  control.off_radiometer() # power off radiometer
  control.off_inverter()   # power off inverter
  control.off_heater()     # power off window heater
  control.off_rain()       # power off rain monitor
  print control.data.radiometer
  print control.data.pth
  print control.data.times

if __name__ == '__main__' : main()
