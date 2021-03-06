#!/usr/bin/env python

import os,sys,datetime,gzip
from math import fsum
from argparse import ArgumentParser
from subprocess import Popen,PIPE
from time import sleep
from datetime import timedelta,tzinfo,time
from pprint import isreadable

# utils ########################################################################

# ISO-8601 datetime format
ISO_8601 = '%Y-%m-%dT%H:%M:%S'

def nums(a):
  return [i for i in xrange(len(a))]

def datums(d,measure,func='%f'):
  return [float(func % float(i[measure][0])) for i in d]

def dtdatums(d,measure,dtfmt=ISO_8601,func='%f'):
  '''returns timestamp for each measurement'''
  t_list,m_list = [],[]
  for i in d:
    t_list.append(i['timestamp'].strftime(dtfmt))
    m_list.append(float(eval(func % float(i[measure][0]))))
  return t_list,m_list

def dtenergies(d,dtfmt=ISO_8601):
  '''returns timestamp for each energy list'''
  t_list,m_list = [],[]
  for i in d:
    t_list.append(i['timestamp'].strftime(dtfmt))
    m_list.append(i['energies'][0])
  return t_list,m_list

def timestamps(d,fmt=ISO_8601):
  return [i['timestamp'].strftime(fmt) for i in d]

def read_data(data_path):
  d = {}
  i = 0
  for f_name in sorted(os.listdir(data_path)):
    print f_name
    i += 1
    if os.path.isfile(os.path.join(data_path,f_name)):
      for line in gzip.open(os.path.join(data_path,f_name),'r'):
        if isreadable(line):
          datum = eval(line)
          t = datum['type']
          if t not in d.keys():
            d[t] = []
          d[t].append(datum)
    if i == 7 : break
  return d

class UTC(tzinfo):
  '''identity timezone'''
  def __init__(self) : super(UTC,self).__init__()
  def __str__(self) : return 'UTC'
  def __repr__(self) : return 'UTC()'
  def tzname(self,dt) : return self.__str__()
  def utcoffset(self,dt) : return timedelta(0)
  def dst(self,dt) : return timedelta(0)

# gnuplot ######################################################################

class Gnuplot:
  def __init__(self):
    self.term = 'wxt'
    self.canvas_size = (1024,600)
    self.time_format = ISO_8601
    self.axis_time_format = '%m-%d\\n%H:%M'
    self.files = {}  # dictionary of files used to store data for plots
    self.f_sep = '|' # data file field separator
    self.history = open('/tmp/gp_history','w')
    self.gp = Popen(('gnuplot',),stdout=PIPE,stdin=PIPE,close_fds=True)
    self.stdin,self.stdout = self.gp.stdin,self.gp.stdout
    self.write('set samples 128\n')
    self.write('set isosamples 128\n')
    self.write('set key top left\n')
    self.set_datafile_separator()
    self.set_term()

  def __del__(self):
    self.gp.stdin.close()
    self.gp.stdout.close()
    self.history.close()
    for f_name in self.files.keys():
      if not self.files[f_name].closed:
        self.files[f_name].close()
      #if os.path.exists(f_name):
#        os.remove(f_name)

  def write(self,a):
    self.history.write(a)
    self.stdin.write(a)

  def set_datafile_separator(self,f_sep=None):
    if f_sep : s = f_sep
    else : s = self.f_sep
    self.set('datafile separator "%s"' % s)

  def set_term(self,term=None,width=None,height=None):
    if term : t = term
    else : t = self.term
    if width : x = width
    else : x = self.canvas_size[0]
    if height : y = height
    else : y = self.canvas_size[1]
    self.set('term %s size %d,%d' % (t,x,y))

  def set_time_format(self,fmt=None):
    if fmt : f = fmt
    else : f = self.time_format
    self.set('timefmt "%s"' % f)

  def set(self,a=None):
    if a:
      self.write('set %s\n' % a)

  def write_file(self,f_name,*args):
    '''
    Write data to temp file used to construct gnuplot plots.  All args supplied
    must be 1D iterables of the same size.
    '''
    self.files[f_name] = open(f_name,'w')
    for row in xrange(len(args[0])):
      line = ''
      for arg in args:
        if not isinstance(arg[row],str):
          m = '%f' % arg[row]
        else:
          m = arg[row]
        if len(line):
          line += self.f_sep
        line += m
      self.files[f_name].write('%s\n' % line)
    self.files[f_name].close()

  def plot(self,a=None):
    self.write('plot %s\n' % a)
    sleep(0.1) # gnuplot file writes are nonblocking

# plots ########################################################################

def volts(g,data,plot_path):
  '''PTH SUPPLY, slow batt volts, array volts'''
  g.set('output "%s"' % os.path.join(plot_path,'volts.png'))
  g.write_file('/tmp/1',*dtdatums(data['PTH'],'SUPPLY'))
  g.write_file('/tmp/2',*dtdatums(data['charger'],'slow battery volts'))
  g.write_file('/tmp/3',*dtdatums(data['charger'],'array volts'))
  g.set('xlabel "UTC"')
  g.set('ylabel "electric potential [V]"')
  g.plot('"/tmp/1" using 1:2 with dots t "PTH SUPPLY volts", "/tmp/2" using 1:2 with dots t "slow batt volts", "/tmp/3" using 1:2 with dots t "solar array volts"')

