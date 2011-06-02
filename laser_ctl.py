#!/usr/bin/env python
# laser_ctl.py
# Wed Feb 16 16:05:00 MST 2011
# findlay@cosmic.utah.edu

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
    print 'writing data'
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
    print 'initializing PTH board'
    self.buffer_size = 65536                 # = 2**2**2**2 : termios read buffer size
    self.name = 'pressure, temperature, and humidity module' # PTH module name
    self.message = ''                        # error message
    super(Serial,self).__init__('/dev/tts/0',baudrate=9600,timeout=0.5)
    self.power_state = power_state.on        # module power state: undefined,on,off
    self.write('RMON 1\r\n')                 # enable rain monitoring
    self.check_switch_state(self.read(self.buffer_size)) # check that rmon got enabled
    self.write('ECHO 0\r\n')                 # disable PTH-side serial echo
    self.read(self.buffer_size)              # clear output buffer
    self.conf_state = conf_state.initialized # module conf state: undefined,initialized,finalized

  def on(self,module=None): # closes a PTH switch and waits for the associated module to stabilize
    print module.on_message,
    if module.power_on_sleep > 0 : print ' ... ',
    self.write('OUT %s 1\r\n' % module.PTH_switch) # close PTH switch for module
    module.message = self.read(self.buffer_size)   # capture module state
    sleep(module.power_on_sleep)                   # wait for module to stabilize
    if module.power_on_sleep > 0 : print 'done'
    else : print

  def off(self,module=None): # opens a PTH switch
    print '%s' % module.off_message
    self.write('OUT %s 0\r\n' % module.PTH_switch) # open PTH switch for module
    self.read(self.buffer_size)                    # clear PTH output buffer

  def poll_data(self):
    self.read(self.buffer_size) # clear output buffer
    self.write('PRESS\r\n')  ; press = self.read(self.buffer_size)
    self.write('TEMP\r\n')   ; temp = self.read(self.buffer_size)
    self.write('HUMID\r\n')  ; humid = self.read(self.buffer_size)
    self.write('SUPPLY\r\n') ; supply = self.read(self.buffer_size)
    data_dict = {}
    for i in press,temp,humid,supply:
      # typical datum = ['PRESS','867.3']
      datum = re.split(r'\s+',i)[:-1]
      data_dict[datum[0]] = float(datum[1])
    data_dict['timestamp'] = datetime.utcnow()
    return data_dict

  def check_switch_state(self,module):
    self.message = ''
    self.conf_state
    return re.search(r'^(.*on 1.*)$',output,state).group(1)

class Heater:
  '''heater module'''

  def __init__(self):
    self.name = 'window heater'              # heater module name
    self.power_state = power_state.undefined # module power state: undefined,on,off
    self.PTH_switch = 'B'                    # PTH board switch that controls heater
    self.power_on_sleep = 30                 # time to stabilize after power on
    self.on_message = 'warming up heater'    # on message
    self.off_message = 'powering off heater' # off message
    self.message = ''                        # error message

class Inverter:
  '''inverter module'''

  def __init__(self):
    self.name = 'power inverter'               # inverter module name
    self.power_state = power_state.undefined   # module power state: undefined,on,off
    self.PTH_switch = 'A'                      # PTH board switch name
    self.power_on_sleep = 0                    # time to stabilize after power on
    self.on_message = 'powering on inverter'   # on message
    self.off_message = 'powering off inverter' # off message
    self.message = ''                          # error message

