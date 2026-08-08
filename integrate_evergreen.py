import re

with open('/Users/vyom/Downloads/reference_invoice_template.html', 'r') as f:
    html = f.read()

# 1. Update @page CSS for letterhead layout_frame
html = re.sub(
    r'@page \{.*?\}',
    r'@page {\n        size: {{ layout_frame.paper_size }} {{ layout_frame.orientation }};\n        margin-top: {{ layout_frame.margin_top }}mm;\n        margin-bottom: {{ layout_frame.margin_bottom }}mm;\n        margin-left: 10mm;\n        margin-right: 10mm;\n    }',
    html,
    flags=re.DOTALL
)

# 2. Insert header spacer after <body>
header_spacer = '\n{% if layout_frame.print_on_letterhead %}\n    <div style="height: {{ layout_frame.header_spacer }}mm;"></div>\n{% endif %}\n'
html = html.replace('<body>', '<body>' + header_spacer)

# 3. Insert footer spacer before </body>
footer_spacer = '\n{% if layout_frame.print_on_letterhead %}\n    <div style="height: {{ layout_frame.footer_spacer }}mm;"></div>\n{% endif %}\n'
html = html.replace('</body>', footer_spacer + '</body>')

# 4. Map variables
replacements = {
    '{{ org.name }}': '{{ company.name }}',
    '{{ org.address }}': '{{ company.address }}',
    '{{ org.city }}': '{{ company.city }}',
    '{{ org.state }}': '{{ company.state }}',
    '{{ org.pincode }}': '{{ company.pincode }}',
    '{{ org.mobile }}': '{{ company.phone }}',
    '{{ org.email }}': '{{ company.email }}',
    '{{ org.gstin }}': '{{ company.gstin }}',
    '{{ org.logo }}': '{{ org.logo.path }}',  # In case it uses org.logo directly
    '{% for item in invoice.items %}': '{% for item in items %}',
    '{{ item.hsn_sac }}': '{{ item.hsn }}',
    '{{ item.tax_rate }}': '{{ item.tax_pct }}',
    '{{ invoice.taxable_amount }}': '{{ invoice.subtotal }}',
    '{{ invoice.total_tax }}': '{{ invoice.tax_total }}',
    '{{ bank.name }}': '{{ company.bank_name }}',
    '{{ bank.account_number }}': '{{ company.acc_no }}',
    '{{ bank.ifsc }}': '{{ company.ifsc }}',
    '{{ bank.branch }}': '{{ company.city }}',
    '{{ invoice.qr_image }}': '{{ invoice.qr_image.url }}',
    # Map logo if it uses org.logo directly inside an img
    'src="file://{{ org.logo.path }}"': 'src="file://{{ org.logo.path }}"',
}

for old, new in replacements.items():
    html = html.replace(old, new)

# 5. Fix notes loop if there is one, or terms loop
# Advance Billing uses invoice.terms as a string, but the reference has:
# {% for term in invoice.terms %} ... {{ forloop.counter }}. {{ term }} {% endfor %}
# If invoice.terms is a string, a for loop will iterate over characters.
# We must replace the loop with linebreaksbr
html = re.sub(
    r'\{% for term in invoice.terms %}.*?\{% endfor %\}',
    r'<div>\n                            {{ invoice.terms|linebreaksbr }}\n                        </div>',
    html,
    flags=re.DOTALL
)

with open('/Users/vyom/Vyom/Advance Billing/templates/pdf/evergreen.html', 'w') as f:
    f.write(html)

print("Evergreen template successfully copied and integrated!")
