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
    self.radiometer = {}
    self.PTH = {}
    self.inverter = {}

class PTH:
  def __init__(self):
    pass

  def heater_on(self):
    pass

  def radiometer_on(self):
    pass

  def open_shutter(self):
    pass

  def poll_data(self):
    pass

class Inverter:
  def __init__(self):
    pass

  def power_on(self):
    pass

  def power_off(self):
    pass

  def poll_data(self):
    pass

class Heater:
  pass

class Shutter:
  pass

class Radiometer(Serial):
  def __init__(self):
    self.buffer_size = 2**16
    super(Serial,self).__init__('/dev/ttyUSB0',baudrate=9600,timeout=1)
    sleep(0.5) ; self.write('TG 1\r') # internal trigger
    sleep(0.5) ; self.write('SS 0\r') # no single shot
    sleep(0.5) ; self.write('RA 2\r') # range 2
    sleep(0.5) ; self.write('BS 0\r') # disable internal battery save
    sleep(0.5) ; self.write('AD\r')   # ASCII dump
    self.flushInput()
    self.flushOutput()
    self.read(self.buffer_size) # clear output buffer again?

  def read_data(self):
    energies = []
    for i in re.split(r'\s+',self.read(self.buffer_size)):
      try: # only collect the numbers from the radiometer output
        energies.append(float(i))
      except:
        pass
    return energies

class Laser:
  pass

def main():
  ## init data
  #data = Data()

  ## init PTH,radiometer
  #pth = PTH()
  #inverter = Inverter()

  ## power on heater
  #pth.heater_on()
  # wait for it to stabilize for 30s?

  ## power on radiometer
  #inverter.power_on()
  #pth.radiometer_on()

  # init radiometer
  print 'initializing radiometer'
  radiometer = Radiometer()

  ## open shutter
  #pth.open_shutter()

  ## power on laser
  #pth.laser_on()

  # run for 3 min
  now = start_time = datetime.utcnow()
  three_minutes = timedelta(seconds=5)
  print 'now collecting data'
  while (now <= start_time + three_minutes):
    # poll environment and electronic data about once a second
    #sleep(1)
    #data.append(pth.poll_data())
    #data.append(inverter.poll_data())
    now = datetime.utcnow()

  ## power off laser
  #inverter.power_off()
  #data.append(radiometer.read_data())

  # gather radiometer data.  The radiometer will wait to return until after it stops detecting data for ~ 1s, so we have to power off the laser first.
  print radiometer.read_data()
  #data.append(radiometer.read_data())

  ## close shutter
  #pth.close_shutter()

  ## power off radiometer
  #pth.radiometer_off()

  ## power off heater
  #pth.heater_off()

  ## write data
  #data.write()

if __name__ == "__main__" : main()
