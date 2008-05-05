class Tuple < Array
  def to_pickle
    "(" + length.to_plong + map { |x| x.to_pickle }.join
  end
end

def tuple(*ary); Tuple[*ary] end
