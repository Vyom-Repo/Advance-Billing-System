import re

file_path = '/Users/vyom/Vyom/Advance Billing/templates/settings_app/invoice_design.html'

with open(file_path, 'r') as f:
    html = f.read()

# Replace any newlines inside {% ... %} with a space
def remove_newlines_in_tags(match):
    content = match.group(1)
    # Collapse multiple spaces and newlines into a single space
    content_cleaned = re.sub(r'\s+', ' ', content)
    return '{%' + content_cleaned + '%}'

new_html = re.sub(r'\{%([^}]+)%\}', remove_newlines_in_tags, html)

# Also fix {{ ... }} just in case
def remove_newlines_in_vars(match):
    content = match.group(1)
    content_cleaned = re.sub(r'\s+', ' ', content)
    return '{{' + content_cleaned + '}}'

new_html = re.sub(r'\{\{([^}]+)\}\}', remove_newlines_in_vars, new_html)

with open(file_path, 'w') as f:
    f.write(new_html)

print("Fixed newlines inside Django template tags!")
