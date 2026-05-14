import sys

with open('data/product_master.json', 'rb') as f:
    content = f.read()

print(f"File size: {len(content)} bytes")
print(f"\nLast 150 bytes (hex):")
last_bytes = content[-150:]
for i in range(0, len(last_bytes), 16):
    hex_str = ' '.join(f'{b:02x}' for b in last_bytes[i:i+16])
    ascii_str = ''.join(chr(b) if 32 <= b < 127 else '.' for b in last_bytes[i:i+16])
    print(f"{len(content)-150+i:04x}: {hex_str:<48} {ascii_str}")

print(f"\nLast 150 bytes (decoded utf-8):")
try:
    print(repr(content[-150:].decode('utf-8')))
except:
    print(repr(content[-150:]))
