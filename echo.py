#!/usr/bin/env python

import socket,os,sys
from time import sleep

class Socket(socket.socket):
  def __init__(self,side=None):
    super(Socket,self).__init__(socket.AF_UNIX,socket.SOCK_STREAM)
    self.buffer_size = 65536
    self.name = '/tmp/5kmlas_socket'
    self.side = side
    if self.side == 'server':
      self.remove()
      self.bind(self.name)
      self.listen(1)
      self.settimeout(0.0)
    elif self.side == 'client':
      self.connect(self.name)

  def __del__(self):
    self.remove()

  def remove(self):
    if self.side == 'server':
      if os.path.lexists(self.name):
        os.remove(self.name)

  def close(self):
    if self.side == 'server':
      self.conn.close()
    elif self.side == 'client':
      super(Socket,self).close()

  def accept(self):
    if self.side == 'server':
      try:
        self.conn,self.addr = super(Socket,self).accept()
        return True
      except socket.error:
        return False

  def read(self):
    if self.side == 'server':
      return self.conn.recv(self.buffer_size)
    elif self.side == 'client':
      return self.recv(self.buffer_size)

  def write(self,data):
    if self.side == 'server':
      return self.conn.send(data)
    elif self.side == 'client':
      return self.send(data)

def server():
  socket = Socket(side='server')
  while True:
    if socket.accept():
      data = socket.read()
      socket.write(data)
    else:
      sleep(1)
      continue
  socket.close()

def client():
  socket = Socket(side='client')
  socket.send('Hello, World')
  print socket.read()
  socket.close()

def main():
  if sys.argv[1] == 'server':
    server()
  elif sys.argv[1] == 'client':
    client()

if __name__ == '__main__' : main()
