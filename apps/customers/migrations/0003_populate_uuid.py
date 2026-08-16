"""
apps/customers/migrations/0003_populate_uuid.py

Data migration: assign a unique UUID to every existing Customer row
that currently has a NULL uuid value.
"""
import uuid as uuid_lib
from django.db import migrations


def populate_customer_uuids(apps, schema_editor):
    Customer = apps.get_model("customers", "Customer")
    for customer in Customer.objects.filter(uuid__isnull=True).iterator():
        customer.uuid = uuid_lib.uuid4()
        customer.save(update_fields=["uuid"])


def reverse_populate(apps, schema_editor):
    # Reversing a data migration is a no-op — we simply leave the UUIDs in place.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("customers", "0002_customer_uuid"),
    ]

    operations = [
        migrations.RunPython(populate_customer_uuids, reverse_populate),
    ]
