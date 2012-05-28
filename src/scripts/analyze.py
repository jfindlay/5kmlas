#!/usr/bin/env python

import os,sys,datetime,gzip
from subprocess import Popen,PIPE
from datetime import timedelta,tzinfo,time
from pprint import pprint,saferepr,isreadable

class UTC(tzinfo):
  def __init__(self) : super(UTC,self).__init__()
  def __str__(self) : return 'UTC'
  def __repr__(self) : return 'UTC()'
  def tzname(self,dt) : return self.__str__()
  def utcoffset(self,dt) : return timedelta(0)
  def dst(self,dt) : return timedelta(0)

class Gnuplot:
  def __init__(self):
    self.term = 'wxt'
    self.canvas_size = (900,500)
    self.time_format = '%Y-%m-%dT%H:%M:%S'
    self.axis_time_format = '%m-%d\\n%H:%M'
    self.f_name = '/tmp/pygnuplot' # send data to gnuplot using this file
    self.gp = Popen(('gnuplot',),stdout=PIPE,stdin=PIPE,close_fds=True)
    self.stdin,self.stdout = self.gp.stdin,self.gp.stdout
    self.stdin.write('set isosamples 128\n')
    self.stdin.write('set key top left\n')

  def set_term(self,t=None,x=None,y=None):
    if t : term = t
    else : term = self.term
    if x : width = x
    else : width = self.canvas_size[0]
    if y : height = y
    else : height = self.canvas_size[1]
    self.stdin.write('set term %s size %d,%d\n' % (term,width,height))

  def set_time_format(self,fmt=None):
    if fmt : time_format = fmt
    else : time_format = self.time_format
    self.stdin.write('set timefmt "%s"\n' % time_format)

  def write_file(self,*args):
    self.f = open(self.f_name,'w')
    for row in xrange(len(args[0])):
      line = ''
      for arg in args:
        line += ' %s' % arg[row]
      self.f.write('%s\n' % line.lstrip())
    self.f.close()

  def plot_file(self,a=None):
    if a : args = a
    else : args = ''
    self.stdin.write('plot "%s" %s\n' % (self.f_name,args))

store_dir = 'store'

def read_data():
  d = {}
  for f_name in sorted(os.listdir(store_dir)):
    if os.path.isfile(os.path.join(store_dir,f_name)):
      for line in gzip.open(os.path.join(store_dir,f_name),'r'):
        if isreadable(line):
          datum = eval(line)
          t = datum['type']
          if t not in d.keys():
            d[t] = []
          d[t].append(datum)
  return d

def nums(a):
  return [i for i in xrange(len(a))]

def datums(d,measure,add_adj=0,mult_adj=1):
  return [float(i[measure][0])*mult_adj + add_adj for i in d]

def timestamps(d,fmt):
  return [i['timestamp'].strftime(fmt) for i in d]

def main():
  full_data = read_data()
  pprint(full_data['charger'][0]) ; raw_input()
  g = Gnuplot()
  g.set_term()
  g.stdin.write('set grid\n')
  g.set_time_format()
  g.stdin.write('set xdata time\n')
  g.stdin.write('set format x "%s"\n' % g.axis_time_format)
  # PTH SUPPLY, charger slow batt volts
  x = timestamps(full_data['PTH'],g.time_format)
  y_1 = datums(full_data['PTH'],'SUPPLY')
  y_2 = datums(full_data['charger'],'slow battery volts')
  g.write_file(x,y_1,y_2)
  g.stdin.write('set xlabel "UTC"\n')
  g.stdin.write('set ylabel "electric potential [V]"\n')
  g.stdin.write('plot "%s" using 1:2 with line t "PTH SUPPLY volts", "%s" using 1:3 with line t "slow batt volts"\n' % ((g.f_name,)*2)) ; raw_input()
  # charger load current, charging current
  x = timestamps(full_data['charger'],g.time_format)
  y_1 = datums(full_data['charger'],'load current')
  y_2 = datums(full_data['charger'],'charging current')
  g.write_file(x,y_1,y_2)
  g.stdin.write('set xlabel "UTC"\n')
  g.stdin.write('set ylabel "electric current [I]"\n')
  g.stdin.write('plot "%s" using 1:2 with line t "load current", "%s" using 1:3 with line t "charging current"\n' % ((g.f_name,)*2)) ; raw_input()
  # charger ambient, heatsink temp, PTH temp
  x = timestamps(full_data['charger'],g.time_format)
  y_1 = datums(full_data['charger'],'heatsink temp',273.15)
  y_2 = datums(full_data['charger'],'ambient temp',273.15)
  y_3 = datums(full_data['PTH'],'TEMP')
  g.write_file(x,y_1,y_2,y_3)
  g.stdin.write('set xlabel "UTC"\n')
  g.stdin.write('set ylabel "temperature [K]"\n')
  g.stdin.write('plot "%s" using 1:2 with line t "heatsink temp", "%s" using 1:3 with line t "ambient temp", "%s" using 1:4 with line t "PTH TEMP"\n' % ((g.f_name,)*3)) ; raw_input()

if __name__ == '__main__':
  try:
    main()
  except KeyboardInterrupt:
    sys.exit(0)
