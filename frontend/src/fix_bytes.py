with open('App.tsx', 'rb') as f:
    content = f.read()

# Replace the UTF-8 replacement character (ef bf bd) repeated 3 times with bullet (e2 80 a2)
corrupted = b'\xef\xbf\xbd\xef\xbf\xbd\xef\xbf\xbd'
clean = b'\xe2\x80\xa2'  # UTF-8 bullet point

content_fixed = content.replace(corrupted, clean)

with open('App.tsx', 'wb') as f:
    f.write(content_fixed)

print("✅ Fixed all corrupted characters!")