def currents(g,data,plot_path):
  '''charger load current, charging current'''
  g.set('output "%s"' % os.path.join(plot_path,'currents.png'))
  g.write_file('/tmp/1',*dtdatums(data['charger'],'load current'))
  g.write_file('/tmp/2',*dtdatums(data['charger'],'charging current'))
  g.set('xlabel "UTC"')
  g.set('ylabel "electric current [I]"')
  g.plot('"/tmp/1" using 1:2 with dots t "load current", "/tmp/2" using 1:2 with dots t "charging current"')

def charge(g,data,plot_path):
  '''battery charge'''
  g.set('output "%s"' % os.path.join(plot_path,'charge.png'))
  g.write_file('/tmp/1',*dtdatums(data['charger'],'Ah total charge'))
  g.set('xlabel "UTC"')
  g.set('ylabel "electric energy [A*h]"')
  g.plot('"/tmp/1" using 1:2 with dots t "battery charge"')

def temps(g,data,plot_path):
  '''charger ambient, heatsink temp, PTH temp'''
  g.set('output "%s"' % os.path.join(plot_path,'temps.png'))
  g.write_file('/tmp/1',*dtdatums(data['charger'],'heatsink temp',func='%f + 273.15'))
  g.write_file('/tmp/2',*dtdatums(data['charger'],'ambient temp',func='%f + 273.15'))
  g.write_file('/tmp/3',*dtdatums(data['PTH'],'TEMP'))
  g.set('xlabel "UTC"')
  g.set('ylabel "temperature [K]"')
  g.plot('"/tmp/1" using 1:2 with dots t "heatsink temp", "/tmp/2" using 1:2 with dots t "ambient temp", "/tmp/3" using 1:2 with dots t "PTH TEMP"')

def energies(g,data,plot_path):
  '''radiometer energy'''
  g.set('output "%s"' % os.path.join(plot_path,'energies.png'))
  (timestamps,energy_lists) = dtenergies(data['radiometer'])
  average_energies = []
  for energy_list in energy_lists:
    if len(energy_list):
      for energy in energy_list:
        if energy >= 1:
          del energy_list[energy_list.index(energy)]
      average_energies.append(fsum(energy_list)/len(energy_list))
    else:
      average_energies.append(0)
  g.write_file('/tmp/1',timestamps,average_energies)
  g.set('xlabel "UTC"')
  g.set('ylabel "energy [J]"')
  g.plot('"/tmp/1" using 1:2 with dots t "energies"')

def temp_energy(g,data,plot_path):
  '''PTH TEMP vs radiometery energy'''
  g.set('output "%s"' % os.path.join(plot_path,'temp_energy.png'))
  etimestamps,energy_lists = dtenergies(data['radiometer'])
  average_energies = []
  for energy_list in energy_lists:
    if len(energy_list):
      for energy in energy_list:
        if energy >= 1:
          del energy_list[energy_list.index(energy)]
      average_energies.append(fsum(energy_list)/len(energy_list))
    else:
      average_energies.append(0)
  energy_tuple = etimestamps,average_energies
  temp_tuple = dtdatums(data['PTH'],'TEMP')
  temps,energies = [],[]
  temp_start = 1
  for i in xrange(len(energy_tuple[0])):
    for j in xrange(temp_start,len(temp_tuple[0])): # there are many more temp measurements than energy measurements
      print temp_tuple[j][1],energy_tuple[i][1] ; raw_input()
      if temp_tuple[j][1] <= energy_tuple[i][1] and temp_tuple[j + 1][1] >= energy_tuple[i][1]:
        temps.append((temp_tuple[j][0] + temp_tuple[j + 1][0])/2.)
        energies.append(energy_tuple[i][0])
        temp_start = j
        break
  g.write_file('/tmp/1',temps,energies)
  g.set('xlabel "temperature [K]"')
  g.set('ylabel "energy [J]"')
  g.plot('"/tmp/1" using 1:2 with dots t "average energy vs temperature"')

# main #########################################################################

def parse_args():
  parser = ArgumentParser(description='Analyze 5kmlas data.')
  parser.add_argument('data_path',type=str,default='data/store',nargs='*',help='path to data location')
  parser.add_argument('plot_path',type=str,default='data/plots',nargs='*',help='path to plot location')
  return parser.parse_args()

def main():
  args = parse_args()
  data = read_data(args.data_path)
  g = Gnuplot()
  g.set_term('png')
  g.set('grid')
  g.set_time_format()
  g.set('xdata time')
  g.set('format x "%s"' % g.axis_time_format)
  #volts(g,data,args.plot_path)
  #currents(g,data,args.plot_path)
  #charge(g,data,args.plot_path)
  #temps(g,data,args.plot_path)
  #energies(g,data,args.plot_path)
  temp_energy(g,data,args.plot_path)

if __name__ == '__main__':
  try:
    main()
  except KeyboardInterrupt:
    sys.exit(0)
