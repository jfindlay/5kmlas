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
    self.inverter = []

  def append(self,*args,**kwargs):
    if 'radiometer_datum' in kwargs:
      self.radiometer.append(kwargs['radiometer_datum'])
    if 'pth_datum' in kwargs:
      self.pth.append(kwargs['pth_datum'])
    if 'inverter_datum' in kwargs:
      self.inverter.append(kwargs['inverter_datum'])
  def write(self):
    print 'writing data'
    # load objects from DST.py and write data structure into DST file
    # the format of the DST file will be a heterogeneous stream with one part per UTC day

class PTH(Serial):
  '''
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
     VER                     - read device firmware version'''

  def __init__(self):
    print 'initializing PTH board'
    self.buffer_size = 2**16
    super(Serial,self).__init__('/dev/ttyAM1',baudrate=9600,timeout=0.5)
    self.write('ECHO 0\r\n')
    self.read(self.buffer_size) # clear output buffer

  def heater_on(self):
    print 'turning on heater'

  def heater_off(self):
    print 'turning off heater'

  def laser_on(self):
    print 'turning on laser'

  def laser_off(self):
    print 'turning off laser'

  def open_shutter(self):
    print 'opening shutter'

  def close_shutter(self):
    print 'closing shutter'

  def poll_data(self):
    self.read(self.buffer_size) # clear output buffer
    self.write('PRESS\r\n')
    press = self.read(self.buffer_size)
    self.write('TEMP\r\n')
    temp = self.read(self.buffer_size)
    self.write('HUMID\r\n')
    humid = self.read(self.buffer_size)
    self.write('SUPPLY\r\n')
    supply = self.read(self.buffer_size)
    data_dict = {}
    for i in press,temp,humid,supply:
      # typical datum = ['PRESS','867.3']
      datum = re.split(r'\s+',i)[:-1]
      data_dict[datum[0]] = float(datum[1])
    data_dict['timestamp'] = datetime.utcnow()
    return data_dict

class Inverter:
  def __init__(self):
    print 'initializing inverter'

  def power_on(self):
    print 'powering on inverter'

  def power_off(self):
    print 'powering off inverter'

  def poll_data(self):
    pass

class Heater:
  pass

class Shutter:
  pass

class Radiometer(Serial):
  '''
     Auger CLF radiometer (RM-3700) settings from lwiencke
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
     AD       ASCII Dump Mode'''

  def __init__(self):
    print 'initializing radiometer'
    self.buffer_size = 2**16
    self.stop_time = self.start_time = datetime.utcnow()
    super(Serial,self).__init__('/dev/ttyTS0',baudrate=9600,timeout=5)
    sleep(0.5) ; self.write('TG 1\r') # internal trigger
    sleep(0.5) ; self.write('SS 0\r') # no single shot
    sleep(0.5) ; self.write('RA 2\r') # range 2
    sleep(0.5) ; self.write('BS 0\r') # disable internal battery save
    sleep(0.5) ; self.write('AD\r')   # ASCII dump
    self.flushInput()
    #self.flushOutput() - doesn't work when run from SBC
    self.read(self.buffer_size) # clear output buffer

  def start(self):
    self.start_time = datetime.utcnow()

  def stop(self):
    self.stop_time = datetime.utcnow()

  def read_data(self):
    print 'reading radiometer data'
    energies = []
    for i in re.split(r'\s+',self.read(self.buffer_size)):
      try: # only return the numbers from the radiometer output
        energies.append(float(i))
      except:
        pass
    data_dict = {'timestamp':datetime.utcnow(),'energies':energies}
    return data_dict

class Laser:
  pass

def main():
  data = Data()
  pth = PTH()
  inverter = Inverter()

  pth.heater_on() # wait for it to stabilize for 30s?
  inverter.power_on()
  radiometer = Radiometer()
  pth.open_shutter()
  pth.laser_on()

  print 'collecting data'
  radiometer.start()
  now = start_time = datetime.utcnow()
  five_minutes = timedelta(seconds=10)
  while (now <= start_time + five_minutes):
    sleep(5)
    data.append(pth_datum=pth.poll_data(),inverter_datum=inverter.poll_data())
    now = datetime.utcnow()
  radiometer.stop()
  print 'done'

  pth.laser_off()
  pth.close_shutter()
  data.append(radiometer_datum=radiometer.read_data())
  data.write()
  inverter.power_off()
  pth.heater_off()
  print data.pth,data.radiometer

if __name__ == "__main__" : main()
