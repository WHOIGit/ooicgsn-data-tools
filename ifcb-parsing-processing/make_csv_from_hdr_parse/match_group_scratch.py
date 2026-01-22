import re

# Define the search string
text = "triggerCount: 9999"

pattern = re.compile(r'triggerCount:\s*(\d+)')
print("pattern: ", pattern)

# Using re.search() with the compiled pattern
match = pattern.search(text)

if match:
    # Extracting the matched number
    number = match.group(1)
    print("Match found:", number)
else:
    print("No match found")