class Proc:
  def __init__(self, code):
    self.code = code
  def call(self, *args):
    exec self.code in dict(zip(self.code.co_varnames, args))

def proc(func):
  return Proc(func)

def puts(*args):
  for x in args: print x
  if not args: print

class BasicObject:
  pass
