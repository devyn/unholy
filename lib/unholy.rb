require 'unholy/tuple'
require 'unholy/pickle'
require 'unholy/pyasm'

def unholy(fname, fpyc)
  asm = Pyasm.new(fname)
  asm.import :Kernel
  asm.eval IO.read(fname)
  asm.compile(fpyc)
end