class RPC:
  '''
  RPC module

  put typical RPC output here
  '''

  def __init__(self):
    self.buffer_size = 16 # = 2**2**2 : termios read buffer size
    print 'initializing RPC'
    super(Serial,self).__init__('/dev/tts/1',baudrate=9600,timeout=0.5)

  def on(self,module=None): # powers on a RPC outlet and waits for the associated module to stabilize
    print module.on_message,
    if module.power_on_sleep > 0 : print ' ... ',
    self.write('on %d\r\n' % module.RPC_switch)          # power on module RPC port
    self.write('Y\r\n')                                  # confirm power on
    self.check_state(self.read(self.buffer_size),module) # check powered on
    sleep(module.power_on_sleep)                         # wait for module to stabilize
    if module.power_on_sleep > 0 : print 'done'
    else : print

  def off(self,module=None): # powers off a RPC outlet and waits for the associated module to stabilize
    print module.off_message,
    if module.power_off_sleep > 0 : print ' ... ',
    self.write('off %d\r\n' % module.RPC_switch)         # power on module RPC port
    self.write('Y\r\n')                                  # confirm power off
    self.check_state(self.read(self.buffer_size),module) # check powered off
    sleep(module.power_off_sleep)                        # wait for module to stabilize
    if module.power_on_sleep > 0 : print 'done'
    else : print

  def check_power_state(self,module):
    return re.search(r'^(.*on 1.*)$',output,state).group(1)

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

  # due to the software paradigm I'm using, I cannot combine the creation of
  # the radiometer object with the initalizaion of the radiometer module
  def __init__(self): # software init
    self.name = 'radiometer'                     # radiometer module name
    self.power_state = power_state.undefined     # power state: undefined,on,off
    self.conf_state = conf_state.undefined       # configuration state: undefined,initialized,finalized
    self.RPC_switch = 1                          # RPC switch name
    self.power_on_sleep = 0                      # time to wait after power on
    self.power_off_sleep = 0                     # time to wait after power off
    self.on_message = 'powering on radiometer'   # on message
    self.off_message = 'powering off radiometer' # off message
    self.message = ''                                  # error message

  def init(self): # hardware init
    print 'initializing radiometer'
    self.buffer_size = 2**16
    self.stop_time = self.start_time = datetime.utcnow()
    super(Serial,self).__init__('/dev/tts/2',baudrate=9600,timeout=5)
    # the radiometer needs a timeout buffer between consecutive commands
    sleep(0.5) ; self.write('TG 1\r') # internal trigger
    sleep(0.5) ; self.write('SS 0\r') # no single shot
    sleep(0.5) ; self.write('RA 2\r') # range 2
    sleep(0.5) ; self.write('BS 0\r') # disable internal battery save
    sleep(0.5) ; self.write('AD\r')   # ASCII dump
    self.flushInput()
    #self.flushOutput() - doesn't work when run from SBC
    self.read(self.buffer_size) # clear output buffer

  def read_data(self):
    print 'reading radiometer data'
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
    self.RPC_switch = 1                      # RPC switch name
    self.power_on_sleep = 10                 # time to wait after power on
    self.power_off_sleep = 10                # time to wait after power off
    self.on_message = 'opening shutter'      # on message
    self.off_message = 'closing shutter'     # off message
    self.message = ''                              # error message

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

# hardware states
conf_state = Enum('undefined initialized finalized')
power_state = Enum('undefined on off')
phase_state = Enum('init final')

