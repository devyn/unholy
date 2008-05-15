class Pyasm
  CO_NEWLOCALS = 0x02
  CO_NOFREE = 0x40

  VM_CALL_FCALL_BIT = 0x08

  OPS = {
    :== => 2
  }

  attr_accessor :argc, :stacksize, :flags, :consts, :bytecode,
    :filename, :lineno, :name, :symbols, :stacknow, :varsyms, :jumps, :labels, :lines
  def initialize(fname, type = nil, name = "<module>", lineno = 0, argc = 0)
    @argc, @stacksize, @flags, @filename, @lineno, @name, @stack, @nopop, @type = 
      argc, 1, CO_NOFREE, fname, lineno, name, [], 0, type
    @flags |= CO_NEWLOCALS if [:class, :method].include?(type)
    @consts = [-1, nil]
    @symbols = [:Kernel]
    @bytecode, @varsyms, @labels, @lines, @jumps = [], [], {}, [], {}
  end

  def add_const(obj)
    @consts << obj unless @consts.include? obj
    @consts.index(obj)
  end
  def add_sym(name)
    @symbols << name unless @symbols.include? name
    @symbols.index(name)
  end
  def add_varsym(name)
    @varsyms << name unless @varsyms.include? name
    @varsyms.index(name)
  end
  def stack_push obj, b
    @stack << [obj, b]
    @stacksize = @stack.length if @stack.length > @stacksize
    b
  end
  def dump_stack
    @stack.clear
  end
  def bc *bytes
    @bytecode << bytes
    bytes
  end
  def mark_jump n, bc
    @jumps[n] ||= []
    @jumps[n] << bc
  end

  def pop_top; bc 0x01; dump_stack end
  def infix i
    add = bc i
    @stack.pop
    add
  end
  def binary_add; infix 0x17 end
  def binary_subscr; infix 0x19 end
  def inplace_add; infix 0x37 end
  def print_item; dump_stack; bc 0x47 end
  def print_newline; dump_stack; bc 0x48 end
  def load_locals; bc 0x52 end
  def ret_val; bc 0x53 end
  def build_class; bc 0x59 end
  def store_name(name)
    dump_stack
    bc 0x5a, add_sym(name), 0x0
  end
  def store_attr(name)
    dump_stack
    bc 0x5f, add_sym(name), 0x0
  end
  def load_const(obj)
    stack_push obj, bc(0x64, add_const(obj), 0x0)
  end
  def load_name(name)
    stack_push name, bc(0x65, add_sym(name), 0x0)
  end
  def build_tuple(n)
    @stack.slice! -(n-1), (n-1)
    bc(0x66, n, 0x0)
  end
  def build_list(n)
    @stack.slice! -(n-1), (n-1)
    bc(0x67, n, 0x0)
  end
  def load_attr(name)
    stack_push name, bc(0x69, add_sym(name), 0x0)
  end
  def compare_op(op)
    bc 0x6a, OPS[op], 0x0
  end
  def import_name(name)
    bc 0x6b, add_sym(name), 0x0
  end
  def import_from(name)
    bc 0x6c, add_sym(name), 0x0
  end
  def jump_if_false(n)
    mark_jump n, bc(0x6f, n, 0x0)
  end
  def load_fast(n)
    stack_push n, bc(0x7c, n, 0x0)
  end
  def store_fast(n)
    dump_stack
    bc 0x7d, n, 0x0
  end
  def call_func(arity)
    (arity + 2).times { @stack.pop }
    stack_push Object.new, bc(0x83, arity, 0x0)
  end
  def make_func(arity)
    bc 0x84, arity, 0x0
  end
  def line n
    @lines << [n, @bytecode.flatten.length]
  end
  def prep_send
    @nopop -= 1 if @nopop > 0
  end
  def label l
    @labels[l] = @bytecode.flatten.length
  end

  def import_split(mod)
    mod = mod.to_s
    return [mod[/^(.+?)(\.|$)/, 1].intern, mod.intern]
  end

  def getinlinecache ic, dst
  end
  def setinlinecache dst
  end
  def getlocal id
    load_fast id - 2
  end
  def setlocal id
    store_fast id - 2
  end
  def getdynamic id, lvl
    load_name @varsyms[id - 1]
  end
  def getconstant sym
    load_name(sym)
  end
  def print_obj
    print_item
    print_newline
  end
  def import(mod, inner = nil)
    load_const(-1)

    mod_in, mod = import_split(mod)
    if inner
      inner_in, inner = import_split(inner)
      load_const(tuple(inner))
      mod_in = inner_in
    else
      load_const(nil)
    end

    import_name(mod)
    import_from(inner) if inner
    store_name(mod_in)
    pop_top if inner
  end
  def from(inner, mod)
    import(inner, mod)
  end
  def kernel_send(meth, *args)
    load_name(:Kernel)
    load_attr(meth)
    args.each do |obj|
      load_const(obj)
    end
    call_func(args.length)
  end

  def leave
    if @type == :class
      load_locals
    else
      load_const(nil) if @stack.empty?
    end
    ret_val
  end
  def duparray ary
    ary.each do |x|
      load_const x
    end
    build_list ary.length
  end
  def newarray size
    build_list size
  end
  def opt_aref
    binary_subscr
  end
  def opt_ltlt
    build_list 1
    inplace_add
  end
  def opt_plus
    binary_add
  end
  def putnil
    load_const(nil)
  end
  def putstring(str)
    str = @filename if str == "<compiled>"
    load_const(str)
  end
  def putobject(obj)
    load_const(obj)
  end
  def message(meth, op_argc, blockiseq, op_flag, ic)
    # args = @stack.slice! -op_argc, op_argc
    # bytes = @bytecode.slice! -op_argc, op_argc

    argc = op_argc + 1
    receiver, recbytes = @stack[-argc]
    args = @stack[-op_argc, op_argc].map { |o,_| o }
    idx = @bytecode.index { |x| x.object_id == recbytes.object_id }
    bytes = []

    if idx
      bytes = @bytecode.slice! idx..-1

      unless receiver
        unpop 
        case meth
        when :print
          @bytecode += bytes
          return print_obj
        when :import
          return import(*args)
        when :from
          return from(*args)
        when :tuple
          return load_const(tuple(*args))
        else
          load_name(:Kernel)
          bytes.shift
        end
      else
        @bytecode << bytes.shift
      end
    elsif op_argc > 0
      idx = @bytecode.index { |x| x.object_id == @stack[-op_argc][1].object_id }
      bytes = @bytecode.slice! idx..-1
    end

    if meth != :new
      load_attr(meth)
    end
    @bytecode += bytes

    if blockiseq
      blk = Pyasm.new(@filename, :block, "<block>", @lines.last[0])
      blk.load_iseq blockiseq
      load_const(blk)
      op_argc += 1
    end

    call_func(op_argc)
  end
  def unpop
    @nopop = 2
  end
  def pop
    pop_top unless @nopop > 0 or @stack.empty?
  end
  def opt_eq arg
    compare_op :==
  end
  def getglobal sym
    case sym when :$0
      load_const(@filename)
    end
  end
  def defineclass klass, iseq, is_singleton
    define :class, klass, iseq, is_singleton
  end
  def definemethod meth, iseq, is_singleton
    define :method, meth, iseq, is_singleton
  end
  def define type, id, iseq, is_singleton
    c = (type == :class) ? -2 : -1
    receiver, recbytes = @stack[c]
    idx = @bytecode.index { |x| x.object_id == recbytes.object_id }
    bytes = @bytecode.slice! idx..-1
    bytes.shift unless receiver

    argc = iseq[4][:arg_size]
    argc += 1 if type == :method # python's self
    asm = Pyasm.new(@filename, type, id.to_s, @lines.last[0], argc)
    if type == :class
      asm.load_name(:__name__)
      asm.store_name(:__module__)
    end
    asm.load_iseq iseq
    if type == :class
      load_const(id.to_s)
      if bytes.empty? or @consts[bytes[0][1]].nil?
        load_const(tuple())
      else
        @bytecode += bytes
        build_tuple(1)
      end
    end
    load_const(asm)
    make_func(0)
    if type == :class
      call_func(0)
      build_class 
    else
      @bytecode += bytes
    end
    store_name(id)

    # this is a bit redundant, but decompyle requires it
    if type == :method
      if @type == nil
        unless receiver
          load_name(id)
          load_name(:Kernel)
          store_attr(id)
        end
      elsif @type == :class and id == :initialize
        load_name(id)
        store_name(:__init__)
      end
    end
  end
  def branchunless label
    jump_if_false label
  end

  def load_iseq iseq
    iseq = iseq.to_a
    @varsyms += iseq[8].reverse

    iseq[11].each do |inst|
      case inst
      when Integer # line no
        line inst
      when Symbol
        label inst
      when Array
        inst[0] = :message if inst[0] == :send
        self.prep_send
        self.send *inst
      end
    end
  end
  def eval src
    begin
      iseq = VM::InstructionSequence.compile(src)
      load_iseq iseq
    rescue NameError => e
      puts "*** Are you sure you're running Ruby 1.9?"
      throw e
    end
  end

  def to_pickle
    # rewrite jumps to use python bytecode ordering
    @jumps.each do |n, jset|
      jset.each do |jump|
        idx = @bytecode.index(jump)
        pos = @bytecode[0,idx].flatten.length
        jump[1] = (@labels[n] - pos) - jump.length
      end
      # @jumps[1] = @labels[n]
    end

    f = "c"
    f << [@argc, @varsyms.length, @stacksize, @flags].pack("LLLL")

    # bytecode
    bytes = @bytecode.flatten
    f << "s" << bytes.length.to_plong
    f << bytes.pack("c*")

    # constants
    f << "(" << @consts.length.to_plong
    @consts.each do |c|
      f << c.to_pickle
    end

    # names
    f << "(" << @symbols.length.to_plong
    @symbols.each do |n|
      f << n.to_pickle
    end

    # varnames
    f << "(" << @varsyms.length.to_plong
    @varsyms.each do |n|
      f << n.to_pickle
    end

    # freevars
    f << "(" << 0.to_plong

    # cellvars
    f << "(" << 0.to_plong

    # metadata
    f << @filename.to_pickle
    f << @name.to_pickle
    f << 1.to_plong

    lnotab = ""
    lastn, lastpos = @lines[0]
    @lines[1..-1].each do |n, pos|
      lnotab << [pos - lastpos, n - lastn].pack("cc")
      lastn, lastpos = n, pos
    end
    f << lnotab.to_pickle
    f
  end

  def compile(fname)
    # dump the bytecode
    File.open(fname, "wb") do |f|
      f << "\xB3\xF2\r\n" # magic number for python 2.5
      f << Time.now.to_i.to_plong

      # code object
      f << self.to_pickle
    end
  end
end
