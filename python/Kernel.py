class Proc:
  def __init__(self, code):
    self.code = code
  def call(self, *args):
    return eval(self.code, dict(zip(self.code.co_varnames, args)))

def proc(func):
  return Proc(func)

def puts(*args):
  for x in args: print x
  if not args: print

class BasicObject:
  pass