class Control:
  '''
  software control module for 5kmlas apparatus

  This control module wraps each function call to the other modules in order to
  simplify and unify error traps.  Each call sets one or more associated states
  in the module.  The control module will take action upon each setting of
  state: either proceed normally or try to return the hardware and software to
  a well-defined and safe state.

  This scheme assumes at least two things:
  - The python code and the operating system it runs on are either so much more
    reliable in comparison with the hardware that they aren't worth checking or
    they will provide their own error handling when necessary.
  - The firmware on the hardware is so much more reliable than the hardware
    itself that all problems will originate with a hardware failure or
    misconfiguration and that the firmware will report it.

  The control process has three phases: init, run, and final.  Depending on the
  phase, the control module may fail in a different manner.
  '''
  def __init__(self):

  def init(self):
    self.data = Data()     # init data structure
    self.init_PTH()        # init PTH board
    self.init_heater()     # init window heater
    self.init_inverter()   # init inverter
    self.init_RPC()        # init RPC
    self.init_radiometer() # init radiometer
    self.init_shutter()    # init shutter

  def run(self):
    print 'collecting data ... ',
    five_minutes = timedelta(seconds=10)
    now = self.start_time = datetime.utcnow()     # record laser on time
    self.init_laser()                             # power on laser
    while (now <= start_time + five_minutes):     # run for 5 minutes
      self.data.append(pth_datum=pth.poll_data()) # collect PTH data about every 5 seconds
      sleep(5)
      now = datetime.utcnow()
    self.final_laser()                            # power off laser
    self.stop_time = datetime.utcnow()            # record laser off time
    print 'done'

  def final(self):
    self.final_shutter()    # close shutter
    self.data.append(radiometer_datum=radiometer.read_data(),
        start=self.start_time,
        stop=self.stop_time)
    self.data.write()       # format and save data
    self.final_radiometer() # power off radiometer
    self.final_inverter()   # power off inverter
    self.final_heater()     # power off window heater

  def init_PTH(self):
    self.pth = PTH()                       # init PTH board
    self.check_init_state(module=self.pth) # check PTH init state

  def init_heater(self):
    self.heater = Heater()                  # create heater object
    self.pth.on(module=self.heater)         # power on heater module
    self.check_on_state(module=self.heater) # check heater power state

  def final_heater(self):
    self.pth.off(module=self.heater)         # power off heater module
    self.check_off_state(module=self.heater) # check heater power state

  def init_inverter(self):
    self.inverter = Inverter()                # create inverter object
    self.pth.on(module=self.inverter)         # power on inverter module
    self.check_on_state(module=self.inverter) # check inverter power state

  def final_inverter(self):
    self.pth.off(module=self.inverter)         # power off inverter module
    self.check_off_state(module=self.inverter) # check inverter power state

  def init_RPC(self):
    self.rpc = RPC()                       # init RPC module
    self.check_init_state(module=self.rpc) # check RPC init state

  def init_radiometer(self):
    self.radiometer = Radiometer()                # create radiometer object
    self.rpc.on(module=self.radiometer)           # power on radiometer module
    self.check_on_state(module=self.radiometer)   # check radiometer power state
    self.radiometer.init()                        # init radiometer module
    self.check_init_state(module=self.radiometer) # check radiometer conf state

  def final_radiometer(self):
    self.rpc.off(module=self.radiometer)           # power off radiometer module
    self.check_off_state(module=self.radiometer)   # check radiometer power state

  def init_shutter(self):
    self.shutter = Shutter()                 # create shutter object
    self.rpc.on(module=self.shutter)         # power on shutter module
    self.check_on_state(module=self.shutter) # check shutter power state

  def final_shutter(self):
    self.rpc.off(module=self.shutter)         # power off shutter module
    self.check_off_state(module=self.shutter) # check shutter power state

  def init_laser(self):
    self.laser = Laser()                   # create laser object
    self.rpc.on(module=self.laser)         # power on laser module
    self.check_on_state(module=self.laser) # check laser power state

  def final_laser(self):
    self.rpc.off(module=self.laser)         # power off laser
    self.check_off_state(module=self.laser) # check laser power state

  def check_init_state(self,module=None):
    if module.conf_state == conf_state.initialized:
      pass
    elif module.conf_state == conf_state.undefined or module.conf_state == conf_state.finalized:
      print '\n%s failed to initialize: %s' % (module.name,module.failure_message)
      self.emergency_shutdown(phase=phase.init)

  def check_final_state(self,module=None):
    if module.conf_state == conf_state.finalized:
      pass
    elif module.conf_state == conf_state.undefined or module.conf_state == conf_state.initialized:
      print '\n%s failed to %s: %s' % (kwargs['module'],kwargs['finalize action'],kwargs['message'])
      self.emergency_shutdown(phase=phase.final)

  def check_on_state(self,module=None):
    if module.power_state == power_state.on:
      pass
    elif module.power_state == power_state.undefined or module.power_state == power_state.off:
      print '\n%s failed to power on: %s' % (kwargs['module'],kwargs['message'])
      self.emergency_shutdown(phase=phase.init)

  def check_off_state(self,module=None):
    if module.power_state == power_state.off:
      pass
    elif module.power_state == power_state.undefined or module.power_state == power_state.on:
      print '\n%s failed to power off: %s' % (kwargs['module'],kwargs['message'])
      self.emergency_shutdown(phase=phase.final)

  def emergency_shutdown(self,phase=None):
    print 'shutting down 5kmlas'
    if phase == phase_state.init:
      print 'shutting down from init phase'
      # check what modules are already inited and shut them down in reverse order
    if phase == phase_state.final:
      print 'shutting down from final phase'
      # try to save the data and get the system shutdown safely
      # perhaps set a flag on the SBC to not run again if there is a problem

def main():
  control = Control()
  control.init()
  control.run()
  control.final()

if __name__ == '__main__' : main()
