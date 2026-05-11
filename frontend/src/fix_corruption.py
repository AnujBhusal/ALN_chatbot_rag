with open('App.tsx', 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Fix line 794 (index 793) - corrupted date separator
if 793 < len(lines) and 'formattedDate' in lines[793] and 'msgs' in lines[793]:
    lines[793] = lines[793].replace('´┐¢´┐¢´┐¢', '•')
    print("✅ Fixed line 794 (date separator)")

# Fix line 808 (index 807) - corrupted delete comment
if 807 < len(lines) and 'Delete button' in lines[807]:
    lines[807] = lines[807].replace('´┐¢´┐¢´┐¢', '→')
    print("✅ Fixed line 808 (delete button comment)")

# Fix line 929 (index 928) - corrupted render comment
if 928 < len(lines) and 'Render content' in lines[928]:
    lines[928] = lines[928].replace('´┐¢´┐¢´┐¢', '→')
    print("✅ Fixed line 929 (render comment)")

with open('App.tsx', 'w', encoding='utf-8') as f:
    f.writelines(lines)

print("✅ All corrupted characters fixed!")
