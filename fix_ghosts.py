import os
import re

templates_dir = "templates/pdf"
templates = [f for f in os.listdir(templates_dir) if f.endswith(".html")]

for tmpl in templates:
    with open(os.path.join(templates_dir, tmpl), "r") as f:
        content = f.read()

    original = content

    # 1. HSN ghost in GST Summary.
    # Usually it's: <th>HSN/SAC</th> or <th>HSN</th>
    # If it's already inside a show_hsn_sac if block, don't replace again.
    if '<th>HSN/SAC</th>' in content and 'prefs.show_hsn_sac %}' not in content.split('<th>HSN/SAC</th>')[0][-30:]:
        content = content.replace('<th>HSN/SAC</th>', '{% if prefs.show_hsn_sac %}<th>HSN/SAC</th>{% endif %}')
    if '<th rowspan="2">HSN/SAC</th>' in content and 'prefs.show_hsn_sac %}' not in content.split('<th rowspan="2">HSN/SAC</th>')[0][-30:]:
        content = content.replace('<th rowspan="2">HSN/SAC</th>', '{% if prefs.show_hsn_sac %}<th rowspan="2">HSN/SAC</th>{% endif %}')

    # Also HSN value cells in GST Summary
    # This requires manual logic. We know compact and landscape have HSN ghosts. Let's handle them.

    # 2. Payment info ghost "Amount Paid"
    # Example: <div>Amount Paid</div> or <td ...>Amount Paid</td>
    if "Amount Paid" in content and "prefs.show_payment_info" not in content:
        # Wrap the whole payment block. For compact and flipkart, it's usually a row or block.
        # It's better to just manually patch if we know the structure.
        pass

    # 3. Company Footer ghost "digitally signed document"
    # Example: This is a digitally signed document.
    if "This is a digitally signed document." in content:
        # replace it with: {% if prefs.show_company_footer %}This is a digitally signed document.{% endif %}
        content = re.sub(
            r'This is a digitally signed document\.',
            r'{% if prefs.show_company_footer %}This is a digitally signed document.{% endif %}',
            content
        )
        # Clean up nested ifs if we accidentally did it
        content = content.replace('{% if prefs.show_company_footer %}{% if prefs.show_company_footer %}This is a digitally signed document.{% endif %}{% endif %}', '{% if prefs.show_company_footer %}This is a digitally signed document.{% endif %}')
        content = content.replace('{% if prefs.show_company_footer %}This is a digitally signed document.{% endif %}{% endif %}', 'This is a digitally signed document.{% endif %}')

    if original != content:
        with open(os.path.join(templates_dir, tmpl), "w") as f:
            f.write(content)
        print(f"Fixed basic ghosts in {tmpl}")

