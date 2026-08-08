import re

with open('/Users/vyom/Vyom/Advance Billing/templates/pdf/evergreen.html', 'r') as f:
    html = f.read()

# Replace taxable amount summary colspan
old_taxable = """                    {% if invoice.subtotal %}
                    <tr class="items-summary">

                        <td colspan="6" class="summary-label">
                            Taxable Amount
                        </td>

                        <td colspan="2" class="amount">
                            {{ invoice.subtotal }}
                        </td>

                    </tr>
                    {% endif %}"""

new_taxable = """                    {% if invoice.subtotal %}
                    <tr class="items-summary">

                        <td colspan="{% if prefs.show_hsn_sac %}6{% else %}5{% endif %}" class="summary-label">
                            Taxable Amount
                        </td>

                        <td colspan="2" class="amount">
                            {{ invoice.subtotal }}
                        </td>

                    </tr>
                    {% endif %}"""
html = html.replace(old_taxable, new_taxable)

# Replace GST summary wrapper colspan
old_gst_wrapper = """                    {% if prefs.show_gst_summary %}

                    <tr>
                        <td colspan="8" class="no-border">

                            <table class="gst-table">"""

new_gst_wrapper = """                    {% if prefs.show_gst_summary %}

                    <tr>
                        <td colspan="{% if prefs.show_hsn_sac %}8{% else %}7{% endif %}" class="no-border">

                            <table class="gst-table">"""
html = html.replace(old_gst_wrapper, new_gst_wrapper)

# Replace Total row colspan
old_total = """                    <tr class="total-row">

                        <td colspan="7" class="total-label">
                            Total
                        </td>

                        <td class="total-value">
                            {{ invoice.total }}
                        </td>

                    </tr>"""

new_total = """                    <tr class="total-row">

                        <td colspan="{% if prefs.show_hsn_sac %}7{% else %}6{% endif %}" class="total-label">
                            Total
                        </td>

                        <td class="total-value">
                            {{ invoice.total }}
                        </td>

                    </tr>"""
html = html.replace(old_total, new_total)

with open('/Users/vyom/Vyom/Advance Billing/templates/pdf/evergreen.html', 'w') as f:
    f.write(html)

print("Colspans adjusted successfully!")
