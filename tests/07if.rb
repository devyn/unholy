# 123
# 123
# 456
# 123
a = []
if true
  a << 123
end
puts a[0]

a = []
if true
  a << 123
else
  a << 456
end
puts a[0]

a = []
if false
  a << 123
else
  a << 456
end
puts a[0]

puts 123 if true
