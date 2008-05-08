class Module
  def to_pickle; self.name.to_pickle end
end

class NilClass
  def to_pickle; "N" end
end

class Integer
  def to_plong; [self].pack("L") end
  def to_pickle; "i#{to_plong}" end
end

class String
  def to_pickle; "s" + length.to_plong + self end
end

class Symbol
  def to_pickle
    str = to_s
    "t" + str.length.to_plong + str
  end
end
