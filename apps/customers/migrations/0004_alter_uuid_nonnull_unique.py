"""
apps/customers/migrations/0004_alter_uuid_nonnull_unique.py

Enforce: uuid is non-nullable and unique across all Customer rows.
This runs after 0003 has backfilled UUIDs for every existing row,
so no NULL values remain.
"""
import uuid
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("customers", "0003_populate_uuid"),
    ]

    operations = [
        migrations.AlterField(
            model_name="customer",
            name="uuid",
            field=models.UUIDField(
                default=uuid.uuid4,
                editable=False,
                db_index=True,
                unique=True,
                null=False,
            ),
        ),
    ]
